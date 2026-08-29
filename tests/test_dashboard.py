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
