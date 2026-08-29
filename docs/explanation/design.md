# vw-telemetry — design

Status: **approved design (2026-08-29)**, pre-implementation. This is the committed spec; the
implementation plan follows (writing-plans). Author: brainstormed with Claude.

## 1. Purpose & scope

A **standalone** service that pulls Volkswagen-Group vehicle telemetry from the **EU Data Act
portal** and writes it to **InfluxDB** for visualisation in **Grafana**. It is deliberately
independent of the `open-california` camper (BLE) project — it shares the same buspi host and the
same Grafana/InfluxDB *engines*, but no code, no bucket, and no dashboard.

**Why the EU Data Act portal:** VW locked the app/WeConnect API behind Google Play Integrity
**attestation** (a Google-signed, device-bound token a server can't forge). The EU Data Act portal
(`eu-data-act.drivesomethinggreater.com`) is the sanctioned, attestation-free path — VW-ID login
only. It is **read-only** and delivers a dataset roughly every **15 minutes** (batch, not live). See
§9 and the `explanation/attestation.md` note.

**Generic by design:** no personal data, VIN, brand, or host is baked in. Any user, with any
VW-Group car (VW / Audi / Škoda / SEAT / Cupra / Bentley), on any InfluxDB+Grafana host, configures
it entirely via environment.

## 2. Non-goals

- No control/commands (the feed is read-only; there is no actuation path).
- No live/CAN data, no GPS parking position (the EU Data Act feed omits location — see §9).
- No coupling to `open-california` or the `volkswagen_decompile` analysis repo.

## 3. Architecture

A **oneshot** entrypoint, fired by a **systemd timer every 15 minutes**:

```
login (VW-ID)                     reader.py
  → list vehicles on the account  reader.py   (VIN auto-discovered; never configured)
  → for each vehicle:
      → list partial datasets     reader.py
      → for each dataset NOT yet ingested (watermark):
          → download + parse      reader.py
          → decode enums/scales   decode.py   (lock/open/window/deci-Kelvin/…)
          → build InfluxDB points influx.py
      → write points              influx.py
  → advance the watermark         poll.py
  → exit
```

Idempotent: each dataset is keyed by its filename; a per-(vin) **watermark** in `state/` prevents
double-writes, so the timer is crash-safe and naturally backfills the portal's rolling 30-dataset
window on each run.

**Implementation note (hard-won):** `reader.py` uses the **low-level `EudaApiClient`**
(`login` → `list_vehicles` → `get_metadata` → `list_datasets` → `download_dataset`), *not* the
high-level `CarConnectivity.fetch_all()` — the latter downloads and merges all ~30 datasets in one
blocking call and hung in testing. Per-dataset download + our own `decode.py` is reliable and lets us
control exactly which datasets are ingested (via the watermark).

### Module layout

```
vw-telemetry/
  vwtelemetry/
    reader.py     # EU Data Act client: login, list vehicles/datasets, download, dedupe
    decode.py     # enum + scale decoders -> typed values with units
    influx.py     # decoded record -> InfluxDB Points; write
    poll.py       # the oneshot orchestration (reader -> decode -> influx), watermark
    config.py     # env-driven config (creds, brand, country, vin allowlist, influx target)
  tests/          # decode/points/dedupe unit tests + the no-private-data guard
  deploy/
    vw-telemetry.service        # systemd oneshot
    vw-telemetry.timer          # every 15 min
    setup-bucket.sh             # create the influx bucket + scoped token (idempotent)
    grafana-vehicle.json        # the dashboard (with a $vin template variable)
    grafana-datasource.yaml     # provisioned InfluxDB datasource
    push_dashboard.py           # push the dashboard to Grafana (Pi; Cloud optional)
    vw-telemetry.env.example    # config template (placeholders only)
  docs/           # Diátaxis: tutorials/ how-to/ reference/ explanation/
  .github/workflows/ci.yml
  .pre-commit-config.yaml · .gitleaks.toml · mkdocs.yml · pyproject.toml · README.md
```

## 4. Configuration (all via environment; nothing personal in git)

| Env | Meaning | Default |
|---|---|---|
| `VWID_USER` / `VWID_PASSWORD` | VW-ID login | — (required) |
| `VW_BRAND` | volkswagen \| audi \| skoda \| seat \| cupra \| bentley | volkswagen |
| `VW_COUNTRY` | portal country | DE |
| `VW_VIN_ALLOWLIST` | comma list; blank = all vehicles on the account | blank |
| `INFLUX_URL` / `INFLUX_ORG` | InfluxDB target | http://localhost:8086 / home |
| `INFLUX_BUCKET` | destination bucket | vehicle |
| `INFLUX_TOKEN` | write token scoped to the bucket | — (required) |

On buspi these live in `/etc/buspi/vw-telemetry.env` (root, 0600), mirroring `calictl.env`. On a Mac
dev box, creds may come from the macOS Keychain (service `vw-telemetry`) with `.env` fallback.

**VIN is never configured or committed** — it is discovered from the account at runtime and only
ever appears as an InfluxDB **tag** (the user's own data, on the user's own host).

## 5. InfluxDB schema

- **Instance / org:** the existing buspi InfluxDB, org `home` (reuse the engine).
- **Bucket:** **`vehicle`** — new, long retention (~5 y; ~96 points/day/vehicle is tiny). Its own
  **write token scoped to this bucket only**, so it cannot read/write the camper `buspi` bucket.
- **Measurement:** one, **`vehicle`**.
- **Tags:** `vin`, `brand`, `source=eu_data_act`.
- **Timestamp:** the **vehicle's real measurement time** (`timestampUtc` from the fields; the max
  field timestamp per dataset) — NOT ingest time. This makes backfill land at correct historical
  moments and Grafana show true vehicle time.
