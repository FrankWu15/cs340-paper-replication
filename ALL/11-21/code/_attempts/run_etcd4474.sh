#!/bin/bash
# etcd#4474 (fix 0cb304ec): raftexample 单节点重启路径死锁
# buggy = 0cb304ec^；判定 = 重启后新提案能否被提交（PUT 是乐观返回，必须看 GET）
set -u
R=/home/li/gopath/src/github.com/coreos/etcd
export GO111MODULE=off PATH=/usr/local/go1.10.8/bin:$PATH
L="$HOME/repro-1121/logs"
B="$HOME/repro-1121/bin"
mkdir -p "$L" "$B"
cd "$R" || exit 9

build() {
  rev="$1"; tag="$2"
  git checkout -q "$rev" || return 8
  export GOPATH="$R/Godeps/_workspace:/home/li/gopath"
  echo "[build $tag] HEAD=$(git rev-parse --short HEAD)"
  go build -o "$B/raft4474_$tag" ./contrib/raftexample || { echo "BUILD FAIL $tag"; return 7; }
}

build 0cb304ec^ buggy
build 0cb304ec fixed

run_case() {
  bin="$1"; tag="$2"; port="$3"; peer="$4"
  work="/tmp/raft4474-$tag"
  rm -rf "$work"; mkdir -p "$work"; cd "$work" || return 9
  "$bin" --id 1 --cluster "http://127.0.0.1:$peer" --port "$port" > "$L/etcd4474_${tag}_run1.log" 2>&1 &
  pid=$!
  sleep 3
  c1=$(curl -s -o /dev/null -w '%{http_code}' -XPUT --data 'v1' "http://127.0.0.1:$port/k1")
  sleep 2
  g1=$(curl -s "http://127.0.0.1:$port/k1")
  kill -TERM "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
  sleep 1

  "$bin" --id 1 --cluster "http://127.0.0.1:$peer" --port "$port" > "$L/etcd4474_${tag}_run2.log" 2>&1 &
  pid2=$!
  sleep 4
  c2=$(curl -s -o /dev/null -w '%{http_code}' -XPUT --data 'v2' "http://127.0.0.1:$port/k2")
  sleep 3
  g2=$(curl -s "http://127.0.0.1:$port/k2")
  alive=$(kill -0 "$pid2" 2>/dev/null && echo yes || echo no)
  kill -TERM "$pid2" 2>/dev/null; wait "$pid2" 2>/dev/null
  echo "$tag: put1=$c1 get1=[$g1] | put2=$c2 get2=[$g2] alive_after=$alive"
}

run_case "$B/raft4474_buggy" buggy 12380 12379
run_case "$B/raft4474_fixed" fixed 12480 12479
