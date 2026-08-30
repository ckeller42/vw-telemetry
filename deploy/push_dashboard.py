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
    req = urllib.request.Request(  # noqa: S310
        url.rstrip("/") + "/api/dashboards/db",
        data=body,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310
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
