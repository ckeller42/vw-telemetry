from vwtelemetry.config import Config
from vwtelemetry.decode import DecodedPoint
from vwtelemetry.influx import to_point, write_points


def _decoded():
    return DecodedPoint(
        vin="WVWTELEMETRY00TES",
        brand="volkswagen",
        time_utc="2026-08-28T10:13:58+00:00",
        fields={"mileage_km": 11942, "any_unlocked": False, "outside_temp_c": 28.0},
    )


def test_to_point_shape():
    line = to_point(_decoded()).to_line_protocol()
    assert line.startswith("vehicle,")
    assert "vin=WVWTELEMETRY00TES" in line and "brand=volkswagen" in line
    assert "source=eu_data_act" in line and "mileage_km=11942" in line


def test_write_points_uses_bucket_and_counts():
    captured = {}

    class FakeWrite:
        def write(self, bucket, org, record):
            captured["bucket"] = bucket
            captured["org"] = org
            captured["n"] = len(record)

    cfg = Config("u", "p", "volkswagen", "DE", [], "http://x", "home", "vehicle", "t")
    n = write_points(cfg, [to_point(_decoded())], write_api_factory=lambda c: FakeWrite())
    assert n == 1 and captured["bucket"] == "vehicle" and captured["org"] == "home"
