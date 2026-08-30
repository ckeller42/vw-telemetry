"""Build and write InfluxDB points for decoded vehicle telemetry (bucket 'vehicle')."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .config import Config
from .decode import DecodedPoint


def to_point(decoded: DecodedPoint) -> Any:
    from influxdb_client import Point  # type: ignore[attr-defined]

    p = (
        Point("vehicle")  # type: ignore[no-untyped-call]
        .tag("vin", decoded.vin)
        .tag("brand", decoded.brand)
        .tag("source", "eu_data_act")
    )
    for k, v in decoded.fields.items():
        p = p.field(k, v)
    if decoded.time_utc:
        p = p.time(decoded.time_utc)
    return p


def _default_write_api(config: Config) -> Any:
    from influxdb_client import InfluxDBClient  # type: ignore[attr-defined]
    from influxdb_client.client.write_api import SYNCHRONOUS

    client = InfluxDBClient(url=config.influx_url, token=config.influx_token, org=config.influx_org)
    return client.write_api(write_options=SYNCHRONOUS)


def write_points(
    config: Config, points: list[Any], write_api_factory: Callable[..., Any] | None = None
) -> int:
    if not points:
        return 0
    api = (write_api_factory or _default_write_api)(config)
    api.write(bucket=config.influx_bucket, org=config.influx_org, record=points)
    return len(points)
