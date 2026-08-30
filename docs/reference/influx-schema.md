# Reference: InfluxDB schema

vw-telemetry writes into an existing InfluxDB instance (the same engine `open-california` uses on
buspi) but its own bucket — no code, bucket, or dashboard is shared with the camper project.

## Instance, org, bucket

| | |
|---|---|
| Org | `home` (reused) |
| Bucket | `vehicle` (new — created by `deploy/setup-bucket.sh`) |
| Retention | long (~5 years); at roughly 96 points/day/vehicle the volume is tiny |
| Write access | a token scoped to the `vehicle` bucket only — it cannot read or write the camper project's `buspi` bucket |

## Measurement

One measurement: **`vehicle`**.

## Tags

| Tag | Meaning |
|---|---|
| `vin` | the vehicle's VIN, auto-discovered from the VW-ID account at runtime — never hard-coded or committed |
| `brand` | `volkswagen` \| `audi` \| `skoda` \| `seat` \| `cupra` \| `bentley` |
| `source` | always `eu_data_act` |

## Timestamp

Each point is stamped with the **vehicle's own measurement time** — the maximum
`timestampUtc` across the dataset's fields — not the time the poller ran. This means backfilled
datasets land at their true historical moment, and Grafana always shows real vehicle time rather
than ingest time.

## Fields

All fields are decoded, typed, and unit-suffixed by `vwtelemetry.decode`. A field is only written
when the source dataset actually carries a value for it, so different datasets can populate
different subsets of these fields on the same point.

### Continuous

| Field | Meaning |
|---|---|
| `mileage_km` | odometer |
| `fuel_pct` | fuel tank level |
| `adblue_pct` | AdBlue tank level |
| `range_km` | combined cruising range |
| `adblue_range_km` | AdBlue (SCR) range |
| `outside_temp_c` | outside temperature (portal delivers deci-Kelvin; converted to °C) |
| `oil_level` | oil level (actual) |
| `trip_short_km` | short-term trip distance |
| `trip_short_l_per_100km` | short-term trip average consumption |
| `trip_short_avg_speed_kmh` | short-term trip average speed (derived from distance/time) |
| `trip_long_avg_speed_kmh` | long-term trip average speed |
| `trip_long_l_per_100km` | long-term trip average consumption |

### Per-door booleans

For each of the six openings (front-left door, front-right door, rear-left door, rear-right door,
tailgate, front engine bonnet):

| Field pattern | Meaning |
|---|---|
| `door_<pos>_locked` | `true`/`false` — decoded from the portal's lock-state enum (`2 = locked`, `3 = unlocked`) |
| `door_<pos>_open` | `true`/`false` — decoded from the portal's open-state enum (`2 = open`, `3 = closed`) |

### Aggregates (dashboard-friendly rollups)

| Field | Meaning |
|---|---|
| `doors_locked` | count of openings currently locked |
| `doors_open` | count of openings currently open |
| `any_unlocked` | `true` if any door (excluding the bonnet) is unlocked |
| `tyres_all_ok` | `true` if every reported tyre-pressure status code is OK (status codes, not bar values — see [design §9](../explanation/design.md#9-known-limitations-honest-from-the-re)) |
| `parking_brake` | `true`/`false` |
| `warnings_active` | count of active instrument-cluster warnings |

### Service

| Field | Meaning |
|---|---|
| `inspection_km_remaining` | distance to next inspection; negative = overdue |
| `oil_km_remaining` | distance to next oil change; negative = overdue |

Negative service-remaining values are intentional (not clamped to zero) so Grafana can apply a red
"overdue" threshold directly to the raw field. The design also anticipates a `_days_remaining` and
a `windows_open` counterpart for these; they are not decoded yet — see
[Add a new field](../how-to/add-a-field.md) if the portal exposes them for your vehicle.

Both the raw per-door detail and the aggregate rollups are stored on the same point, so a
dashboard can show a full status table and simple stat panels without needing Flux-side
aggregation.
