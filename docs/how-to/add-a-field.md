# How to: add a new field

The EU Data Act portal exposes far more `dataFieldName` keys than vw-telemetry currently decodes.
Adding one is a three-step, test-driven change: decode it, test it, show it.

## 1. Add the mapping in `decode.py`

Each dataset arrives as a flat `dict[str, str]` of `dataFieldName -> value` (see
`vwtelemetry/reader.py`, which builds `record["fields"]` from the downloaded dataset's rows).
`vwtelemetry.decode.decode()` reads named keys out of that dict with the `g()` / `put_int()`
helpers and writes typed, unit-suffixed output fields.

For a simple numeric passthrough, follow the pattern already used for mileage/fuel/range:

```python
put_int("my_new_field_unit", "the_portal_data_field_name")
```

For a field that needs a scale or enum conversion (like `outside_temperature`, which arrives in
deci-Kelvin and is converted to Celsius), read it with `g()` and convert explicitly:

```python
raw = g("some_portal_field")
if raw is not None:
    out["my_new_field_unit"] = round(raw / 10, 1)  # e.g. deci-units -> units
```

Conventions to follow:

- **Name the output field with its unit** (`_km`, `_pct`, `_c`, `_kmh`, `_l_per_100km`) so it's
  self-documenting in Grafana and InfluxDB, matching the existing fields listed in
  [the InfluxDB schema reference](../reference/influx-schema.md).
- **Guard on `None`** — only add the key to `out` if the source value was present and parsed
  (`g()` returns `None` for missing/unparseable values), so a dataset that doesn't carry the field
  doesn't write a spurious `0` or `null`.
- **Booleans from enum codes** — VW's field enums aren't `0`/`1`; e.g. locked state is `2 = locked`
  / `3 = unlocked`, open state is `2 = open` / `3 = closed`. Check the real code values (the
  module docstring at the top of `decode.py` lists the known code values) rather
  than assuming a truthy/falsy mapping — an inverted boolean is a classic silent bug here.

## 2. Add a test in `tests/test_decode.py`

The `raw_record` fixture in `tests/conftest.py` provides a synthetic dataset (VIN
`WVWTELEMETRY00TES`) with a representative set of `dataFieldName` values. Add your new field's
raw key/value to the fixture if it isn't already present, then assert the decoded output:

```python
def test_my_new_field(raw_record):
    f = decode(raw_record).fields
    assert f["my_new_field_unit"] == <expected decoded value>
```

Run it:

```bash
uv run pytest tests/test_decode.py -v
```

## 3. Add a dashboard panel

Add a panel to `deploy/grafana-vehicle.json` that queries the `vehicle` measurement's new field
from the `vehicle` bucket, filtered by the `$vin` template variable, following the style of the
existing panels (a timeline for continuous values, a stat panel for a single current value, a
gauge for a bounded percentage). Then push the updated dashboard:

```bash
uv run python deploy/push_dashboard.py --url http://localhost:3000 --token <grafana-api-token>
```

See [Deploy to buspi](deploy-buspi.md#5-push-the-grafana-dashboard) for the full push step, and
[the InfluxDB schema reference](../reference/influx-schema.md) for how the existing fields are
grouped (continuous / per-door booleans / aggregates / service).

## Before committing

Run the full gate — the new field must not break decoding of records that don't carry it, and the
field name must not collide with an existing one:

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy vwtelemetry && uv run pytest -q
```
