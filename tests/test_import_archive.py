import json

import pytest

from vwtelemetry.config import Config
from vwtelemetry.import_archive import (
    _ts_to_iso,
    import_records,
    iter_records,
    normalize,
)


def _cfg(allow=None, brand="volkswagen"):
    return Config("u", "p", brand, "DE", allow or [], "http://x", "home", "vehicle", "t")


def _archive_rec(name="20260830164321_WVWTELEMETRY00TES.zip"):
    """An archive-shaped record: no brand, no captured_at — only ts + fields."""
    return {
        "dataset": name,
        "ts": name[:14],
        "vin": "WVWTELEMETRY00TES",
        "fields": {"mileage": "12337"},
    }


def test_ts_to_iso_converts_utc():
    """A valid 14-digit stamp becomes an ISO-8601 UTC string."""
    assert _ts_to_iso("20260830164321") == "2026-08-30T16:43:21+00:00"


@pytest.mark.parametrize(
    "bad",
    [
        "2026083016432",  # too short
        "not-a-ts",  # non-digit
        "202608301643210",  # too long
        "",  # empty
        "20261301000000",  # month 13 — 14 digits but not a real date
        "20260230120000",  # Feb 30 — impossible calendar day
        "20260830250000",  # hour 25
    ],
)
def test_ts_to_iso_rejects_malformed(bad):
    """Only real calendar timestamps convert; 14-digits-but-impossible is rejected."""
    with pytest.raises(ValueError):
        _ts_to_iso(bad)


def test_normalize_fills_captured_at_from_ts_and_defaults_brand():
    """A bare archive record gains captured_at (from ts) and the default brand."""
    rec = normalize(_archive_rec())
    assert rec["captured_at"] == "2026-08-30T16:43:21+00:00"
    assert rec["brand"] == "volkswagen"


def test_normalize_uses_given_default_brand():
    """The default brand is caller-supplied, so imports can match the live feed's brand tag."""
    rec = normalize(_archive_rec(), default_brand="cupra")
    assert rec["brand"] == "cupra"


def test_normalize_preserves_existing_captured_at():
    """An explicit captured_at/brand in the record is never overwritten."""
    rec = normalize(
        {
            "ts": "20260830164321",
            "vin": "V",
            "captured_at": "2026-01-01T00:00:00+00:00",
            "brand": "audi",
            "fields": {},
        }
    )
    assert rec["captured_at"] == "2026-01-01T00:00:00+00:00" and rec["brand"] == "audi"


def test_import_records_decodes_and_writes_with_vehicle_time():
    """Records decode to points timestamped at the vehicle's own measurement time."""
    written = []
    n = import_records(
        _cfg(), [_archive_rec()], write=lambda cfg, pts: written.extend(pts) or len(pts)
    )
    assert n == 1
    line = written[0].to_line_protocol()
    assert "mileage_km=12337" in line and "vin=WVWTELEMETRY00TES" in line
    # timestamp derived from ts (2026-08-30T16:43:21Z) -> nanosecond epoch suffix
    assert line.rstrip().endswith("1788108201000000000")


def test_import_records_tags_brand_from_config():
    """Brandless records inherit config.brand, so they overwrite live points instead of forking."""
    written = []
    import_records(
        _cfg(brand="cupra"),
        [_archive_rec()],
        write=lambda cfg, pts: written.extend(pts) or len(pts),
    )
    assert "brand=cupra" in written[0].to_line_protocol()


def test_import_records_respects_vin_allowlist():
    """A record whose VIN is outside the allowlist is skipped entirely."""
    written = []
    n = import_records(
        _cfg(allow=["SOMEOTHERVIN0000"]),
        [_archive_rec()],
        write=lambda cfg, pts: written.extend(pts) or len(pts),
    )
    assert n == 0 and written == []


def test_iter_records_reads_jsonl_skipping_blanks(tmp_path):
    """Blank lines in the JSONL store are ignored; every data line yields one record."""
    p = tmp_path / "arc.jsonl"
    a = json.dumps(_archive_rec())
    b = json.dumps(_archive_rec("20260830165915_X.zip"))
    p.write_text(f"{a}\n\n{b}\n")  # blank line in the middle must be skipped
    recs = list(iter_records(str(p)))
    assert len(recs) == 2 and recs[0]["ts"] == "20260830164321"
