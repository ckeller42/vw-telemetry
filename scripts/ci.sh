#!/usr/bin/env bash
# Local mirror of CI — run before pushing. Same gates the workflow runs.
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
cd "$(dirname "$0")/.."

uv sync --all-extras
uv run pytest tests/test_no_private_data.py -q   # privacy guard first (fail fast)
uv run ruff check .
uv run ruff format --check .
uv run mypy vwtelemetry
uv run pytest -q
uv run mkdocs build --strict
echo "local gate: all green ✓"
