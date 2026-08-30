# Reference: configuration

vw-telemetry is configured **entirely by environment variables** — nothing personal (VIN,
credentials, host) is ever hard-coded or committed. `vwtelemetry.config.Config.from_env()` reads
these at startup; on a plain dev checkout it also loads a `.env` file in the working directory if
one is present (see `deploy/vw-telemetry.env.example` for a template). On buspi these live in
`/etc/buspi/vw-telemetry.env` (root-owned, `0600`), mirroring how `calictl.env` is handled for the
camper project.

| Env | Meaning | Default |
|---|---|---|
| `VWID_USER` | VW-ID login email | — (required) |
| `VWID_PASSWORD` | VW-ID login password | — (required) |
| `VW_BRAND` | `volkswagen` \| `audi` \| `skoda` \| `seat` \| `cupra` \| `bentley` | `volkswagen` |
| `VW_COUNTRY` | EU Data Act portal country | `DE` |
| `VW_VIN_ALLOWLIST` | comma-separated VIN list; blank = every vehicle on the account | blank |
| `INFLUX_URL` | InfluxDB base URL | `http://localhost:8086` |
| `INFLUX_ORG` | InfluxDB org | `home` |
| `INFLUX_BUCKET` | destination bucket | `vehicle` |
| `INFLUX_TOKEN` | write token scoped to `INFLUX_BUCKET` | — (required) |

`Config.from_env()` exits with a clear error listing any of `VWID_USER`, `VWID_PASSWORD`, or
`INFLUX_TOKEN` that are missing — those three have no default and must always be supplied.

`VW_VIN_ALLOWLIST` is the only way to restrict which vehicles get polled; the VIN itself is never
configured directly — it's always discovered from the account by `vwtelemetry.reader.Reader` and
only ever appears downstream as an InfluxDB tag on your own host.

One more variable, outside `Config`, controls where the watermark file is written:

| Env | Meaning | Default |
|---|---|---|
| `VW_STATE_DIR` | directory for `watermark.json` (the per-VIN dedupe state) | `state` |

`deploy/vw-telemetry.service` sets `VW_STATE_DIR` explicitly so the systemd unit's watermark
persists under its `WorkingDirectory` regardless of the process's current directory.
