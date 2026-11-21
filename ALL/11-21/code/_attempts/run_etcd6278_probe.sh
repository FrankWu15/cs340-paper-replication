#!/bin/bash
# etcd#6278 真实复现：单机 etcd server + clientv3/concurrency 小程序
# buggy = 48f4a7d03，fixed = 9497e967
# 触发条件：已存在 "testa"，再在 "test" 前缀上 Campaign —— buggy 会等错 key 直到 ctx 超时
set -u
R=/home/li/gopath/src/github.com/coreos/etcd
export GO111MODULE=off PATH=/usr/local/go1.10.8/bin:$PATH GOPATH=/home/li/gopath
L="$HOME/repro-1121/logs"
PROBE="$GOPATH/src/etcd6278probe"
mkdir -p "$L" "$PROBE"
cp /tmp/main6278.go "$PROBE/main.go"
cd "$R" || exit 9

# 服务端用 fixed 版编译一次即可（#6278 只改客户端库）
git checkout -q 9497e967
go build -o /tmp/etcd6278srv . || { echo "SERVER BUILD FAIL"; exit 7; }
rm -rf /tmp/e6278 && mkdir -p /tmp/e6278
/tmp/etcd6278srv --name default --data-dir /tmp/e6278 \
  --listen-client-urls http://127.0.0.1:23791 --advertise-client-urls http://127.0.0.1:23791 \
  --listen-peer-urls http://127.0.0.1:23801 --initial-advertise-peer-urls http://127.0.0.1:23801 \
  --initial-cluster default=http://127.0.0.1:23801 > "$L/etcd6278_server.log" 2>&1 &
srv=$!
for i in $(seq 1 20); do sleep 1; curl -s -m 1 http://127.0.0.1:23791/version >/dev/null 2>&1 && break; done
echo "[server] $(curl -s http://127.0.0.1:23791/version)"

run_side() {
  rev="$1"; tag="$2"
  git checkout -q "$rev" || return 8
  echo "[$tag] HEAD=$(git rev-parse --short HEAD)"
  ( cd "$PROBE" && go build -o /tmp/probe6278 . ) || { echo "[$tag] CLIENT BUILD FAIL"; return 7; }
  /tmp/probe6278 2>&1 | tee "$L/etcd6278_${tag}.log"
}

run_side 48f4a7d03 buggy
# 清掉上一次的 election key，避免残留影响 fixed 侧
curl -s -XPOST http://127.0.0.1:23791/v3/kv/deleterange -d '{"key":"dGVzdA==","range_end":"dGVzdA=="}' >/dev/null 2>&1 || true
run_side 9497e967 fixed

kill -TERM "$srv" 2>/dev/null
