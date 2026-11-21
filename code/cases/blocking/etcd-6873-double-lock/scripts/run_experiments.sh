#!/usr/bin/env bash
# Run every (bug, mode) combination REPEAT times and collect raw logs + summary.
set -o pipefail
export GOPROXY=off GOSUMDB=off GOTRACEBACK=all
REPEAT="${REPEAT:-20}"
TIMEOUT_SEC="${TIMEOUT_SEC:-8s}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN="$ROOT/bin/repro"
RAW="$ROOT/results/raw"
CSV="$ROOT/results/summary.csv"
mkdir -p "$ROOT/bin" "$RAW"
go build -o "$BIN" ./cmd/repro

: > "$CSV"
echo "run_id,bug,mode,reproduced_deadlock,exit_code,elapsed_ms" >> "$CSV"

for bug in etcd6873 doublelock; do
  for mode in buggy fixed; do
    for i in $(seq 1 "$REPEAT"); do
      rid="${bug}-$(printf '%02d' "$i")"
      log="$RAW/${bug}-${mode}-$(printf '%02d' "$i").log"
      set +e
      timeout "$TIMEOUT_SEC" "$BIN" -bug="$bug" -mode="$mode" -run-id="$rid" > "$log" 2>&1
      rc=$?
      reproduced=0
      if [ "$rc" -eq 2 ] || grep -q "all goroutines are asleep" "$log"; then reproduced=1; fi
      elapsed=$(grep -oE 'elapsed_ms=[0-9.]+' "$log" | tail -1 | cut -d= -f2)
      [ -z "$elapsed" ] && elapsed=NA
      echo "$rid,$bug,$mode,$reproduced,$rc,$elapsed" >> "$CSV"
    done
    echo "done $bug/$mode ($REPEAT runs)"
  done
done

python3 "$ROOT/scripts/analyze.py"
echo "[done] raw logs: $RAW ; summary: $CSV"
