from vwtelemetry.config import Config
from vwtelemetry.reader import Reader


class FakeClient:
    def __init__(self, user, pw, country="DE", accept_terms_on_login=True):
        pass

    def ensure_login(self):
        pass

    def list_vehicles(self):
        return [{"vin": "WVWTELEMETRY00TES"}]

    def get_metadata(self, vin, request_type="partial"):
        return {"Identifier": "ID1"}

    def list_datasets(self, vin, ident, request_type="partial"):
        return [
            {"name": "20260828104222_WVWTELEMETRY00TES.zip"},
            {"name": "20260828101000_WVWTELEMETRY00TES_no_content_found.zip"},
        ]

    def download_dataset(self, vin, ident, name, request_type="partial"):
        return {
            "Data": [
                {
                    "dataFieldName": "mileage",
                    "value": "11942",
                    "timestampUtc": "2026-08-28T10:13:58.000Z",
                }
            ]
        }


def _cfg():
    return Config("u", "p", "volkswagen", "DE", [], "http://x", "home", "vehicle", "t")


def test_yields_only_new_content_datasets():
    r = Reader(_cfg(), client_factory=lambda u, p, country: FakeClient(u, p, country))
    recs = list(r.iter_new_records(seen={}))
    assert len(recs) == 1  # the no_content one is skipped
    rec = recs[0]
    assert rec["vin"] == "WVWTELEMETRY00TES" and rec["fields"]["mileage"] == "11942"
    assert rec["captured_at"].startswith("2026-08-28T10:13:58")


def test_skips_already_seen():
    r = Reader(_cfg(), client_factory=lambda u, p, country: FakeClient(u, p, country))
    seen = {"WVWTELEMETRY00TES": {"20260828104222_WVWTELEMETRY00TES.zip"}}
    assert list(r.iter_new_records(seen=seen)) == []


def test_vin_allowlist_filters():
    cfg = Config("u", "p", "volkswagen", "DE", ["OTHERVIN"], "http://x", "home", "vehicle", "t")
    r = Reader(cfg, client_factory=lambda u, p, country: FakeClient(u, p, country))
    assert list(r.iter_new_records(seen={})) == []  # our VIN not in allowlist
