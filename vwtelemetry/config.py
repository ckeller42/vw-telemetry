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
    def from_env(cls) -> Config:
        _load_dotenv()
        missing = [
            k for k in ("VWID_USER", "VWID_PASSWORD", "INFLUX_TOKEN") if not os.environ.get(k)
        ]
        if missing:
            sys.exit(
                f"Missing required env: {', '.join(missing)} (see deploy/vw-telemetry.env.example)"
            )
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