- **Fields** (decoded, typed, unit-suffixed names):
  - *Continuous:* `mileage_km`, `fuel_pct`, `adblue_pct`, `range_km`, `adblue_range_km`,
    `outside_temp_c`, `oil_level`, `trip_short_km`, `trip_short_l_per_100km`,
    `trip_long_avg_speed_kmh`, `trip_long_l_per_100km`.
  - *Per-door booleans:* `door_<pos>_locked` (0/1), `door_<pos>_open` (0/1) for the six openings.
  - *Aggregates (dashboard-friendly):* `doors_locked` (count), `doors_open`, `any_unlocked` (bool),
    `windows_open`, `tyres_all_ok` (bool), `parking_brake` (bool), `warnings_active` (count).
  - *Service:* `inspection_km_remaining`, `oil_km_remaining` (negative = overdue → Grafana red
    threshold), plus the `_days_remaining` counterparts.

Both raw per-door detail *and* rollups are stored, so the dashboard can show a status table and
simple stat panels without Flux gymnastics.

## 6. Grafana

- A **new provisioned InfluxDB datasource** for bucket `vehicle` (Flux).
- A **new dashboard** `grafana-vehicle.json` with a **`$vin` template variable** (dropdown of the
  user's vehicles) + optional `$brand`, so it serves 1..N cars and any user.
- **Panels:** mileage timeline · fuel + AdBlue gauges · range · consumption trend (short/long) ·
  driving-style scatter (avg speed vs L/100km) · lock/open status table · **service-overdue stat
  (red threshold)** · warnings stat · tyre status.
- Pushed via `push_dashboard.py` to the **Pi Grafana (localhost:3000)**; Grafana Cloud push is
  optional/deferred (the Cloud token is not pi-readable — same limitation noted for the camper).

## 7. CI & quality gates — credential/data protection first

Defense in depth so a secret or a real VIN cannot be committed even if one layer is bypassed:

1. **`.gitignore`** (present from commit #1): `.env`/`*.env` (except `.example`), `state/`, `*.jsonl`,
   `data/`, `archive/`, `*.zip`.
2. **pre-commit** (local, fast, auto-fix): `gitleaks`, `detect-private-key`,
   `check-added-large-files`, end-of-file/trailing-whitespace; **Ruff** lint+format; and a custom
   **`no-private-data`** hook — fails if a staged file matches a real VW-Group VIN pattern
   (`W` + valid WMI, 17 chars) or a populated `VWID_PASSWORD=`/token.
3. **GitHub Actions CI** (authoritative; can't be locally skipped):
   | Stage | Tool |
   |---|---|
   | secret-scan | `gitleaks` (full history) |
   | no-private-data guard | pytest test grepping the tree for VIN/cred patterns |
   | lint + format | **Ruff** (incl. `S` security rules) |
   | types | **mypy --strict** |
   | test | **pytest** (decoders, point-building, dedupe) |
   | docs | `mkdocs build --strict` |

**The VIN guard is generic:** it blocks real VINs, while tests/docs use a synthetic placeholder
(`VWTELEMETRY000TEST`, which deliberately does not match the real-VIN regex; the guard allowlists
exactly that one string). Tooling is **uv** (fast env + lockfile) — the 2026 standard stack
(uv + Ruff + mypy + pytest + pre-commit).

## 8. Documentation — Diátaxis + MkDocs Material + mkdocstrings

Markdown-first, API reference auto-generated from docstrings, organised by the **Diátaxis** four
quadrants (as Django/NumPy do):

- **Tutorial:** zero → your vehicle in Grafana (deploy + first data).
- **How-to:** deploy to buspi · add a new field · rotate creds · create the bucket · add a brand.
- **Reference:** the InfluxDB schema, the **field catalog** (every metric + unit + source), the
  config/env table, the systemd units, the CLI.
- **Explanation:** the attestation story (why EU Data Act), the architecture, the real-timestamp
  decision, why standalone.

Public functions carry docstrings (Google style, mkdocstrings-rendered). CI runs
`mkdocs build --strict`; docs are **not published publicly** (the repo is private and users' data is
personal) — build-check only, with private GitHub Pages as an optional later step. (NB: Material for
MkDocs is stable now; its successor *Zensical* reads the same config, so no lock-in.)

## 9. Known limitations (honest, from the RE)

- **Batch, not live:** ~15-min cadence; VW may delay the *first* delivery by hours after a data
  request is enabled; parked/idle vehicles emit empty datasets until driven.
- **No GPS parking position** in the EU Data Act feed (attestation-gated app API only).
- **Tyre pressures are status codes** (OK/warn), not bar values.
- **No driving score** (harsh-braking/acceleration events); "driving style" is derived from
  consumption + speed.
- Depends on the community `carconnectivity-connector-vw-eu-data-act`, which tracks portal changes.

## 10. Deploy flow (buspi)

1. `git clone` under `/home/pi/` (or `~/src`), create a venv, `uv pip install -r requirements.txt`.
2. `/etc/buspi/vw-telemetry.env` (root 0600) with creds + influx target + scoped token.
3. `deploy/setup-bucket.sh` — create the `vehicle` bucket + scoped write token (idempotent).
4. Install + enable `vw-telemetry.timer` (15 min) + `.service`.
5. Add the Grafana datasource + import the dashboard (`push_dashboard.py`).
6. First runs backfill the portal's retained window; optional archive import backfills full history
   at correct timestamps.
