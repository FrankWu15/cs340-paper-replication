#!/usr/bin/env bash
# run_experiments.sh
# Build the buggy and fixed binaries and run each 20 times in the Linux
# (WSL) environment, capturing stdout/stderr + exit code per run.
#
# Expectation (mirrors the paper's blocking-bug behaviour):
#   buggy  -> deadlock -> Go native detector "all goroutines are asleep"
#             -> exit code 2  (20/20)
#   fixed  -> clean termination -> exit code 0  (20/20)
#
# Usage: bash scripts/run_experiments.sh
set -u

ROOT=/mnt/c/Users/30683/WorkBuddy/2026-11-05-11-07-12/cockroachdb-bugs-repro
cd "$ROOT"

RAW="$ROOT/results/raw"
FIG="$ROOT/results/figures"
mkdir -p "$RAW" "$FIG" bin

# No external deps; build offline to avoid any network dependency.
export GOPROXY=off GOSUMDB=off
go build -o bin/buggy  ./cmd/buggy  || { echo "BUILD buggy FAILED"; exit 1; }
go build -o bin/fixed ./cmd/fixed || { echo "BUILD fixed FAILED"; exit 1; }
echo "build ok"

N=20
CSV="$RAW/statistics.csv"
echo "variant,run,exit_code,deadlock" > "$CSV"

run_variant() {
  local variant=$1
  local bin=$2
  echo "=== running $variant x$N ==="
  for i in $(seq 1 "$N"); do
    idx=$(printf '%02d' "$i")
    log="$RAW/${variant}_${idx}.log"
    "./$bin" > "$log" 2>&1
    rc=$?
    # A deadlock is reported by Go with exit code 2.
    if [ "$rc" -eq 2 ]; then dl=1; else dl=0; fi
    echo "$variant,$idx,$rc,$dl" >> "$CSV"
  done
}

run_variant buggy  bin/buggy
run_variant fixed  bin/fixed

echo "=== summary ==="
echo "buggy deadlocks (exit 2): $(awk -F, '$1=="buggy" && $3==2' "$CSV" | wc -l)"
echo "fixed deadlocks (exit 2): $(awk -F, '$1=="fixed" && $3==2' "$CSV" | wc -l)"
echo "fixed clean    (exit 0): $(awk -F, '$1=="fixed" && $3==0' "$CSV" | wc -l)"
echo "DONE"
