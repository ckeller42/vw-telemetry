import pytest


@pytest.fixture
def raw_record():
    """A synthetic EU Data Act record (placeholder VIN, representative field values)."""
    return {
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
            "locked_state_front_engine_bonnet": "3",
            "open_state_front_engine_bonnet": "3",
            "locked_state__rear_left_door": "2",
            "open_state_rear_left_door": "3",
            "tyre_pressure_actual_front_left": "1",
            "tyre_pressure_actual_rear_right": "1",
            "active_warnings_in_instrument_cluster_feff_filtered": "1",
            "short_term_data_mileage": "267",
            "short_term_data_travel_time": "268",
            "short_term_data_average_fuel_consumption": "67",
            "long_term_data_mileage": "707",
            "long_term_data_average_speed": "58",
            "long_term_data_average_fuel_consumption": "65",
        },
    }
