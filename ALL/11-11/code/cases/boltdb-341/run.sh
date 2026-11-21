#!/usr/bin/env bash
# boltdb#341 —— Close() 在写事务未结束时提前返回（非阻塞，确定性）
# buggy 55af28c  VERDICT=BUG  closeMs=0
# fixed c69cb102 VERDICT=OK   closeMs=150+
#
# 必须用独立探针，官方测试无效（见 README 与 docs/p4-repro-boltdb.md）。
set -uo pipefail

REPO="${P4_REPO:-$HOME/gopath/src/github.com/boltdb/bolt}"
GOPATH="${GOPATH:-$HOME/gopath}"
GO110="${GO110:-/usr/local/go1.10.8/bin/go}"
PROBE_DIR="${PROBE_DIR:-$GOPATH/src/boltprobe}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export GOPATH GO111MODULE=off
export GOROOT="$(dirname "$(dirname "$GO110")")"
export PATH="$GOROOT/bin:$PATH"

mkdir -p "$PROBE_DIR"
cp "$HERE/probe/main.go" "$PROBE_DIR/main.go"

for side in buggy fixed; do
  if [ "$side" = buggy ]; then sha=55af28c; else sha=c69cb102; fi
  echo "=== $side @ $sha ==="
  git -C "$REPO" checkout -f --detach "$sha" >/dev/null 2>&1 || { echo "[x] checkout 失败"; exit 1; }
  # 必须清 pkg：GOPATH 模式下 .a 不会随 checkout 失效，否则会链到上一个版本的代码
  rm -rf "$GOPATH/pkg"
  "$GO110" run "$PROBE_DIR/main.go" "$side" 2>&1 | tee "$HOME/bolt341_${side}.log"
  echo
done

git -C "$REPO" checkout -f master >/dev/null 2>&1 || true
echo "[ok] 日志: ~/bolt341_buggy.log  ~/bolt341_fixed.log"
