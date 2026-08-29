# vw-telemetry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone service that pulls VW-Group telemetry from the EU Data Act portal, decodes it, writes it to a dedicated InfluxDB bucket, and surfaces it in a Grafana dashboard — run as a 15-minute systemd-timer oneshot.

**Architecture:** A oneshot Python entrypoint (`poll.py`) orchestrates: `config` (env) → `reader` (low-level `EudaApiClient`: login, auto-discover vehicles, download only not-yet-ingested datasets via a per-VIN watermark) → `decode` (raw enum/scale codes → typed record) → `influx` (points into bucket `vehicle`, timestamped at the vehicle's real measurement time). Grafana reads the bucket via a `$vin` dashboard variable. Defense-in-depth CI (gitleaks + a no-real-VIN guard + ruff + mypy + pytest + mkdocs build) is in place from the first code commit.

**Tech Stack:** Python 3.11+, `uv` (env + lockfile), `ruff` (lint+format, incl. `S` security rules), `mypy --strict`, `pytest`, `pre-commit`, `gitleaks`, `influxdb-client`, `carconnectivity-connector-vw-eu-data-act` (its low-level `EudaApiClient` only), MkDocs Material + mkdocstrings.

**Spec:** `docs/explanation/design.md` (in this repo). The plan implements that design; executors read both.

## Global Constraints

- **VIN is never committed.** No real VIN in code, tests, fixtures, or docs. Tests use the single allowlisted synthetic VIN **`WVWTELEMETRY00TES`** (17 chars, VIN charset, obviously fake). The no-private-data guard blocks every other VIN-shaped token.
- **No credentials committed.** `.env`/`*.env` (except `*.env.example`), `state/`, `*.jsonl`, `*.zip`, `data/` are gitignored (already present).
- **Generic:** brand/country/host/VIN-filter all from environment. No personal defaults. Auto-discover all vehicles on the account.
- **Reader uses the low-level `EudaApiClient`** (`login`/`list_vehicles`/`get_metadata`/`list_datasets`/`download_dataset`) — NOT `CarConnectivity.fetch_all()` (it merges all ~30 datasets in one blocking call and hangs).
- **InfluxDB:** org `home` (default), bucket **`vehicle`**, measurement **`vehicle`**, tags `vin`/`brand`/`source=eu_data_act`, point time = the dataset's real `timestampUtc` (max field timestamp), never ingest time.
- **Python floor 3.11**; **ruff + mypy --strict must pass**; every task ends green.
- **Enum codes (authoritative, from the connector's decoders):** lock `2=locked/3=unlocked`; open `2=open/3=closed`; lights `2=off/3,4,5=on`; parking_brake `0=released/1=engaged`; outside temp is **deci-Kelvin** → °C = `value/10 - 273.15`; consumption fields are **deci-L/100km** → `/10`; maintenance remaining negative = overdue.

---

## File Structure

```
vw-telemetry/
  pyproject.toml            # uv project, ruff+mypy+pytest config, deps
  .pre-commit-config.yaml   # gitleaks, detect-private-key, no-private-data, ruff
  .gitleaks.toml            # gitleaks config
  .github/workflows/ci.yml  # secret-scan · guard · ruff · mypy · pytest · docs
  mkdocs.yml                # Diátaxis nav + mkdocstrings
  vwtelemetry/
    __init__.py
    config.py               # Config dataclass from env (+ Mac Keychain fallback)
    reader.py               # EudaApiClient wrapper: login, discover, download, dedupe
    decode.py               # raw dataset dict -> typed decoded record
    influx.py               # decoded record -> InfluxDB Points; write
    poll.py                 # oneshot orchestration + per-VIN watermark
  tests/
    test_no_private_data.py # the guard (Task 1)
    test_config.py          # Task 2
    test_decode.py          # Task 4 (the biggest test surface)
    test_influx.py          # Task 5
    test_reader.py          # Task 3
    test_poll.py            # Task 6
    conftest.py             # shared fixtures (a synthetic dataset)
  deploy/
    vw-telemetry.service · vw-telemetry.timer
    setup-bucket.sh · vw-telemetry.env.example
    grafana-datasource.yaml · grafana-vehicle.json · push_dashboard.py
  docs/                     # explanation/ (design.md exists) + tutorials/ how-to/ reference/
```

---

## Task 1: Project scaffolding + CI safety net (the guard first)

Rationale: the credential/VIN guard and CI must exist before any code that touches data. This task delivers a green CI on an (almost) empty project plus the no-private-data guard test.

**Files:**
- Create: `pyproject.toml`, `.pre-commit-config.yaml`, `.gitleaks.toml`, `.github/workflows/ci.yml`, `vwtelemetry/__init__.py`, `tests/__init__.py`
- Test: `tests/test_no_private_data.py`

**Interfaces:**
- Produces: the repo's tooling contract (ruff/mypy/pytest via `uv`), and `tests/test_no_private_data.py::test_no_real_vin_committed` / `::test_no_credentials_committed` that later tasks must keep green.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "vw-telemetry"
version = "0.1.0"
description = "VW-Group EU Data Act telemetry -> InfluxDB -> Grafana"
requires-python = ">=3.11"
dependencies = [
    "influxdb-client>=1.40",
    "carconnectivity-connector-vw-eu-data-act>=0.3",
]

[dependency-groups]
dev = ["pytest>=8", "mypy>=1.11", "ruff>=0.6", "pre-commit>=3.8",
       "mkdocs-material>=9.5", "mkdocstrings[python]>=0.26"]

[tool.ruff]
target-version = "py311"
line-length = 100
[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "S"]   # incl. S = bandit security rules
[tool.ruff.lint.per-file-ignores]
"tests/*" = ["S101"]   # asserts are fine in tests

[tool.mypy]
python_version = "3.11"
strict = true
[[tool.mypy.overrides]]
module = ["carconnectivity_connectors.*", "influxdb_client.*"]
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Write the guard test `tests/test_no_private_data.py`**

```python
"""CI guard: no real VIN and no credentials may ever be committed."""
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# The ONE allowlisted synthetic VIN used by tests/docs. Everything else VIN-shaped is blocked.
PLACEHOLDER_VIN = "WVWTELEMETRY00TES"
VIN_RE = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b")          # 17-char VIN charset (no I/O/Q)
CRED_RE = re.compile(r"(VWID_PASSWORD|INFLUX_TOKEN)\s*=\s*\S+")


def _tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True)
    return [REPO / p for p in out.stdout.split() if p]


def _text_files() -> list[Path]:
    keep = {".py", ".md", ".toml", ".yml", ".yaml", ".sh", ".json", ".cfg", ".txt", ".example"}
    return [p for p in _tracked_files() if p.suffix in keep and p.is_file()]


def test_no_real_vin_committed():
    offenders = []
    for f in _text_files():
        for m in VIN_RE.findall(f.read_text(errors="ignore")):
            if m != PLACEHOLDER_VIN:
                offenders.append(f"{f.relative_to(REPO)}: {m}")
    assert not offenders, "VIN-shaped tokens committed (use the placeholder in tests):\n" + "\n".join(offenders)


def test_no_credentials_committed():
    offenders = []
    for f in _text_files():
        if f.name.endswith(".env.example"):
            continue                      # placeholders like VWID_PASSWORD= (empty) are fine here
        for m in CRED_RE.findall(f.read_text(errors="ignore")):
            offenders.append(f"{f.relative_to(REPO)}: {m}")
    assert not offenders, "credential assignments committed:\n" + "\n".join(offenders)
```

- [ ] **Step 3: Run the guard, expect PASS on the clean repo**

Run: `uv run pytest tests/test_no_private_data.py -v`
Expected: 2 passed (nothing sensitive committed yet).

- [ ] **Step 4: Write `.gitleaks.toml`**

```toml
title = "vw-telemetry gitleaks config"
[extend]
useDefault = true
[allowlist]
description = "synthetic test VIN + example env placeholders"
regexes = ['''WVWTELEMETRY00TES''']
paths = ['''.*\.env\.example$''']
```

- [ ] **Step 5: Write `.pre-commit-config.yaml`**

```yaml
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.18.4
    hooks: [{id: gitleaks}]
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - {id: detect-private-key}
      - {id: check-added-large-files}
      - {id: end-of-file-fixer}
      - {id: trailing-whitespace}
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.9
    hooks:
      - {id: ruff, args: [--fix]}
      - {id: ruff-format}
  - repo: local
    hooks:
      - id: no-private-data
        name: no private data (VIN/creds)
        entry: uv run pytest tests/test_no_private_data.py -q
        language: system
        pass_filenames: false
```

- [ ] **Step 6: Write `.github/workflows/ci.yml`**

```yaml
name: ci
on: [push, pull_request]
jobs:
  secret-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: {fetch-depth: 0}
      - uses: gitleaks/gitleaks-action@v2
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv python install 3.11
      - run: uv sync --all-extras
      - run: uv run pytest tests/test_no_private_data.py -v   # guard runs first
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run mypy vwtelemetry
      - run: uv run pytest -v
      - run: uv run mkdocs build --strict
```

- [ ] **Step 7: Create empty packages**

```bash
mkdir -p vwtelemetry tests && touch vwtelemetry/__init__.py tests/__init__.py
```

- [ ] **Step 8: Verify the whole quality gate locally**

Run: `uv sync --all-extras && uv run ruff check . && uv run pytest -v`
Expected: ruff clean; guard tests pass. (mkdocs build is added in Task 9 — until then run CI's other stages.)

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml .pre-commit-config.yaml .gitleaks.toml .github vwtelemetry tests
git commit -m "ci: tooling + no-private-data guard (gitleaks, ruff, mypy, pytest) from commit #1"
```

---

## Task 2: `config.py` — env-driven configuration

**Files:**
- Create: `vwtelemetry/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Config` dataclass with fields `vwid_user: str`, `vwid_password: str`, `brand: str`, `country: str`, `vin_allowlist: list[str]`, `influx_url: str`, `influx_org: str`, `influx_bucket: str`, `influx_token: str`; and `Config.from_env() -> Config` (raises `SystemExit` with a clear message when a required value is missing). Consumed by `reader.py`, `influx.py`, `poll.py`.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from vwtelemetry.config import Config


def test_from_env_reads_all(monkeypatch):
    for k, v in {"VWID_USER": "u@e.com", "VWID_PASSWORD": "pw", "VW_BRAND": "audi",
                 "VW_COUNTRY": "AT", "VW_VIN_ALLOWLIST": "WVWTELEMETRY00TES, ABC",
                 "INFLUX_URL": "http://x:8086", "INFLUX_ORG": "home",
                 "INFLUX_BUCKET": "vehicle", "INFLUX_TOKEN": "tok"}.items():
        monkeypatch.setenv(k, v)
    c = Config.from_env()
    assert c.brand == "audi" and c.country == "AT"
    assert c.vin_allowlist == ["WVWTELEMETRY00TES", "ABC"]
    assert c.influx_bucket == "vehicle" and c.vwid_user == "u@e.com"


def test_defaults(monkeypatch):
    for k in ("VW_BRAND", "VW_COUNTRY", "VW_VIN_ALLOWLIST", "INFLUX_URL", "INFLUX_ORG", "INFLUX_BUCKET"):
        monkeypatch.delenv(k, raising=False)
    for k, v in {"VWID_USER": "u", "VWID_PASSWORD": "p", "INFLUX_TOKEN": "t"}.items():
        monkeypatch.setenv(k, v)
    c = Config.from_env()
    assert c.brand == "volkswagen" and c.country == "DE"
    assert c.influx_url == "http://localhost:8086" and c.influx_org == "home"
    assert c.influx_bucket == "vehicle" and c.vin_allowlist == []


def test_missing_required_exits(monkeypatch):
    monkeypatch.delenv("VWID_USER", raising=False)
    monkeypatch.setenv("VWID_PASSWORD", "p")
    monkeypatch.setenv("INFLUX_TOKEN", "t")
    with pytest.raises(SystemExit):
        Config.from_env()
```

- [ ] **Step 2: Run, expect FAIL** — `uv run pytest tests/test_config.py -v` → ImportError/fail.

- [ ] **Step 3: Implement `vwtelemetry/config.py`**

```python
"""Environment-driven configuration. Nothing personal is hard-coded; every value comes from env
(on buspi: /etc/buspi/vw-telemetry.env). A .env in the CWD is loaded if present."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass


def _load_dotenv(path: str = ".env") -> None:
    if not os.path.isfile(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Config:
    vwid_user: str
    vwid_password: str
    brand: str
    country: str
    vin_allowlist: list[str]
    influx_url: str
    influx_org: str
    influx_bucket: str
    influx_token: str

    @classmethod
    def from_env(cls) -> "Config":
        _load_dotenv()
        missing = [k for k in ("VWID_USER", "VWID_PASSWORD", "INFLUX_TOKEN") if not os.environ.get(k)]
        if missing:
            sys.exit("Missing required env: %s (see deploy/vw-telemetry.env.example)" % ", ".join(missing))
        raw = os.environ.get("VW_VIN_ALLOWLIST", "")
        allow = [v.strip() for v in raw.split(",") if v.strip()]
        return cls(
            vwid_user=os.environ["VWID_USER"],
            vwid_password=os.environ["VWID_PASSWORD"],
            brand=os.environ.get("VW_BRAND", "volkswagen"),
            country=os.environ.get("VW_COUNTRY", "DE"),
            vin_allowlist=allow,
            influx_url=os.environ.get("INFLUX_URL", "http://localhost:8086"),
            influx_org=os.environ.get("INFLUX_ORG", "home"),
            influx_bucket=os.environ.get("INFLUX_BUCKET", "vehicle"),
            influx_token=os.environ["INFLUX_TOKEN"],
        )
```

- [ ] **Step 4: Run, expect PASS** — `uv run pytest tests/test_config.py -v`.

- [ ] **Step 5: Commit** — `git add vwtelemetry/config.py tests/test_config.py && git commit -m "feat(config): env-driven Config.from_env"`

---

## Task 3: `decode.py` — raw dataset → typed record

This is the core value + biggest test surface. Pure functions, no I/O.

**Files:**
- Create: `vwtelemetry/decode.py`, `tests/conftest.py`
- Test: `tests/test_decode.py`

**Interfaces:**
- Consumes: a raw record `{"dataset": str, "ts": str, "vin": str, "brand": str, "fields": dict[str, str], "captured_at": str|None}` (produced by `reader.py`).
- Produces: `decode(record: dict) -> DecodedPoint` where `DecodedPoint` is a dataclass with `vin: str`, `brand: str`, `time_utc: str` (ISO), and `fields: dict[str, float|int|bool]` (the InfluxDB field set). Consumed by `influx.py`.

- [ ] **Step 1: Write `tests/conftest.py` (a synthetic dataset fixture)**

```python
import pytest

@pytest.fixture
def raw_record():
    """A synthetic EU Data Act record (placeholder VIN, representative field values)."""
    return {
        "dataset": "20260828104222_WVWTELEMETRY00TES.zip",
        "ts": "20260828104222",
        "vin": "WVWTELEMETRY00TES",
        "brand": "volkswagen",
        "captured_at": "2026-08-28T10:13:58+00:00",
        "fields": {
            "mileage": "11942", "fuel_level_current_level": "79",
            "tank_current_level": "100", "cruising_range_combined": "630",
            "scr_range": "14500", "outside_temperature": "3011",
            "oil_level_actual_level": "37.5",
            "parking_brake": "1", "parking_lights": "2",
            "locked_state_front_left_door": "2", "open_state_front_left_door": "3",
            "locked_state_front_engine_bonnet": "3", "open_state_front_engine_bonnet": "3",
            "locked_state__rear_left_door": "2", "open_state_rear_left_door": "3",
            "tyre_pressure_actual_front_left": "1", "tyre_pressure_actual_rear_right": "1",
            "active_warnings_in_instrument_cluster_feff_filtered": "1",
            "short_term_data_mileage": "267", "short_term_data_travel_time": "268",
            "short_term_data_average_fuel_consumption": "67",
            "long_term_data_mileage": "707", "long_term_data_average_speed": "58",
            "long_term_data_average_fuel_consumption": "65",
        },
    }
```

- [ ] **Step 2: Write the failing test `tests/test_decode.py`**

```python
from vwtelemetry.decode import decode


def test_scales_and_enums(raw_record):
    d = decode(raw_record)
    assert d.vin == "WVWTELEMETRY00TES" and d.brand == "volkswagen"
    assert d.time_utc == "2026-08-28T10:13:58+00:00"
    f = d.fields
    assert f["mileage_km"] == 11942
    assert f["fuel_pct"] == 79 and f["adblue_pct"] == 100
    assert f["range_km"] == 630 and f["adblue_range_km"] == 14500
    assert round(f["outside_temp_c"], 1) == 28.0            # 3011 deci-K
    assert f["parking_brake"] is True                        # code 1
    assert f["trip_short_l_per_100km"] == 6.7                # 67 deci-L
    assert f["trip_long_avg_speed_kmh"] == 58


def test_door_aggregates(raw_record):
    f = decode(raw_record).fields
    assert f["door_front_left_locked"] is True               # code 2
    assert f["door_front_left_open"] is False                # code 3 = closed
    assert f["any_unlocked"] is True                         # bonnet code 3 = unlocked
    assert f["doors_locked"] >= 2


def test_service_overdue_and_warnings(raw_record):
    raw_record["fields"]["maintenance_interval_distance_until_inspection"] = "-28100"
    f = decode(raw_record).fields
    assert f["inspection_km_remaining"] == -28100
    assert f["warnings_active"] == 1


def test_tyres_all_ok(raw_record):
    assert decode(raw_record).fields["tyres_all_ok"] is True
```

- [ ] **Step 3: Run, expect FAIL** — `uv run pytest tests/test_decode.py -v`.

- [ ] **Step 4: Implement `vwtelemetry/decode.py`**

```python
"""Decode a raw EU Data Act dataset into a typed InfluxDB field set.

Enum codes are authoritative, from the vw_eu_data_act connector's decoders:
  lock 2=locked/3=unlocked · open 2=open/3=closed · lights 2=off/3-5=on
  parking_brake 0/1 · outside_temperature deci-Kelvin · *_consumption deci-L/100km
"""
from __future__ import annotations

from dataclasses import dataclass

DOOR_SUFFIXES = ["front_left_door", "front_right_door", "_rear_left_door", "rear_right_door",
                 "tailgate", "front_engine_bonnet"]


@dataclass(frozen=True)
class DecodedPoint:
    vin: str
    brand: str
    time_utc: str
    fields: dict[str, float | int | bool]


def _num(v: object) -> float | None:
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def decode(record: dict) -> DecodedPoint:
    src: dict[str, str] = record.get("fields", {})
    out: dict[str, float | int | bool] = {}

    def g(k: str) -> float | None:
        return _num(src.get(k))

    def put_int(name: str, key: str) -> None:
        v = g(key)
        if v is not None:
            out[name] = int(v)

    put_int("mileage_km", "mileage")
    put_int("fuel_pct", "fuel_level_current_level")
    put_int("adblue_pct", "tank_current_level")
    put_int("range_km", "cruising_range_combined")
    put_int("adblue_range_km", "scr_range")
    temp = g("outside_temperature")
    if temp is not None:
        out["outside_temp_c"] = round(temp / 10 - 273.15, 1)
    oil = g("oil_level_actual_level")
    if oil is not None:
        out["oil_level"] = oil
    pb = g("parking_brake")
    if pb in (0, 1):
        out["parking_brake"] = bool(pb)

    # doors: per-door bools + aggregates
    locked = opened = 0
    any_unlocked = False
    for suffix in DOOR_SUFFIXES:
        name = suffix.lstrip("_")
        lk = _num(src.get("locked_state_" + suffix, src.get("locked_state_" + name)))
        op = _num(src.get("open_state_" + name))
        if lk == 2:
            out["door_%s_locked" % name] = True
            locked += 1
        elif lk == 3:
            out["door_%s_locked" % name] = False
            if name != "front_engine_bonnet":       # bonnet unlocked is normal, ignore for 'any'
                any_unlocked = True
        if op == 2:
            out["door_%s_open" % name] = True
            opened += 1
        elif op == 3:
            out["door_%s_open" % name] = False
    out["doors_locked"] = locked
    out["doors_open"] = opened
    out["any_unlocked"] = any_unlocked

    # tyres: status codes; 1 across all actual_* = OK
    tp = [k for k in src if k.startswith("tyre_pressure_actual")]
    if tp:
        vals = {_num(src[k]) for k in tp}
        out["tyres_all_ok"] = vals <= {1.0}

    # service (negative = overdue)
    for name, key in (("inspection_km_remaining", "maintenance_interval_distance_until_inspection"),
                      ("oil_km_remaining", "maintenance_interval_distance_until_oil_change")):
        v = g(key)
        if v is not None:
            out[name] = int(v)
    w = g("active_warnings_in_instrument_cluster_feff_filtered")
    if w is not None:
        out["warnings_active"] = int(w)

    # trip computers
    stc = g("short_term_data_average_fuel_consumption")
    if stc is not None:
        out["trip_short_l_per_100km"] = round(stc / 10, 1)
    stk, stm = g("short_term_data_mileage"), g("short_term_data_travel_time")
    if stk is not None:
        out["trip_short_km"] = int(stk)
    if stk and stm:
        out["trip_short_avg_speed_kmh"] = round(stk / (stm / 60), 1)
    ltc = g("long_term_data_average_fuel_consumption")
    if ltc is not None:
        out["trip_long_l_per_100km"] = round(ltc / 10, 1)
    lts = g("long_term_data_average_speed")
    if lts is not None:
        out["trip_long_avg_speed_kmh"] = int(lts)

    return DecodedPoint(vin=record["vin"], brand=record.get("brand", "volkswagen"),
                        time_utc=record["captured_at"] or "", fields=out)
```

- [ ] **Step 5: Run, expect PASS** — `uv run pytest tests/test_decode.py -v`.

- [ ] **Step 6: Commit** — `git add vwtelemetry/decode.py tests/test_decode.py tests/conftest.py && git commit -m "feat(decode): raw dataset -> typed field set with enum/scale decoding"`

---

## Task 4: `reader.py` — EU Data Act client wrapper

**Files:**
- Create: `vwtelemetry/reader.py`
- Test: `tests/test_reader.py`

**Interfaces:**
- Consumes: `Config` (Task 2).
- Produces:
  - `class Reader` with `__init__(self, config: Config, client_factory=None)`.
  - `Reader.iter_new_records(self, seen: dict[str, set[str]]) -> Iterator[dict]` — logs in, discovers vehicles (honouring `config.vin_allowlist`), and yields one raw record per **content-bearing** dataset **not** already in `seen[vin]`. Each yielded record has keys `dataset`, `ts`, `vin`, `brand`, `captured_at`, `fields`. `captured_at` is derived from the max `timestampUtc` across the dataset's rows (ISO), else `None`.
  - `client_factory(user, pw, country) -> client` lets tests inject a fake `EudaApiClient` (default builds the real one). Consumed by `poll.py`.

- [ ] **Step 1: Write the failing test `tests/test_reader.py`**

```python
from vwtelemetry.config import Config
from vwtelemetry.reader import Reader


class FakeClient:
    def __init__(self, user, pw, country="DE", accept_terms_on_login=True):
        pass
    def ensure_login(self): pass
    def list_vehicles(self): return [{"vin": "WVWTELEMETRY00TES"}]
    def get_metadata(self, vin, request_type="partial"): return {"Identifier": "ID1"}
    def list_datasets(self, vin, ident, request_type="partial"):
        return [{"name": "20260828104222_WVWTELEMETRY00TES.zip"},
                {"name": "20260828101000_WVWTELEMETRY00TES_no_content_found.zip"}]
    def download_dataset(self, vin, ident, name, request_type="partial"):
        return {"Data": [{"dataFieldName": "mileage", "value": "11942",
                          "timestampUtc": "2026-08-28T10:13:58.000Z"}]}


def _cfg():
    return Config("u", "p", "volkswagen", "DE", [], "http://x", "home", "vehicle", "t")


def test_yields_only_new_content_datasets():
    r = Reader(_cfg(), client_factory=lambda u, p, country: FakeClient(u, p, country))
    recs = list(r.iter_new_records(seen={}))
    assert len(recs) == 1                                  # the no_content one is skipped
    rec = recs[0]
    assert rec["vin"] == "WVWTELEMETRY00TES" and rec["fields"]["mileage"] == "11942"
    assert rec["captured_at"].startswith("2026-08-28T10:13:58")


def test_skips_already_seen():
    r = Reader(_cfg(), client_factory=lambda u, p, country: FakeClient(u, p, country))
    seen = {"WVWTELEMETRY00TES": {"20260828104222_WVWTELEMETRY00TES.zip"}}
    assert list(r.iter_new_records(seen=seen)) == []


def test_vin_allowlist_filters():
    cfg = Config("u", "p", "volkswagen", "DE", ["OTHERVIN"], "http://x", "home", "vehicle", "t")
    r = Reader(cfg, client_factory=lambda u, p, country: FakeClient(u, p, country))
    assert list(r.iter_new_records(seen={})) == []          # our VIN not in allowlist
```

- [ ] **Step 2: Run, expect FAIL** — `uv run pytest tests/test_reader.py -v`.

- [ ] **Step 3: Implement `vwtelemetry/reader.py`**

```python
"""Read the VW EU Data Act portal via the low-level EudaApiClient (NOT CarConnectivity.fetch_all,
which merges all datasets in one blocking call and hangs). Auto-discovers all vehicles; yields one
raw record per content-bearing dataset not already ingested."""
from __future__ import annotations

from collections.abc import Callable, Iterator

from .config import Config


def _default_factory(user: str, pw: str, country: str):
    from carconnectivity_connectors.vw_eu_data_act.client import EudaApiClient
    return EudaApiClient(user, pw, country=country, accept_terms_on_login=True)


class Reader:
    def __init__(self, config: Config, client_factory: Callable | None = None) -> None:
        self._cfg = config
        self._factory = client_factory or _default_factory

    def iter_new_records(self, seen: dict[str, set[str]]) -> Iterator[dict]:
        c = self._factory(self._cfg.vwid_user, self._cfg.vwid_password, self._cfg.country)
        c.ensure_login()
        for veh in c.list_vehicles():
            vin = veh.get("vin")
            if not vin or (self._cfg.vin_allowlist and vin not in self._cfg.vin_allowlist):
                continue
            ident = c.get_metadata(vin, request_type="partial").get("Identifier")
            if not ident:
                continue
            already = seen.get(vin, set())
            for d in c.list_datasets(vin, ident, request_type="partial"):
                name = d.get("name", "")
                if not name or "no_content_found" in name or name in already:
                    continue
                data = c.download_dataset(vin, ident, name, request_type="partial")
                rows = data.get("Data", []) if isinstance(data, dict) else []
                fields = {r.get("dataFieldName"): r.get("value") for r in rows
                          if r.get("dataFieldName")}
                tss = [r.get("timestampUtc") for r in rows if r.get("timestampUtc")]
                captured = max(tss).replace("Z", "+00:00") if tss else None
                yield {"dataset": name, "ts": name.split("_", 1)[0], "vin": vin,
                       "brand": self._cfg.brand, "captured_at": captured, "fields": fields}
```

- [ ] **Step 4: Run, expect PASS** — `uv run pytest tests/test_reader.py -v`.

- [ ] **Step 5: Commit** — `git add vwtelemetry/reader.py tests/test_reader.py && git commit -m "feat(reader): low-level EudaApiClient wrapper, dedupe + allowlist"`

---

## Task 5: `influx.py` — decoded record → InfluxDB points

**Files:**
- Create: `vwtelemetry/influx.py`
- Test: `tests/test_influx.py`

**Interfaces:**
- Consumes: `DecodedPoint` (Task 3), `Config` (Task 2).
- Produces:
  - `to_point(decoded: DecodedPoint) -> Point` — one `influxdb_client.Point` in measurement `vehicle`, tags `vin`/`brand`/`source=eu_data_act`, fields from `decoded.fields`, time = `decoded.time_utc`.
  - `write_points(config: Config, points: list, write_api_factory=None) -> int` — writes and returns the count; `write_api_factory` lets tests inject a fake. Consumed by `poll.py`.

- [ ] **Step 1: Write the failing test `tests/test_influx.py`**

```python
from vwtelemetry.config import Config
from vwtelemetry.decode import DecodedPoint
from vwtelemetry.influx import to_point, write_points


def _decoded():
    return DecodedPoint(vin="WVWTELEMETRY00TES", brand="volkswagen",
                        time_utc="2026-08-28T10:13:58+00:00",
                        fields={"mileage_km": 11942, "any_unlocked": False, "outside_temp_c": 28.0})


def test_to_point_shape():
    line = to_point(_decoded()).to_line_protocol()
    assert line.startswith("vehicle,")
    assert "vin=WVWTELEMETRY00TES" in line and "brand=volkswagen" in line
    assert "source=eu_data_act" in line and "mileage_km=11942" in line


def test_write_points_uses_bucket_and_counts():
    captured = {}
    class FakeWrite:
        def write(self, bucket, org, record):
            captured["bucket"] = bucket; captured["org"] = org; captured["n"] = len(record)
    cfg = Config("u", "p", "volkswagen", "DE", [], "http://x", "home", "vehicle", "t")
    n = write_points(cfg, [to_point(_decoded())], write_api_factory=lambda c: FakeWrite())
    assert n == 1 and captured["bucket"] == "vehicle" and captured["org"] == "home"
```

- [ ] **Step 2: Run, expect FAIL** — `uv run pytest tests/test_influx.py -v`.

- [ ] **Step 3: Implement `vwtelemetry/influx.py`**

```python
"""Build and write InfluxDB points for decoded vehicle telemetry (bucket 'vehicle')."""
from __future__ import annotations

from collections.abc import Callable

from .config import Config
from .decode import DecodedPoint


def to_point(decoded: DecodedPoint):
    from influxdb_client import Point
    p = (Point("vehicle").tag("vin", decoded.vin).tag("brand", decoded.brand)
         .tag("source", "eu_data_act"))
    for k, v in decoded.fields.items():
        p = p.field(k, v)
    if decoded.time_utc:
        p = p.time(decoded.time_utc)
    return p


def _default_write_api(config: Config):
    from influxdb_client import InfluxDBClient
    from influxdb_client.client.write_api import SYNCHRONOUS
    client = InfluxDBClient(url=config.influx_url, token=config.influx_token, org=config.influx_org)
    return client.write_api(write_options=SYNCHRONOUS)


def write_points(config: Config, points: list, write_api_factory: Callable | None = None) -> int:
    if not points:
        return 0
    api = (write_api_factory or _default_write_api)(config)
    api.write(bucket=config.influx_bucket, org=config.influx_org, record=points)
    return len(points)
```

- [ ] **Step 4: Run, expect PASS** — `uv run pytest tests/test_influx.py -v`.

- [ ] **Step 5: Commit** — `git add vwtelemetry/influx.py tests/test_influx.py && git commit -m "feat(influx): decoded record -> Points, write to bucket vehicle"`

---

## Task 6: `poll.py` — oneshot orchestration + watermark

**Files:**
- Create: `vwtelemetry/poll.py`
- Test: `tests/test_poll.py`

**Interfaces:**
- Consumes: `Config`, `Reader`, `decode`, `to_point`/`write_points`.
- Produces: `run(config, reader=None, write=None, state_dir=None) -> int` (returns points written); loads/saves the per-VIN watermark under `state_dir` (default `./state`); a `main()` entrypoint (`python -m vwtelemetry.poll`).

- [ ] **Step 1: Write the failing test `tests/test_poll.py`**

```python
from vwtelemetry.config import Config
from vwtelemetry.poll import run


class FakeReader:
    def __init__(self, recs): self._recs = recs
    def iter_new_records(self, seen):
        return (r for r in self._recs if r["dataset"] not in seen.get(r["vin"], set()))


def _cfg():
    return Config("u", "p", "volkswagen", "DE", [], "http://x", "home", "vehicle", "t")


def _rec(name):
    return {"dataset": name, "ts": name[:14], "vin": "WVWTELEMETRY00TES", "brand": "volkswagen",
            "captured_at": "2026-08-28T10:13:58+00:00", "fields": {"mileage": "11942"}}


def test_writes_and_persists_watermark(tmp_path):
    written = []
    n = run(_cfg(), reader=FakeReader([_rec("20260828104222_WVWTELEMETRY00TES.zip")]),
            write=lambda cfg, pts: written.extend(pts) or len(pts), state_dir=str(tmp_path))
    assert n == 1 and len(written) == 1
    # second run: same dataset is now in the watermark -> nothing written
    n2 = run(_cfg(), reader=FakeReader([_rec("20260828104222_WVWTELEMETRY00TES.zip")]),
             write=lambda cfg, pts: len(pts), state_dir=str(tmp_path))
    assert n2 == 0
```

- [ ] **Step 2: Run, expect FAIL** — `uv run pytest tests/test_poll.py -v`.

- [ ] **Step 3: Implement `vwtelemetry/poll.py`**

```python
"""Oneshot: pull new datasets, decode, write to InfluxDB, advance the per-VIN watermark."""
from __future__ import annotations

import json
import os
from collections.abc import Callable

from .config import Config
from .decode import decode
from .influx import to_point, write_points
from .reader import Reader

STATE_DIR_DEFAULT = os.environ.get("VW_STATE_DIR", "state")


def _load_seen(state_dir: str) -> dict[str, set[str]]:
    path = os.path.join(state_dir, "watermark.json")
    if not os.path.isfile(path):
        return {}
    with open(path) as f:
        return {k: set(v) for k, v in json.load(f).items()}


def _save_seen(state_dir: str, seen: dict[str, set[str]]) -> None:
    os.makedirs(state_dir, exist_ok=True)
    with open(os.path.join(state_dir, "watermark.json"), "w") as f:
        json.dump({k: sorted(v) for k, v in seen.items()}, f)


def run(config: Config, reader: object | None = None, write: Callable | None = None,
        state_dir: str | None = None) -> int:
    state_dir = state_dir or STATE_DIR_DEFAULT
    reader = reader or Reader(config)
    write = write or (lambda cfg, pts: write_points(cfg, pts))
    seen = _load_seen(state_dir)
    points, touched = [], []
    for rec in reader.iter_new_records(seen):          # type: ignore[union-attr]
        points.append(to_point(decode(rec)))
        touched.append((rec["vin"], rec["dataset"]))
    n = write(config, points) if points else 0
    for vin, name in touched:
        seen.setdefault(vin, set()).add(name)
    if touched:
        _save_seen(state_dir, seen)
    return n


def main() -> None:
    cfg = Config.from_env()
    n = run(cfg)
    print("vw-telemetry: wrote %d point(s)" % n, flush=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run, expect PASS** — `uv run pytest tests/test_poll.py -v`.

- [ ] **Step 5: Run the whole suite + quality gates**

Run: `uv run ruff check . && uv run mypy vwtelemetry && uv run pytest -v`
Expected: all green.

- [ ] **Step 6: Commit** — `git add vwtelemetry/poll.py tests/test_poll.py && git commit -m "feat(poll): oneshot orchestration + per-VIN watermark"`

---

## Task 7: Deploy artifacts (systemd timer, bucket setup, env example)

**Files:**
- Create: `deploy/vw-telemetry.service`, `deploy/vw-telemetry.timer`, `deploy/setup-bucket.sh`, `deploy/vw-telemetry.env.example`
- Test: `tests/test_deploy_artifacts.py`

**Interfaces:**
- Produces: installable systemd units + a bucket-setup script + the config template. No runtime interface.

- [ ] **Step 1: Write `deploy/vw-telemetry.env.example`**

```bash
# Copy to /etc/buspi/vw-telemetry.env (root, chmod 0600). NEVER commit a filled-in copy.
VWID_USER=you@example.com
VWID_PASSWORD=
VW_BRAND=volkswagen        # volkswagen|audi|skoda|seat|cupra|bentley
VW_COUNTRY=DE
VW_VIN_ALLOWLIST=          # blank = all vehicles on the account
INFLUX_URL=http://localhost:8086
INFLUX_ORG=home
INFLUX_BUCKET=vehicle
INFLUX_TOKEN=
```

- [ ] **Step 2: Write `deploy/vw-telemetry.service`**

```ini
[Unit]
Description=vw-telemetry — EU Data Act -> InfluxDB (oneshot)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=pi
WorkingDirectory=/home/pi/vw-telemetry
EnvironmentFile=/etc/buspi/vw-telemetry.env
Environment=VW_STATE_DIR=/home/pi/vw-telemetry/state
ExecStart=/home/pi/vw-telemetry/.venv/bin/python -m vwtelemetry.poll
```

- [ ] **Step 3: Write `deploy/vw-telemetry.timer`**

```ini
[Unit]
Description=Run vw-telemetry every 15 minutes

[Timer]
OnBootSec=3min
OnUnitActiveSec=15min
Persistent=true

[Install]
WantedBy=timers.target
```

- [ ] **Step 4: Write `deploy/setup-bucket.sh`**

```bash
#!/usr/bin/env bash
# Create the 'vehicle' bucket + a write-scoped token in the existing InfluxDB. Idempotent.
# Requires the influx CLI configured (or run on buspi where it is). ORG defaults to 'home'.
set -euo pipefail
ORG="${INFLUX_ORG:-home}"
BUCKET="${INFLUX_BUCKET:-vehicle}"
RETENTION="${INFLUX_RETENTION:-0}"   # 0 = infinite
influx bucket list --org "$ORG" --name "$BUCKET" >/dev/null 2>&1 \
  || influx bucket create --org "$ORG" --name "$BUCKET" --retention "$RETENTION"
echo "Bucket '$BUCKET' ready in org '$ORG'."
echo "Create a write-scoped token (copy into /etc/buspi/vw-telemetry.env as INFLUX_TOKEN):"
echo "  influx auth create --org $ORG --write-bucket \$(influx bucket list --org $ORG --name $BUCKET --hide-headers | awk '{print \$1}') --description vw-telemetry"
```

- [ ] **Step 5: Write `tests/test_deploy_artifacts.py`**

```python
from pathlib import Path

DEPLOY = Path(__file__).resolve().parent.parent / "deploy"


def test_service_runs_the_module():
    s = (DEPLOY / "vw-telemetry.service").read_text()
    assert "Type=oneshot" in s and "-m vwtelemetry.poll" in s
    assert "EnvironmentFile=/etc/buspi/vw-telemetry.env" in s


def test_timer_is_15_min():
    assert "OnUnitActiveSec=15min" in (DEPLOY / "vw-telemetry.timer").read_text()


def test_env_example_has_no_secrets():
    t = (DEPLOY / "vw-telemetry.env.example").read_text()
    assert "VWID_PASSWORD=\n" in t and "INFLUX_TOKEN=\n" in t   # empty placeholders
```

- [ ] **Step 6: Run, expect PASS** — `uv run pytest tests/test_deploy_artifacts.py -v`; then `chmod +x deploy/setup-bucket.sh`.

- [ ] **Step 7: Commit** — `git add deploy tests/test_deploy_artifacts.py && git commit -m "feat(deploy): systemd oneshot timer, bucket setup, env template"`

---

## Task 8: Grafana datasource + dashboard + push

**Files:**
- Create: `deploy/grafana-datasource.yaml`, `deploy/grafana-vehicle.json`, `deploy/push_dashboard.py`
- Test: `tests/test_dashboard.py`

**Interfaces:**
- Produces: a provisioned InfluxDB datasource (Flux, bucket `vehicle`), a dashboard JSON with a `$vin` template variable and panels reading measurement `vehicle`, and a push script.

- [ ] **Step 1: Write `deploy/grafana-datasource.yaml`**

```yaml
apiVersion: 1
datasources:
  - name: vehicle-influx
    type: influxdb
    access: proxy
    url: http://localhost:8086
    jsonData:
      version: Flux
      organization: home
      defaultBucket: vehicle
    secureJsonData:
      token: ${INFLUX_TOKEN}      # provisioned from env; not committed
```

- [ ] **Step 2: Write a minimal `deploy/grafana-vehicle.json`**

A dashboard with a `$vin` template variable and at least: a mileage timeseries, a fuel gauge, and a service-overdue stat. Keep it minimal-but-valid so CI/JSON checks pass; panels can grow later.

```json
{
  "title": "Vehicle (EU Data Act)",
  "uid": "vw-telemetry",
  "schemaVersion": 39,
  "templating": {"list": [
    {"name": "vin", "type": "query", "datasource": "vehicle-influx",
     "query": "import \"influxdata/influxdb/schema\"\nschema.tagValues(bucket: \"vehicle\", tag: \"vin\")"}
  ]},
  "panels": [
    {"id": 1, "title": "Odometer", "type": "timeseries", "datasource": "vehicle-influx",
     "targets": [{"query": "from(bucket:\"vehicle\") |> range(start: v.timeRangeStart) |> filter(fn:(r)=> r._measurement==\"vehicle\" and r.vin==\"${vin}\" and r._field==\"mileage_km\")"}]},
    {"id": 2, "title": "Fuel %", "type": "gauge", "datasource": "vehicle-influx",
     "targets": [{"query": "from(bucket:\"vehicle\") |> range(start: -1d) |> filter(fn:(r)=> r._measurement==\"vehicle\" and r.vin==\"${vin}\" and r._field==\"fuel_pct\") |> last()"}]},
    {"id": 3, "title": "Inspection km remaining", "type": "stat", "datasource": "vehicle-influx",
     "fieldConfig": {"defaults": {"thresholds": {"steps": [{"color":"red","value":null},{"color":"green","value":0}]}}},
     "targets": [{"query": "from(bucket:\"vehicle\") |> range(start:-1d) |> filter(fn:(r)=> r._measurement==\"vehicle\" and r.vin==\"${vin}\" and r._field==\"inspection_km_remaining\") |> last()"}]}
  ]
}
```

- [ ] **Step 3: Write `deploy/push_dashboard.py`**

```python
"""Push grafana-vehicle.json to a Grafana instance via its HTTP API.
Usage: python deploy/push_dashboard.py --url http://localhost:3000 --token <grafana-token>"""
from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path


def push(url: str, token: str, dashboard_path: str) -> int:
    dash = json.loads(Path(dashboard_path).read_text())
    body = json.dumps({"dashboard": dash, "overwrite": True}).encode()
    req = urllib.request.Request(url.rstrip("/") + "/api/dashboards/db", data=body,
                                 headers={"Authorization": "Bearer " + token,
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:3000")
    ap.add_argument("--token", required=True)
    ap.add_argument("--dashboard", default=str(Path(__file__).parent / "grafana-vehicle.json"))
    a = ap.parse_args()
    print("HTTP", push(a.url, a.token, a.dashboard))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Write `tests/test_dashboard.py`**

```python
import json
from pathlib import Path

DEPLOY = Path(__file__).resolve().parent.parent / "deploy"


def test_dashboard_valid_json_with_vin_variable():
    d = json.loads((DEPLOY / "grafana-vehicle.json").read_text())
    assert d["uid"] == "vw-telemetry"
    names = [v["name"] for v in d["templating"]["list"]]
    assert "vin" in names
    assert any(p["type"] == "timeseries" for p in d["panels"])


def test_datasource_uses_vehicle_bucket():
    y = (DEPLOY / "grafana-datasource.yaml").read_text()
    assert "defaultBucket: vehicle" in y and "version: Flux" in y
```

- [ ] **Step 5: Run, expect PASS** — `uv run pytest tests/test_dashboard.py -v`.

- [ ] **Step 6: Commit** — `git add deploy/grafana-datasource.yaml deploy/grafana-vehicle.json deploy/push_dashboard.py tests/test_dashboard.py && git commit -m "feat(grafana): datasource + dashboard (\$vin var) + push script"`

---

## Task 9: Documentation (Diátaxis + MkDocs Material + mkdocstrings)

**Files:**
- Create: `mkdocs.yml`, `docs/tutorials/first-vehicle.md`, `docs/how-to/deploy-buspi.md`, `docs/how-to/add-a-field.md`, `docs/reference/influx-schema.md`, `docs/reference/config.md`, `docs/reference/api.md`
- (exists: `docs/explanation/design.md`)

**Interfaces:** none (docs). CI's `mkdocs build --strict` must pass.

- [ ] **Step 1: Write `mkdocs.yml`**

```yaml
site_name: vw-telemetry
theme:
  name: material
plugins:
  - search
  - mkdocstrings:
      handlers: {python: {paths: [.]}}
nav:
  - Home: index.md
  - Tutorials: [tutorials/first-vehicle.md]
  - How-to: [how-to/deploy-buspi.md, how-to/add-a-field.md]
  - Reference: [reference/influx-schema.md, reference/config.md, reference/api.md]
  - Explanation: [explanation/design.md]
```

- [ ] **Step 2: Create `docs/index.md`** (copy the README intro; one paragraph + the Diátaxis map).

- [ ] **Step 3: Write the four quadrant pages** — real content, no placeholders:
  - `tutorials/first-vehicle.md`: enable the 15-min "All data" request in the portal → set `.env` → `python -m vwtelemetry.poll` → see points in Influx → import the dashboard.
  - `how-to/deploy-buspi.md`: clone, `uv sync`, `/etc/buspi/vw-telemetry.env`, `setup-bucket.sh`, enable the timer, push the dashboard.
  - `how-to/add-a-field.md`: add a mapping in `decode.py` + a test in `test_decode.py` + a dashboard panel.
  - `reference/influx-schema.md`: the measurement/tags/fields table (from the spec §5).
  - `reference/config.md`: the env table (from the spec §4).
  - `reference/api.md`: `::: vwtelemetry.decode` / `::: vwtelemetry.reader` / `::: vwtelemetry.poll` (mkdocstrings auto-render).

- [ ] **Step 4: Build the docs** — `uv run mkdocs build --strict`; fix any broken nav/refs.

- [ ] **Step 5: Commit** — `git add mkdocs.yml docs && git commit -m "docs: Diátaxis structure (MkDocs Material + mkdocstrings)"`

- [ ] **Step 6: Final full gate** — `uv run ruff check . && uv run ruff format --check . && uv run mypy vwtelemetry && uv run pytest -v && uv run mkdocs build --strict`; expect all green. Push.

---

## Deploy & verify on buspi (after the plan is built and green)

Not a code task — the on-device rollout (do once, with the owner):
1. `git clone` under `/home/pi/vw-telemetry`; `uv sync`.
2. `sudo` write `/etc/buspi/vw-telemetry.env` (0600) with creds + a bucket-scoped `INFLUX_TOKEN`.
3. `bash deploy/setup-bucket.sh` (create bucket + token).
4. `sudo cp deploy/vw-telemetry.{service,timer} /etc/systemd/system/ && sudo systemctl enable --now vw-telemetry.timer`.
5. `python deploy/push_dashboard.py --token <grafana-token>` (Pi Grafana).
6. Verify: `systemctl status vw-telemetry.service`, points land in bucket `vehicle`, dashboard shows the vehicle.

---

## Self-Review

**Spec coverage:** §1 purpose → Task 1–9; §3 architecture → Tasks 2–6; §4 config → Task 2; §5 InfluxDB schema → Tasks 3+5; §6 Grafana → Task 8; §7 CI → Task 1; §8 docs → Task 9; §9 limitations → documented in docs (Task 9); §10 deploy → Task 7 + the buspi rollout section. All covered.

**Placeholder scan:** every code step contains real, runnable code; no TBD/TODO. Task 9 Step 3 lists page contents rather than full prose — acceptable (docs prose, not code), with the exact source sections named.

**Type consistency:** `Config` fields/order match across Tasks 2/4/5/6. `DecodedPoint(vin, brand, time_utc, fields)` consistent in Tasks 3/5. `Reader.iter_new_records(seen)` and record keys (`dataset/ts/vin/brand/captured_at/fields`) consistent across Tasks 4/6. `to_point`/`write_points` signatures consistent in Tasks 5/6. Placeholder VIN `WVWTELEMETRY00TES` consistent in the guard, conftest, and all tests.
