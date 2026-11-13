#!/usr/bin/env bash
# =============================================================================
# Non-blocking concurrency bug reproduction — experiment driver
# (self-contained: place one copy in each <app>/scripts/run_experiments.sh)
#
# What it measures
#   A non-blocking bug does NOT deadlock: the program always finishes. The bug
#   is a DATA RACE, observable only when built with `go build -race`.
#   For each (toolchain, mode, build) we run N times and record whether the
#   race detector reported "WARNING: DATA RACE".
#
#   Expected verdicts:
#     buggy + race  -> race reported (exit 66)   [bug reproduced]
#     fixed + race  -> clean         (exit 0)    [fix works]
#     buggy + plain -> clean run, no deadlock    [silent, non-blocking nature]
#     fixed + plain -> clean run
#
# Toolchains (Linux / WSL2):
#   go126 = default `go`  -> Go 1.26.8 (primary, modern -race, module-aware)
#   go18  = $HOME/sdks/go1.8.7/bin/go with GOROOT -> Go 1.8.7 (era-faithful
#           cross-check, closest to the 2015/2016 upstream commits)
#   Both run the SAME source files; Go 1.8 uses GOPATH mode (GO111MODULE=off).
#
# GORACE=halt_on_error=1 makes the process exit promptly at the first race
# (exit 66) instead of printing many reports; it does not affect clean runs.
# =============================================================================
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$(basename "$ROOT")"
RAW="$ROOT/results/raw"
FIG="$ROOT/results/figures"
EVID="$ROOT/results/real-source-evidence"
mkdir -p "$RAW" "$FIG" "$EVID"

N="${N:-20}"
ITERS="${ITERS:-5000}"
OLDGO="$HOME/sdks/go1.8.7/bin/go"
OLDROOT="$HOME/sdks/go1.8.7"

WORK="/tmp/nbexp_${APP}"
rm -rf "$WORK"; mkdir -p "$WORK/logs"
LOGTMP="$WORK/logs"
CSV="$WORK/statistics.csv"
RUNLOG="$WORK/_run.txt"

GOV_NEW="$(go version 2>&1)"
GOV_OLD="$(GOROOT="$OLDROOT" "$OLDGO" version 2>&1)"

binpath() { echo "$WORK/${1}_${2}_${3}"; }   # tc_mode_build

compile() {
  local tc="$1" gobin="$2" goroot="$3" mode="$4" build="$5"
  local src="$ROOT/$mode/main.go"
  local out; out="$(binpath "$tc" "$mode" "$build")"
  local -a envp=() flags=()
  [ "$tc" = "go18" ] && envp=(env "GOROOT=$goroot" GO111MODULE=off)
  [ "$build" = "race" ] && flags=(-race)
  ( cd /tmp && "${envp[@]}" "$gobin" build "${flags[@]}" -o "$out" "$src" ) >>"$RUNLOG" 2>&1
  return $?
}

run_one() {
  local tc="$1" gov="$2" mode="$3" build="$4" run="$5"
  local bin; bin="$(binpath "$tc" "$mode" "$build")"
  local log="$LOGTMP/${tc}_${mode}_${build}_${run}.log"
  GORACE="halt_on_error=1" timeout 60 "$bin" -n "$ITERS" >"$log" 2>&1
  local rc=$?
  local rd=0; grep -q "WARNING: DATA RACE" "$log" && rd=1
  printf '%s,%s,%s,%s,%s,%s,%s\n' "$APP" "$tc" "$mode" "$build" "$run" "$rc" "$rd" >>"$CSV"
}

echo "app=$APP  N=$N  iters=$ITERS" | tee "$RUNLOG"
echo "new: $GOV_NEW" | tee -a "$RUNLOG"
echo "old: $GOV_OLD" | tee -a "$RUNLOG"
printf 'app,toolchain,mode,build,run,exit_code,race_detected\n' >"$CSV"

# --- compile all binaries once per toolchain ---
echo "=== compiling ===" | tee -a "$RUNLOG"
for mode in buggy fixed; do
  for build in race plain; do
    if compile go126 go "" "$mode" "$build"; then echo "  go126 $mode/$build OK" | tee -a "$RUNLOG"; else echo "  go126 $mode/$build BUILD_FAIL"; fi
  done
done
for mode in buggy fixed; do
  if compile go18 "$OLDGO" "$OLDROOT" "$mode" race; then echo "  go18 $mode/race OK" | tee -a "$RUNLOG"; else echo "  go18 $mode/race BUILD_FAIL"; fi
done

# --- run all groups ---
echo "=== running (N=$N per group) ===" | tee -a "$RUNLOG"
for mode in buggy fixed; do
  for build in race plain; do
    for i in $(seq -w 1 "$N"); do run_one go126 "$GOV_NEW" "$mode" "$build" "$i"; done
  done
done
for mode in buggy fixed; do
  for i in $(seq -w 1 "$N"); do run_one go18 "$GOV_OLD" "$mode" race "$i"; done
done

# --- summary (from CSV, authoritative) ---
grp() { awk -F, -v a="$1" -v m="$2" -v b="$3" '$2==a&&$3==m&&$4==b{n++;r+=$7}END{printf "%d/%d", r+0, n+0}' "$CSV"; }
echo "=== summary (race_detected / runs) ===" | tee -a "$RUNLOG"
echo "  go126 buggy race  : $(grp go126 buggy race)   (want $N/$N)" | tee -a "$RUNLOG"
echo "  go126 fixed race  : $(grp go126 fixed race)   (want 0/$N)" | tee -a "$RUNLOG"
echo "  go126 buggy plain : $(grp go126 buggy plain)  (want 0/$N; no -race)" | tee -a "$RUNLOG"
echo "  go126 fixed plain : $(grp go126 fixed plain)  (want 0/$N)" | tee -a "$RUNLOG"
echo "  go18  buggy race  : $(grp go18 buggy race)   (want $N/$N)" | tee -a "$RUNLOG"
echo "  go18  fixed race  : $(grp go18 fixed race)   (want 0/$N)" | tee -a "$RUNLOG"

# --- publish evidence ---
cp "$CSV" "$RAW/statistics.csv"
cp "$RUNLOG" "$RAW/_run.log"
cp "$LOGTMP"/*.log "$RAW/" 2>/dev/null
# keep one full race report as an easy-to-read exhibit
cp "$LOGTMP/go126_buggy_race_01.log" "$EVID/sample_race_report.log" 2>/dev/null
# environment record
{
  echo "Primary toolchain : $GOV_NEW"
  echo "Cross-check       : $GOV_OLD (GOROOT=$OLDROOT, GO111MODULE=off, GOPATH mode)"
  echo "OS                : $(uname -a)"
  echo "Detector          : go build -race ; GORACE=halt_on_error=1"
  echo "Runs per group    : $N ; iterations per goroutine per run: $ITERS"
  echo "Date (UTC)        : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$EVID/ENVIRONMENT.txt"

echo "=== DONE: results in $RAW ===" | tee -a "$RUNLOG"
