#!/usr/bin/env bash
# 4 smoke trials: 2 bugs x {buggy should deadlock, fixed should exit clean}.
set -e
export GOPROXY=off GOSUMDB=off GOTRACEBACK=all
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN="$ROOT/bin/repro"
mkdir -p "$ROOT/bin"
go build -o "$BIN" ./cmd/repro
chk() { # bug mode expected_rc
  set +e
  out=$("$BIN" -bug="$1" -mode="$2" 2>&1); rc=$?
  set -e
  if [ "$rc" -eq "$3" ]; then echo "PASS $1/$2 (rc=$rc)"; else echo "FAIL $1/$2 expected rc=$3 got rc=$rc"; echo "$out" | head -5; exit 1; fi
}
chk etcd6873 buggy 2
chk etcd6873 fixed 0
chk doublelock buggy 2
chk doublelock fixed 0
echo "[verify] all PASS"
