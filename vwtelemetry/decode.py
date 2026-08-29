"""Decode a raw EU Data Act dataset into a typed InfluxDB field set.

Enum codes are authoritative, from the vw_eu_data_act connector's decoders:
  lock 2=locked/3=unlocked · open 2=open/3=closed · lights 2=off/3-5=on
  parking_brake 0/1 · outside_temperature deci-Kelvin · *_consumption deci-L/100km
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DOOR_SUFFIXES = [
    "front_left_door",
    "front_right_door",
    "_rear_left_door",
    "rear_right_door",
    "tailgate",
    "front_engine_bonnet",
]


@dataclass(frozen=True)
class DecodedPoint:
    vin: str
    brand: str
    time_utc: str
    fields: dict[str, float | int | bool]


def _num(v: object) -> float | None:
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def decode(record: dict[str, Any]) -> DecodedPoint:
    src: dict[str, str] = record.get("fields", {})
    out: dict[str, float | int | bool] = {}

    def g(k: str) -> float | None:
        return _num(src.get(k))

    def put_int(name: str, key: str) -> None:
        v = g(key)
        if v is not None:
            out[name] = int(v)

    put_int("mileage_km", "mileage")
    put_int("fuel_pct", "fuel_level_current_level")
    put_int("adblue_pct", "tank_current_level")
    put_int("range_km", "cruising_range_combined")
    put_int("adblue_range_km", "scr_range")
    temp = g("outside_temperature")
    if temp is not None:
        out["outside_temp_c"] = round(temp / 10 - 273.15, 1)
    oil = g("oil_level_actual_level")
    if oil is not None:
        out["oil_level"] = oil
    pb = g("parking_brake")
    if pb in (0, 1):
        out["parking_brake"] = bool(pb)

    # doors: per-door bools + aggregates
    locked = opened = 0
    any_unlocked = False
    for suffix in DOOR_SUFFIXES:
        name = suffix.lstrip("_")
        # Strip _door suffix for output name
        output_name = name[:-5] if name.endswith("_door") else name
        lk = _num(src.get("locked_state_" + suffix, src.get("locked_state_" + name)))
        op = _num(src.get("open_state_" + name))
        if lk == 2:
            out[f"door_{output_name}_locked"] = True
            locked += 1
        elif lk == 3:
            out[f"door_{output_name}_locked"] = False
            any_unlocked = True
        if op == 2:
            out[f"door_{output_name}_open"] = True
            opened += 1
        elif op == 3:
            out[f"door_{output_name}_open"] = False
    out["doors_locked"] = locked
    out["doors_open"] = opened
    out["any_unlocked"] = any_unlocked

    # tyres: status codes; 1 across all actual_* = OK
    tp = [k for k in src if k.startswith("tyre_pressure_actual")]
    if tp:
        vals = {_num(src[k]) for k in tp}
        out["tyres_all_ok"] = vals <= {1.0}

    # service (negative = overdue)
    for name, key in (
        ("inspection_km_remaining", "maintenance_interval_distance_until_inspection"),
        ("oil_km_remaining", "maintenance_interval_distance_until_oil_change"),
    ):
        v = g(key)
        if v is not None:
            out[name] = int(v)
    w = g("active_warnings_in_instrument_cluster_feff_filtered")
    if w is not None:
        out["warnings_active"] = int(w)

    # trip computers
    stc = g("short_term_data_average_fuel_consumption")
    if stc is not None:
        out["trip_short_l_per_100km"] = round(stc / 10, 1)
    stk, stm = g("short_term_data_mileage"), g("short_term_data_travel_time")
    if stk is not None:
        out["trip_short_km"] = int(stk)
    if stk and stm:
        out["trip_short_avg_speed_kmh"] = round(stk / (stm / 60), 1)
    ltc = g("long_term_data_average_fuel_consumption")
    if ltc is not None:
        out["trip_long_l_per_100km"] = round(ltc / 10, 1)
    lts = g("long_term_data_average_speed")
    if lts is not None:
        out["trip_long_avg_speed_kmh"] = int(lts)

    return DecodedPoint(
        vin=record["vin"],
        brand=record.get("brand", "volkswagen"),
        time_utc=record["captured_at"] or "",
        fields=out,
    )
