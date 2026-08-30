"""Oneshot: pull new datasets, decode, write to InfluxDB, advance the per-VIN watermark."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any, cast

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


def run(
    config: Config,
    reader: object | None = None,
    write: Callable[[Config, list[Any]], int] | None = None,
    state_dir: str | None = None,
) -> int:
    state_dir = state_dir or STATE_DIR_DEFAULT
    reader = reader or Reader(config)
    write = write or (lambda cfg, pts: write_points(cfg, pts))
    seen = _load_seen(state_dir)
    points, touched = [], []
    for rec in cast(Reader, reader).iter_new_records(seen):
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
    print(f"vw-telemetry: wrote {n} point(s)", flush=True)


if __name__ == "__main__":
    main()
