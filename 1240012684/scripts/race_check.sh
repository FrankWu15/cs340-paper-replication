#!/usr/bin/env bash
# Supplementary controlled check (report Section 4, Evidence 3).
#
# Build the SAME buggy program with Go's race detector and observe whether
# (a) a data race is reported and (b) the built-in deadlock detector still
# fires.  BoltDB v1.3.1 (2017) uses unsafe pointer arithmetic that modern Go
# checkptr rejects, so -gcflags=all=-d=checkptr=0 is required only for this
# instrumented build; the main experiment uses an unmodified build.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export GOPROXY=off GOSUMDB=off GOTRACEBACK=all
mkdir -p results/raw

echo "[race-check] building with -race (checkptr disabled for legacy bolt)"
go build -race -gcflags=all=-d=checkptr=0 -o bin/repro-race ./cmd/repro

set +e
timeout 15s ./bin/repro-race -mode=buggy -run-id=race-check > results/raw/race-check.log 2>&1
rc=$?
set -e
det=$(grep -c "all goroutines are asleep - deadlock" results/raw/race-check.log || true)
data_races=$(grep -c "WARNING: DATA RACE" results/raw/race-check.log || true)
hang=0; [ "$rc" -eq 124 ] && hang=1

{
  echo "# Supplementary controlled check: Go race detector on a blocking bug"
  echo "# log: results/raw/race-check.log"
  echo "exit_code=$rc"
  echo "deadlock_reported=$det"
  echo "data_race_warnings=$data_races"
  echo "silent_hang_until_timeout=$hang"
  echo "timeout=15s"
  echo "build_flags=-race -gcflags=all=-d=checkptr=0"
  echo "note=legacy BoltDB unsafe pointer code fails Go 1.26 checkptr; disabled only here"
} > results/race_check.txt
echo "[race-check] exit=$rc deadlock_reported=$det data_race_warnings=$data_races silent_hang=$hang"
