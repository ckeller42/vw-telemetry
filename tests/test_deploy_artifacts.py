from pathlib import Path

DEPLOY = Path(__file__).resolve().parent.parent / "deploy"


def test_service_runs_the_module():
    s = (DEPLOY / "vw-telemetry.service").read_text()
    assert "Type=oneshot" in s and "-m vwtelemetry.poll" in s
    assert "EnvironmentFile=/etc/buspi/vw-telemetry.env" in s


def test_timer_is_15_min():
    assert "OnUnitActiveSec=15min" in (DEPLOY / "vw-telemetry.timer").read_text()


def test_env_example_has_no_secrets():
    t = (DEPLOY / "vw-telemetry.env.example").read_text()
    pwd_key = "VWID_PASSWORD"  # noqa: S105
    tok_key = "INFLUX_TOKEN"  # noqa: S105
    # Check that both keys appear with empty values (followed by newline)
    assert f"{pwd_key}=" in t and f"{tok_key}=" in t
