# How to: backfill history from an archive

The live poller ([`vwtelemetry.poll`](../reference/api.md)) only sees the portal's rolling window —
the EU Data Act `partial` feed keeps just the most recent datasets, and older ones roll off. If you
have been capturing datasets into an **append-only JSONL store** (one dataset per line), you can
replay that store into InfluxDB to backfill history at the correct historical timestamps.

## The archive format

`import_archive` reads a JSONL file where each non-blank line is one dataset record:

```json
{"dataset": "20260830164321_<VIN>.zip", "ts": "20260830164321", "vin": "<VIN>", "fields": {"mileage": "12337", "...": "..."}}
```

- `ts` is the dataset's `YYYYMMDDHHMMSS` UTC stamp. `import_archive` derives `captured_at` from it,
  so every point lands at the **vehicle's real measurement time**, not the time you run the import.
- `brand` and `captured_at` are optional — `brand` defaults to `volkswagen`, and `captured_at` is
  filled from `ts` when absent.
- `fields` is the flat `dataFieldName -> value` map, exactly as the live [`reader`](../reference/api.md)
  builds it. Only fields the [decoder](add-a-field.md) understands are written; the rest are ignored.

## Dry-run first

Decode every record without touching InfluxDB (needs no credentials):

```bash
uv run python -m vwtelemetry.import_archive path/to/telemetry.jsonl --dry-run
```

It prints how many records decoded cleanly:

```
vw-telemetry import (dry-run): 219 record(s) decoded OK, 0 written
```

A record that fails to decode raises immediately, pointing at the offending line — fix or drop it
before the real run.

## Import

```bash
uv run python -m vwtelemetry.import_archive path/to/telemetry.jsonl
```

This decodes each record and writes it to the `vehicle` bucket, honouring `VW_VIN_ALLOWLIST` (blank
= all vehicles) and defaulting each record's `brand` to `VW_BRAND`, the same as the live poller.
Backfill writes to InfluxDB only and never contacts the portal, so it needs the **InfluxDB settings
only** — `INFLUX_URL`, `INFLUX_ORG`, `INFLUX_BUCKET`, `INFLUX_TOKEN` (plus `VW_BRAND` if your feed
isn't the `volkswagen` default) — and **no VW-ID credentials**. Run it wherever those are set.

**Idempotent:** points are timestamped at the vehicle's own clock, so re-importing the same archive
overwrites each point in place rather than duplicating it. The live 15-minute timer and a one-time
backfill write to the same coordinate space and cannot double-count. Run the backfill once, then let
the timer carry history forward.

## Verify

```bash
influx query 'from(bucket:"vehicle") |> range(start:-30d) |> count()' --org home
```

The count should jump by roughly the number of records in your archive, and the Grafana timeline
should now extend back to the archive's earliest dataset.
