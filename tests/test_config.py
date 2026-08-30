import pytest

from vwtelemetry.config import Config


def test_from_env_reads_all(monkeypatch):
    for k, v in {
        "VWID_USER": "u@e.com",
        "VWID_PASSWORD": "pw",
        "VW_BRAND": "audi",
        "VW_COUNTRY": "AT",
        "VW_VIN_ALLOWLIST": "WVWTELEMETRY00TES, ABC",
        "INFLUX_URL": "http://x:8086",
        "INFLUX_ORG": "home",
        "INFLUX_BUCKET": "vehicle",
        "INFLUX_TOKEN": "tok",
    }.items():
        monkeypatch.setenv(k, v)
    c = Config.from_env()
    assert c.brand == "audi" and c.country == "AT"
    assert c.vin_allowlist == ["WVWTELEMETRY00TES", "ABC"]
    assert c.influx_bucket == "vehicle" and c.vwid_user == "u@e.com"


def test_defaults(monkeypatch):
    for k in (
        "VW_BRAND",
        "VW_COUNTRY",
        "VW_VIN_ALLOWLIST",
        "INFLUX_URL",
        "INFLUX_ORG",
        "INFLUX_BUCKET",
    ):
        monkeypatch.delenv(k, raising=False)
    for k, v in {"VWID_USER": "u", "VWID_PASSWORD": "p", "INFLUX_TOKEN": "t"}.items():
        monkeypatch.setenv(k, v)
    c = Config.from_env()
    assert c.brand == "volkswagen" and c.country == "DE"
    assert c.influx_url == "http://localhost:8086" and c.influx_org == "home"
    assert c.influx_bucket == "vehicle" and c.vin_allowlist == []


def test_missing_required_exits(monkeypatch):
    monkeypatch.delenv("VWID_USER", raising=False)
    monkeypatch.setenv("VWID_PASSWORD", "p")
    monkeypatch.setenv("INFLUX_TOKEN", "t")
    with pytest.raises(SystemExit):
        Config.from_env()
