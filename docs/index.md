# vw-telemetry

**vw-telemetry** pulls Volkswagen-Group vehicle telemetry from the **EU Data Act portal** into
**InfluxDB**, and visualises it in **Grafana**. It's standalone, read-only, and generic — any
user, any VW-Group car (VW / Audi / Škoda / SEAT / Cupra / Bentley), on any InfluxDB + Grafana
host. A oneshot process, fired by a systemd timer every 15 minutes, logs into the portal,
downloads any datasets it hasn't seen yet, decodes them, and writes the results to InfluxDB —
nothing personal (no VIN, no credentials) is ever committed to this repository.

## Documentation map

This documentation is organised by [Diátaxis](https://diataxis.fr/), which separates material by
what you're trying to do:

- **[Tutorial](tutorials/first-vehicle.md)** — learning-oriented. Start here: from an empty
  checkout to your own vehicle's data in Grafana.
- **How-to guides** — goal-oriented steps for a specific task:
    - [Deploy to buspi](how-to/deploy-buspi.md)
    - [Add a new field](how-to/add-a-field.md)
- **Reference** — information-oriented, precise and complete:
    - [InfluxDB schema](reference/influx-schema.md)
    - [Configuration (environment variables)](reference/config.md)
    - [API (`vwtelemetry` modules)](reference/api.md)
- **[Explanation](explanation/design.md)** — understanding-oriented: the design, why the EU Data
  Act portal exists, the architecture, and known limitations.
