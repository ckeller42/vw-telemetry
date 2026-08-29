# vw-telemetry

Pull **Volkswagen-Group** vehicle telemetry from the **EU Data Act** portal into **InfluxDB**, and
visualise it in **Grafana**. Standalone, read-only, and generic — any user, any VW-Group car
(VW / Audi / Škoda / SEAT / Cupra / Bentley), any InfluxDB+Grafana host.

> **Status: design phase.** The committed design is in
> [`docs/explanation/design.md`](docs/explanation/design.md); implementation follows.

## Why

VW locked the app/WeConnect API behind Google Play Integrity **attestation** (an unforgeable,
device-bound token). The **EU Data Act portal** is the sanctioned, attestation-free path — VW-ID
login only, read-only, ~15-minute batch datasets. This service polls it on a schedule and stores the
decoded telemetry (odometer, fuel, AdBlue, range, doors/windows/locks, tyres, service intervals,
warnings, trip computers) for dashboards.

## Privacy & configuration

Nothing personal is committed. **Your VIN is never in the repo** — vehicles are auto-discovered from
your account at runtime and only ever appear as an InfluxDB tag on your own host. Credentials, brand,
country, and the InfluxDB target are all supplied via environment (see
`deploy/vw-telemetry.env.example`). CI blocks any real VIN or credential from being committed.

## Quick start

_(implementation pending — see the design doc)_ Bring your VW-ID and a host running InfluxDB +
Grafana; configure `.env`; enable the 15-minute systemd timer; import the dashboard.
