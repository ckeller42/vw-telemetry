# Tutorial: your first vehicle in Grafana

This walks you from a fresh checkout to seeing your own car's telemetry in Grafana. It assumes
you already have a host running InfluxDB and Grafana (buspi, or any machine) and a VW-ID account
with at least one VW-Group vehicle on it.

## 1. Enable the 15-minute data feed in the EU Data Act portal

vw-telemetry reads the **EU Data Act portal** (`eu-data-act.drivesomethinggreater.com`), the
official channel VW provides for accessing your own vehicle data under the EU Data Act. It is
read-only and delivers a new dataset roughly every 15 minutes.

1. Sign in to the portal with your VW-ID.
2. Find your vehicle and enable the **"All data"** data request.
3. Wait for the first delivery. This can take anywhere from a few minutes to a few hours after
   you first enable the request — the portal has to provision the feed before it starts batching
   datasets. A parked, idle car will still emit empty datasets until it's driven; some fields (trip
   computers, live doors/locks) only populate once the car actually moves.

You don't need to note your VIN anywhere — vw-telemetry discovers every vehicle on the account
automatically at runtime.

## 2. Configure the environment

Clone the repository and install dependencies with [uv](https://docs.astral.sh/uv/):

```bash
git clone <this-repo> vw-telemetry
cd vw-telemetry
uv sync
```

Copy the example environment file and fill in your own values:

```bash
cp deploy/vw-telemetry.env.example .env
```

Edit `.env`:

```bash
VWID_USER=you@example.com
VW_BRAND=volkswagen        # volkswagen|audi|skoda|seat|cupra|bentley
VW_COUNTRY=DE
VW_VIN_ALLOWLIST=          # blank = all vehicles on the account
INFLUX_URL=http://localhost:8086
INFLUX_ORG=home
INFLUX_BUCKET=vehicle
```

Two more variables are in the example file, left blank on purpose: your VW-ID password, and an
InfluxDB write token scoped to the `vehicle` bucket (see
[Deploy to buspi](../how-to/deploy-buspi.md#3-create-the-influxdb-bucket) for how to create one
with `deploy/setup-bucket.sh`, or use an existing token if you already have one). Fill those two
in locally — never commit a `.env` with real values. Leave `VW_VIN_ALLOWLIST` blank to ingest
every vehicle on the account, or set it to a comma-separated list of VINs to restrict it.

`.env` is git-ignored — it never gets committed, and CI actively blocks any real VIN or
credential value from landing in the repository.

## 3. Run the poller once

```bash
uv run python -m vwtelemetry.poll
```

`poll.py` will:

1. Log into the EU Data Act portal with `EudaApiClient`.
2. List every vehicle on the account (filtered by `VW_VIN_ALLOWLIST` if set).
3. For each vehicle, list its datasets and download every one not already recorded in the local
   watermark (`state/watermark.json`).
4. Decode each dataset (`vwtelemetry.decode`) into typed, unit-suffixed fields.
5. Write the decoded points to the `vehicle` measurement in InfluxDB, timestamped with the
   vehicle's own measurement time — not the time you ran the poller.
6. Advance the watermark so the same dataset is never written twice.

On success it prints how many points it wrote:

```
vw-telemetry: wrote 1 point(s)
```

If it wrote `0` points on a fresh install, that's normal — the portal may not have delivered its
first dataset yet (see step 1). Run it again in a few minutes.

## 4. Confirm the data landed in InfluxDB

```bash
influx query 'from(bucket:"vehicle") |> range(start:-1h) |> limit(n:5)' --org home
```

You should see rows for the `vehicle` measurement, tagged with `vin`, `brand`, and
`source=eu_data_act`, and fields like `mileage_km`, `fuel_pct`, and `door_front_left_locked`.

## 5. Import the Grafana dashboard

Point Grafana at the `vehicle` bucket (a Flux datasource) and import
`deploy/grafana-vehicle.json`, either through the Grafana UI ("Import dashboard" → paste the
JSON) or with the provided script:

```bash
uv run python deploy/push_dashboard.py --url http://localhost:3000 --token <grafana-api-token>
```

Open the dashboard and pick your car from the `$vin` dropdown. You should see the mileage
timeline, fuel/AdBlue gauges, range, consumption trend, lock/open status, and service-overdue
panels populate for your vehicle.

## Next steps

- To run this continuously instead of by hand, see [Deploy to buspi](../how-to/deploy-buspi.md),
  which sets up the systemd timer that runs `poll.py` every 15 minutes.
- To add a metric the portal exposes but vw-telemetry doesn't decode yet, see
  [Add a new field](../how-to/add-a-field.md).
