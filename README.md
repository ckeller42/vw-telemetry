# vw-telemetry

[![CI](https://github.com/ckeller42/vw-telemetry/actions/workflows/ci.yml/badge.svg)](https://github.com/ckeller42/vw-telemetry/actions/workflows/ci.yml)
[![docs](https://img.shields.io/badge/docs-github%20pages-blue)](https://ckeller42.github.io/vw-telemetry/)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

Pull **Volkswagen-Group** vehicle telemetry from the **EU Data Act** portal into **InfluxDB**, and
visualise it in **Grafana**. Standalone, read-only, and generic — any user, any VW-Group car
(VW / Audi / Škoda / SEAT / Cupra / Bentley), any InfluxDB+Grafana host.

## Why

The **EU Data Act portal** (`eu-data-act.drivesomethinggreater.com`) is the official channel for
accessing your own VW-Group vehicle data — VW-ID login only, read-only, delivered as ~15-minute
batch datasets. This service polls it on a schedule and stores the decoded telemetry (odometer,
fuel, AdBlue, range, doors/windows/locks, tyres, service intervals, warnings, trip computers) in
InfluxDB for dashboards.

## Privacy & configuration

Nothing personal is committed. **Your VIN is never in the repo** — vehicles are auto-discovered from
your account at runtime and only ever appear as an InfluxDB tag on your own host. Credentials, brand,
country, and the InfluxDB target are all supplied via environment (see
`deploy/vw-telemetry.env.example`). CI blocks any real VIN or credential from being committed.

## Quick start

_(implementation pending — see the design doc)_ Bring your VW-ID and a host running InfluxDB +
Grafana; configure `.env`; enable the 15-minute systemd timer; import the dashboard.
