## What & why

<!-- One or two sentences: what this PR changes and the reason. -->

## Checklist

- [ ] `uv run ruff check . && uv run ruff format --check .` clean
- [ ] `uv run mypy vwtelemetry` clean
- [ ] `uv run pytest -q` green (incl. the no-private-data guard)
- [ ] No real VIN or credentials added (guard enforces `WVWTELEMETRY00TES` only)
- [ ] Docs updated if behaviour/config changed (`uv run mkdocs build --strict`)

## Notes for reviewers

<!-- Anything CodeRabbit / a human reviewer should focus on. -->
