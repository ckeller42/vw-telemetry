"""Replay an archived JSONL telemetry store into InfluxDB (historic backfill).

The live poller (:mod:`vwtelemetry.poll`) only sees the portal's rolling window. To load history
captured earlier into an append-only JSONL store, replay it here. Each line is one dataset record::

    {"dataset": "...", "ts": "YYYYMMDDHHMMSS", "vin": "...", "fields": {name: value, ...}}

``brand`` and ``captured_at`` are optional: ``captured_at`` is derived from ``ts`` (the portal
stamps datasets in UTC) so every point is timestamped at the vehicle's real measurement time, and
``brand`` defaults to ``volkswagen``. Idempotent: identical ``(vin, time, field)`` points overwrite
in InfluxDB, so re-running the import never double-counts.

    python -m vwtelemetry.import_archive path/to/telemetry.jsonl
    python -m vwtelemetry.import_archive path/to/telemetry.jsonl --dry-run
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Iterable, Iterator
from typing import Any

from .config import Config
from .decode import decode
from .influx import to_point, write_points


def _ts_to_iso(ts: str) -> str:
    """``20260830164321`` -> ``2026-08-30T16:43:21+00:00`` (portal stamps are UTC)."""
    if len(ts) != 14 or not ts.isdigit():
        raise ValueError(f"bad ts {ts!r}: expected 14 digits YYYYMMDDHHMMSS")
    return f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}T{ts[8:10]}:{ts[10:12]}:{ts[12:14]}+00:00"


def normalize(record: dict[str, Any]) -> dict[str, Any]:
    """Fill ``captured_at`` (from ``ts``) and ``brand`` so an archive record decodes."""
    rec = dict(record)
    if not rec.get("captured_at"):
        rec["captured_at"] = _ts_to_iso(str(rec["ts"]))
    rec.setdefault("brand", "volkswagen")
    return rec


def iter_records(path: str) -> Iterator[dict[str, Any]]:
    """Yield one dict per non-blank JSONL line in ``path``."""
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def import_records(
    config: Config,
    records: Iterable[dict[str, Any]],
    write: Callable[[Config, list[Any]], int] | None = None,
) -> int:
    """Decode ``records`` and write them to InfluxDB; return the point count written.

    Honours ``config.vin_allowlist`` (blank = all vehicles), matching the live poller.
    """
    do_write = write or write_points
    allow = set(config.vin_allowlist)
    points = [
        to_point(decode(normalize(rec))) for rec in records if not allow or rec.get("vin") in allow
    ]
    return do_write(config, points) if points else 0


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill InfluxDB from an archived telemetry JSONL.")
    ap.add_argument("path", help="JSONL file of archived datasets")
    ap.add_argument("--dry-run", action="store_true", help="decode only; write nothing, no creds")
    a = ap.parse_args()
    if a.dry_run:
        n = 0
        for rec in iter_records(a.path):
            decode(normalize(rec))  # raises on a malformed record, pointing at the bad line
            n += 1
        print(f"vw-telemetry import (dry-run): {n} record(s) decoded OK, 0 written", flush=True)
        return
    n = import_records(Config.from_env(), iter_records(a.path))
    print(f"vw-telemetry import: wrote {n} point(s)", flush=True)


if __name__ == "__main__":
    main()
