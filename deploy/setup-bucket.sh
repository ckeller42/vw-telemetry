#!/usr/bin/env bash
# Create the 'vehicle' bucket + a write-scoped token in the existing InfluxDB. Idempotent.
# Requires the influx CLI configured (or run on buspi where it is). ORG defaults to 'home'.
set -euo pipefail
ORG="${INFLUX_ORG:-home}"
BUCKET="${INFLUX_BUCKET:-vehicle}"
RETENTION="${INFLUX_RETENTION:-0}"   # 0 = infinite
influx bucket list --org "$ORG" --name "$BUCKET" >/dev/null 2>&1 \
  || influx bucket create --org "$ORG" --name "$BUCKET" --retention "$RETENTION"
echo "Bucket '$BUCKET' ready in org '$ORG'."
echo "Create a write-scoped token (copy into /etc/buspi/vw-telemetry.env as INFLUX_TOKEN):"
echo "  influx auth create --org $ORG --write-bucket \$(influx bucket list --org $ORG --name $BUCKET --hide-headers | awk '{print \$1}') --description vw-telemetry"
