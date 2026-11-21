#!/usr/bin/env bash
# etcd#6278 双侧复现：单机 etcd server + clientv3/concurrency 触发器
# buggy = 48f4a7d03，fixed = 9497e967
# 用法：bash run.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
R="${ETCD_REPO:-/home/li/gopath/src/github.com/coreos/etcd}"
GO="${GO:-/usr/local/go1.10.8/bin/go}"
mkdir -p "$HERE/logs" "$HERE/results"

export GO111MODULE=off
export PATH="$(dirname "$GO"):$PATH"
export GOPATH="${GOPATH:-/home/li/gopath}"
PROBE="$GOPATH/src/etcd6278probe"
mkdir -p "$PROBE" && cp "$HERE/probe/main.go" "$PROBE/main.go"

cd "$R" || { echo "repo not found: $R"; exit 9; }

# 服务端用 fixed 版编译一次（#6278 只改客户端库）
git checkout -q 9497e967 || exit 8
$GO build -o /tmp/etcd6278srv . || { echo "server build fail"; exit 7; }
rm -rf /tmp/e6278 && mkdir -p /tmp/e6278
/tmp/etcd6278srv --name default --data-dir /tmp/e6278 \
  --listen-client-urls http://127.0.0.1:23791 --advertise-client-urls http://127.0.0.1:23791 \
  --listen-peer-urls http://127.0.0.1:23801 --initial-advertise-peer-urls http://127.0.0.1:23801 \
  --initial-cluster default=http://127.0.0.1:23801 > "$HERE/logs/etcd6278_server.log" 2>&1 &
srv=$!
trap 'kill -TERM $srv 2>/dev/null' EXIT
for _ in $(seq 1 20); do sleep 1; curl -s -m 1 http://127.0.0.1:23791/version >/dev/null 2>&1 && break; done
echo "[server] $(curl -s http://127.0.0.1:23791/version)"

run_side() {
  rev="$1"; tag="$2"
  git checkout -q "$rev" || return 8
  echo "[$tag] HEAD=$(git rev-parse --short HEAD)"
  ( cd "$PROBE" && $GO build -o /tmp/probe6278 . ) || { echo "[$tag] client build fail"; return 7; }
  /tmp/probe6278 2>&1 | tee "$HERE/logs/etcd6278_${tag}.log"
}

run_side 48f4a7d03 buggy
run_side 9497e967 fixed

b=$(grep -q '^CAMPAIGN_FAIL' "$HERE/logs/etcd6278_buggy.log" && echo DEADLOCK || echo OTHER)
f=$(grep -q '^CAMPAIGN_OK' "$HERE/logs/etcd6278_fixed.log" && echo CLEAN || echo OTHER)
printf 'buggy=%s fixed=%s\n' "$b" "$f" | tee "$HERE/results/verdict.txt"
[ "$b" = DEADLOCK ] && [ "$f" = CLEAN ]
