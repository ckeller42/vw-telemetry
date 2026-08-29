# Contributing to vw-telemetry

## Workflow (PR-based)

1. Branch off `main`: `git switch -c <type>-<short-desc>` (e.g. `feat-add-field`).
2. Make changes with tests. Keep every gate green locally (see below).
3. Push the branch and open a **pull request to `main`**.
4. CI runs (secret-scan, no-private-data guard, ruff, mypy, pytest, mkdocs build) **and**
   **CodeRabbit** reviews the PR automatically.
5. Address findings, then merge once CI is green and review is resolved. `main` is the release line.

Do not commit directly to `main`.

## Local quality gate (uv)

```sh
uv sync --all-extras
uv run ruff check . && uv run ruff format --check .
uv run mypy vwtelemetry
uv run pytest -q
uv run mkdocs build --strict
```

## Hard rules

- **Never commit a real VIN or credentials.** Tests/docs use only the synthetic VIN
  `WVWTELEMETRY00TES`; `.env` and `state/` are gitignored. The `no-private-data` guard (in CI and
  pre-commit) blocks real VW-Group VIN patterns and populated `VWID_PASSWORD=`/`INFLUX_TOKEN=`.
- Install the pre-commit hooks once: `uv run pre-commit install`.

## CodeRabbit

PRs are reviewed by [CodeRabbit](https://coderabbit.ai) (configured in `.coderabbit.yaml`). The
GitHub App must be installed on the repository by an owner for reviews to post.
