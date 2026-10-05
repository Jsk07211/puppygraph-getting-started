#!/usr/bin/env bash
# Start the demo stack and load the data into Iceberg.
#
# Runs entirely inside Docker: CSV-to-Parquet conversion and table loading both happen
# in the spark-iceberg container, so no local Python is needed. Safe to re-run.
#
# Usage: ./init.sh
set -euo pipefail
cd "$(dirname "$0")"

SPARK="docker exec spark-iceberg"
SPARK_STDIN="docker exec -i spark-iceberg"
LOG="$(mktemp -t init-sh.XXXXXX)"
trap 'echo "Failed. Details:" >&2; tail -n 30 "$LOG" >&2' ERR

echo "==> Starting services"
docker compose up -d

echo "==> Waiting for Spark and the Iceberg catalog"
for attempt in $(seq 1 40); do
  if $SPARK spark-sql -S -e "SHOW DATABASES" >/dev/null 2>&1; then
    break
  fi
  if [ "$attempt" -eq 40 ]; then
    echo "Spark did not become ready; check 'docker compose logs spark-iceberg'" >&2
    exit 1
  fi
  sleep 3
done

echo "==> Converting CSV files to Parquet"
$SPARK python3 /home/iceberg/CsvToParquet.py /csv_data /parquet_data >>"$LOG" 2>&1

echo "==> Loading tables into Iceberg"
$SPARK spark-sql -S -f /home/iceberg/init.sql >>"$LOG" 2>&1

echo "==> Checking row counts"
tables=$($SPARK sh -c 'cd /csv_data && ls *.csv | sed "s/\.csv$//"')
query=""
for t in $tables; do
  query="${query}SELECT '${t}', COUNT(*) FROM ai_chip_supply_chain.${t};"
done
$SPARK spark-sql -S -e "$query" 2>>"$LOG" | $SPARK_STDIN python3 -c '
import glob, os, sys, pandas as pd
loaded = dict(line.split("\t") for line in sys.stdin.read().splitlines() if "\t" in line)
expected_tables = {os.path.basename(f)[:-4] for f in glob.glob("/csv_data/*.csv")}
failed = 0
for table in sorted(expected_tables - set(loaded)):
    failed += 1
    print(f"  MISSING  {table}: no table loaded")
for table, count in sorted(loaded.items()):
    expected = len(pd.read_csv(f"/csv_data/{table}.csv", keep_default_na=False, na_values=[""]))
    if int(count) != expected:
        failed += 1
        print(f"  MISMATCH {table}: {count} rows loaded, {expected} in CSV")
print(f"  {len(loaded)} of {len(expected_tables)} tables loaded" + ("" if failed else "; all row counts match the CSV files"))
sys.exit(1 if failed else 0)
'

echo
echo "Done. Open PuppyGraph at http://localhost:8081 (puppygraph / puppygraph123)"
echo "and create the graph schema described in SCHEMA.md."
