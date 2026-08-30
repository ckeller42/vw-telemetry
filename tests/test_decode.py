from vwtelemetry.decode import decode


def test_scales_and_enums(raw_record):
    d = decode(raw_record)
    assert d.vin == "WVWTELEMETRY00TES" and d.brand == "volkswagen"
    assert d.time_utc == "2026-08-28T10:13:58+00:00"
    f = d.fields
    assert f["mileage_km"] == 11942
    assert f["fuel_pct"] == 79 and f["adblue_pct"] == 100
    assert f["range_km"] == 630 and f["adblue_range_km"] == 14500
    assert round(f["outside_temp_c"], 1) == 28.0  # 3011 deci-K
    assert f["parking_brake"] is True  # code 1
    assert f["trip_short_l_per_100km"] == 6.7  # 67 deci-L
    assert f["trip_long_avg_speed_kmh"] == 58


def test_door_aggregates(raw_record):
    f = decode(raw_record).fields
    assert f["door_front_left_locked"] is True  # code 2
    assert f["door_front_left_open"] is False  # code 3 = closed
    assert f["any_unlocked"] is False  # bonnet code 3 = unlocked, but bonnet doesn't count
    assert f["doors_locked"] == 2

    # Verify a real door unlock DOES trigger any_unlocked
    real_door_unlock = dict(raw_record)
    real_door_unlock["fields"] = dict(raw_record["fields"])
    real_door_unlock["fields"]["locked_state_front_left_door"] = "3"
    f_real_unlock = decode(real_door_unlock).fields
    assert f_real_unlock["any_unlocked"] is True


def test_service_overdue_and_warnings(raw_record):
    raw_record["fields"]["maintenance_interval_distance_until_inspection"] = "-28100"
    f = decode(raw_record).fields
    assert f["inspection_km_remaining"] == -28100
    assert f["warnings_active"] == 1


def test_tyres_all_ok(raw_record):
    assert decode(raw_record).fields["tyres_all_ok"] is True
