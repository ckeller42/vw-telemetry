from vwtelemetry.config import Config
from vwtelemetry.poll import run


class FakeReader:
    def __init__(self, recs):
        self._recs = recs

    def iter_new_records(self, seen):
        return (r for r in self._recs if r["dataset"] not in seen.get(r["vin"], set()))


def _cfg():
    return Config("u", "p", "volkswagen", "DE", [], "http://x", "home", "vehicle", "t")


def _rec(name):
    return {
        "dataset": name,
        "ts": name[:14],
        "vin": "WVWTELEMETRY00TES",
        "brand": "volkswagen",
        "captured_at": "2026-08-28T10:13:58+00:00",
        "fields": {"mileage": "11942"},
    }


def test_writes_and_persists_watermark(tmp_path):
    written = []
    n = run(
        _cfg(),
        reader=FakeReader([_rec("20260828104222_WVWTELEMETRY00TES.zip")]),
        write=lambda cfg, pts: written.extend(pts) or len(pts),
        state_dir=str(tmp_path),
    )
    assert n == 1 and len(written) == 1
    # second run: same dataset is now in the watermark -> nothing written
    n2 = run(
        _cfg(),
        reader=FakeReader([_rec("20260828104222_WVWTELEMETRY00TES.zip")]),
        write=lambda cfg, pts: len(pts),
        state_dir=str(tmp_path),
    )
    assert n2 == 0
