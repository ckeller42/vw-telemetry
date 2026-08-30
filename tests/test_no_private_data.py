"""CI guard: no real VIN and no credentials may ever be committed."""

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# The ONE allowlisted synthetic VIN used by tests/docs. Everything else VIN-shaped is blocked.
PLACEHOLDER_VIN = "WVWTELEMETRY00TES"
VIN_RE = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b")  # 17-char VIN charset (no I/O/Q)
CRED_RE = re.compile(r"(VWID_PASSWORD|INFLUX_TOKEN)[ \t]*=[ \t]*\S+")


def _tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files"],  # noqa: S607 - "git" resolved via PATH is intentional here
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    return [REPO / p for p in out.stdout.split() if p]


def _text_files() -> list[Path]:
    keep = {".py", ".md", ".toml", ".yml", ".yaml", ".sh", ".json", ".cfg", ".txt", ".example"}
    return [
        p
        for p in _tracked_files()
        if p.suffix in keep
        and p.is_file()
        # SDD plan/spec docs quote future files' exact contents (incl. placeholder
        # KEY= / VIN-shaped samples for later tasks) verbatim; they are design
        # material, not committed secrets - excluded the same way tooling excludes them.
        # (path-prefix check, not substring, so docs/superpowers-old/... etc. isn't
        # wrongly swept in too)
        and p.relative_to(REPO).parts[:2] != ("docs", "superpowers")
    ]


def test_no_real_vin_committed():
    offenders = []
    for f in _text_files():
        for m in VIN_RE.findall(f.read_text(errors="ignore")):
            if m != PLACEHOLDER_VIN:
                offenders.append(f"{f.relative_to(REPO)}: {m}")
    assert not offenders, (
        "VIN-shaped tokens committed (use the placeholder in tests):\n" + "\n".join(offenders)
    )


def test_no_credentials_committed():
    offenders = []
    for f in _text_files():
        if f.name.endswith(".env.example"):
            continue  # placeholders like VWID_PASSWORD (empty) are fine here
        for m in CRED_RE.findall(f.read_text(errors="ignore")):
            offenders.append(f"{f.relative_to(REPO)}: {m}")
    assert not offenders, "credential assignments committed:\n" + "\n".join(offenders)


def test_cred_regex_does_not_span_newlines():
    # a bare KEY= on its own line (empty value) must NOT match a token on a later line
    password_key = "VWID_PASSWORD"  # noqa: S105
    token_key = "INFLUX_TOKEN"  # noqa: S105
    assert not CRED_RE.search(password_key + "=\n\nsome prose later\n")
    # an inline populated credential MUST still be caught
    assert CRED_RE.search(password_key + "=hunter2")
    assert CRED_RE.search(token_key + " = abc123")
