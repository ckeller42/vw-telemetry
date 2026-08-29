# How to: deploy to buspi

This installs vw-telemetry as a systemd timer on **buspi** (the same Raspberry Pi host that runs
`open-california`'s `calictl`), running independently — its own venv, its own InfluxDB bucket, its
own Grafana dashboard. It shares only the InfluxDB and Grafana *engines* already running on the
Pi.

## 1. Clone and install

```bash
ssh pi@buspi
cd ~/src   # or wherever you keep checkouts
git clone <this-repo> vw-telemetry
cd vw-telemetry
uv sync
```

`uv sync` creates `.venv` and installs the pinned dependencies (`influxdb-client`,
`carconnectivity-connector-vw-eu-data-act`) from the lockfile.

## 2. Write the credentials file

Credentials live outside the repo, mirroring how `calictl.env` is handled for the camper project:

```bash
sudo mkdir -p /etc/buspi
sudo touch /etc/buspi/vw-telemetry.env
sudo chmod 0600 /etc/buspi/vw-telemetry.env
sudo $EDITOR /etc/buspi/vw-telemetry.env
```

Base it on `deploy/vw-telemetry.env.example` — every variable is documented in
[Configuration](../reference/config.md). Fill in your VW-ID login, the target InfluxDB org/URL
(the buspi instance, org `home`), the `vehicle` bucket name, and — once you've run
[step 3](#3-create-the-influxdb-bucket) — the scoped write token. The file must stay `0600` and
owned so only root/the service user can read it; it is never committed.

## 3. Create the InfluxDB bucket

```bash
bash deploy/setup-bucket.sh
```

This is idempotent: it creates the `vehicle` bucket (long retention — 0 means infinite, since
telemetry at ~96 points/day/vehicle is tiny) in the existing `home` org if it doesn't already
exist, then prints an `influx auth create` command scoped to *only* that bucket. Run the printed
command and copy its token into the write token field of `/etc/buspi/vw-telemetry.env`. Because
the token is bucket-scoped, vw-telemetry can never read or write the camper project's `buspi`
bucket, and vice versa.

## 4. Install and enable the systemd units

```bash
sudo cp deploy/vw-telemetry.service deploy/vw-telemetry.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vw-telemetry.timer
```

The service is a `oneshot` (`ExecStart=... -m vwtelemetry.poll`) that reads
`/etc/buspi/vw-telemetry.env` and writes its watermark to
`/home/pi/vw-telemetry/state/watermark.json`. The timer fires it on boot (after a 3-minute delay)
and then every 15 minutes, matching the portal's delivery cadence.

Check it's running:

```bash
systemctl status vw-telemetry.timer
systemctl status vw-telemetry.service
journalctl -u vw-telemetry.service -n 50
```

The log line `vw-telemetry: wrote N point(s)` confirms a successful run. `N` can legitimately be
`0` on a run where the portal hasn't delivered a new dataset since the last poll.

## 5. Push the Grafana dashboard

```bash
uv run python deploy/push_dashboard.py --url http://localhost:3000 --token <grafana-api-token>
```

This upserts `deploy/grafana-vehicle.json` to buspi's local Grafana (`localhost:3000`) via
`overwrite: true`, so re-running it after editing the dashboard JSON is safe. You'll also need the
provisioned datasource from `deploy/grafana-datasource.yaml` pointing at the `vehicle` bucket.
Pushing to Grafana Cloud is optional and deferred — the Cloud token isn't readable from the Pi,
the same limitation noted for the camper project's dashboard.

## 6. Verify end to end

- `systemctl status vw-telemetry.service` — last run succeeded (`Active: inactive (dead)` with
  exit code 0 is normal for a oneshot between timer firings).
- `influx query 'from(bucket:"vehicle") |> range(start:-1h)' --org home` — points are landing,
  timestamped at the vehicle's own measurement time.
- Open the Grafana dashboard and confirm your vehicle appears in the `$vin` dropdown with live
  panels.

If nothing has landed after the first hour, check `journalctl -u vw-telemetry.service` for a
login or portal error, and confirm the EU Data Act "All data" request is enabled for the vehicle
(see [the tutorial](../tutorials/first-vehicle.md#1-enable-the-15-minute-data-feed-in-the-eu-data-act-portal)).
