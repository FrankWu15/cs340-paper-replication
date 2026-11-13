#!/usr/bin/env bash
# Fast smoke test of all four modes; used by `make verify` and CI.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export GOPROXY=off GOSUMDB=off GOTRACEBACK=all

check() {
  mode="$1"; expected_rc="$2"; expected_pattern="$3"
  log="$(mktemp)"
  set +e
  timeout 5s ./bin/repro -mode="$mode" -run-id="verify-$mode" > "$log" 2>&1
  rc=$?
  set -e
  if [ "$rc" -ne "$expected_rc" ]; then
    echo "FAIL $mode: exit $rc, expected $expected_rc"; cat "$log"; rm -f "$log"; exit 1
  fi
  if ! grep -q "$expected_pattern" "$log"; then
    echo "FAIL $mode: pattern '$expected_pattern' not found"; cat "$log"; rm -f "$log"; exit 1
  fi
  echo "PASS $mode (rc=$rc)"
  rm -f "$log"
}

check buggy  2   "all goroutines are asleep - deadlock!"
check move   0   "status=finished"
check select 0   "status=finished"

# mode=live must hang silently until the timeout (rc=124), with no deadlock report.
log="$(mktemp)"
set +e
timeout 3s ./bin/repro -mode=live -run-id=verify-live > "$log" 2>&1
rc=$?
set -e
if [ "$rc" -ne 124 ] || grep -q "all goroutines are asleep" "$log"; then
  echo "FAIL live: rc=$rc (expected 124 and no deadlock report)"; cat "$log"; rm -f "$log"; exit 1
fi
echo "PASS live (rc=124, detector silent)"
rm -f "$log"
echo "All smoke checks passed."
