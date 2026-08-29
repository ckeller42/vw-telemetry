import json
import re
from pathlib import Path

from vwtelemetry.decode import decode

DEPLOY = Path(__file__).resolve().parent.parent / "deploy"

# A raw record exercising EVERY input field that produces an output, so decode() yields the full
# set of possible field names. Used to prove the dashboard only queries fields the decoder emits.
_FULL_RECORD = {
    "dataset": "20260828104222_WVWTELEMETRY00TES.zip",
    "ts": "20260828104222",
    "vin": "WVWTELEMETRY00TES",
    "brand": "volkswagen",
    "captured_at": "2026-08-28T10:13:58+00:00",
    "fields": {
        "mileage": "11942",
        "fuel_level_current_level": "79",
        "tank_current_level": "100",
        "cruising_range_combined": "630",
        "scr_range": "14500",
        "outside_temperature": "3011",
        "oil_level_actual_level": "37.5",
        "parking_brake": "1",
        "parking_lights": "2",
        "locked_state_front_left_door": "2",
        "open_state_front_left_door": "3",
        "locked_state_front_right_door": "2",
        "open_state_front_right_door": "3",
        "locked_state__rear_left_door": "2",
        "open_state_rear_left_door": "3",
        "locked_state_rear_right_door": "2",
        "open_state_rear_right_door": "3",
        "locked_state_tailgate": "2",
        "open_state_tailgate": "3",
        "locked_state_front_engine_bonnet": "3",
        "open_state_front_engine_bonnet": "3",
        "tyre_pressure_actual_front_left": "1",
        "tyre_pressure_actual_rear_right": "1",
        "maintenance_interval_distance_until_inspection": "-28100",
        "maintenance_interval_distance_until_oil_change": "-18100",
        "active_warnings_in_instrument_cluster_feff_filtered": "1",
        "short_term_data_average_fuel_consumption": "67",
        "short_term_data_mileage": "267",
        "short_term_data_travel_time": "268",
        "long_term_data_average_fuel_consumption": "65",
        "long_term_data_mileage": "707",
        "long_term_data_average_speed": "58",
    },
}


def _emitted_fields() -> set[str]:
    """The full set of InfluxDB field names decode() can produce (ground truth, not regex)."""
    return set(decode(_FULL_RECORD).fields)


def _iter_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        yield from (s for v in obj.values() for s in _iter_strings(v))
    elif isinstance(obj, list):
        yield from (s for v in obj for s in _iter_strings(v))


def _dashboard_referenced_fields() -> set[str]:
    """Every `_field=="..."` a dashboard panel query references."""
    dash = json.loads((DEPLOY / "grafana-vehicle.json").read_text())
    refs: set[str] = set()
    for s in _iter_strings(dash):
        refs |= set(re.findall(r'_field\s*==\s*"([a-zA-Z0-9_]+)"', s))
    return refs


def test_dashboard_valid_json_with_vin_variable():
    d = json.loads((DEPLOY / "grafana-vehicle.json").read_text())
    assert d["uid"] == "vw-telemetry"
    names = [v["name"] for v in d["templating"]["list"]]
    assert "vin" in names
    assert any(p["type"] == "timeseries" for p in d["panels"])


def test_datasource_uses_vehicle_bucket():
    y = (DEPLOY / "grafana-datasource.yaml").read_text()
    assert "defaultBucket: vehicle" in y and "version: Flux" in y


def test_dashboard_only_queries_fields_the_decoder_emits():
    """Guard against dashboard/decoder drift: a panel querying a field decode() never produces
    would render silently empty in Grafana. Fail CI instead."""
    referenced = _dashboard_referenced_fields()
    assert referenced, 'no `_field=="..."` references found in the dashboard (regex/format drift?)'
    missing = referenced - _emitted_fields()
    assert not missing, (
        "dashboard queries field(s) decode.py never emits (would render empty): %s"
        % sorted(missing)
    )
