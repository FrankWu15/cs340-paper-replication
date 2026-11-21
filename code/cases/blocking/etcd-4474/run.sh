#!/usr/bin/env bash
# etcd#4474 双侧复现：单节点 raftexample 重启
# buggy = 0cb304ec^ (5e47ba3fa)，fixed = 0cb304ec
# 用法：bash run.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
R="${ETCD_REPO:-/home/li/gopath/src/github.com/coreos/etcd}"
GO="${GO:-/usr/local/go1.10.8/bin/go}"
BIN="$HERE/.bin"
mkdir -p "$HERE/logs" "$HERE/results" "$BIN"

export GO111MODULE=off
export PATH="$(dirname "$GO"):$PATH"
cd "$R" || { echo "repo not found: $R"; exit 9; }

build() {
  rev="$1"; tag="$2"
  git checkout -q "$rev" || { echo "checkout fail $rev"; return 8; }
  export GOPATH="$R/Godeps/_workspace:$(go env GOPATH 2>/dev/null || echo /home/li/gopath)"
  echo "[build $tag] HEAD=$(git rev-parse --short HEAD)"
  $GO build -o "$BIN/raftexample_$tag" ./contrib/raftexample || return 7
}

run_case() {
  bin="$1"; tag="$2"; port="$3"; peer="$4"
  work="/tmp/raft4474-$tag"
  rm -rf "$work"; mkdir -p "$work"; cd "$work" || return 9

  "$bin" --id 1 --cluster "http://127.0.0.1:$peer" --port "$port" > "$HERE/logs/${tag}_run1.log" 2>&1 &
  pid=$!
  sleep 3
  c1=$(curl -s -o /dev/null -w '%{http_code}' -XPUT --data 'v1' "http://127.0.0.1:$port/k1")
  sleep 2
  g1=$(curl -s "http://127.0.0.1:$port/k1")
  kill -TERM "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
  sleep 1

  "$bin" --id 1 --cluster "http://127.0.0.1:$peer" --port "$port" > "$HERE/logs/${tag}_run2.log" 2>&1 &
  pid2=$!
  sleep 4
  c2=$(curl -s -o /dev/null -w '%{http_code}' -XPUT --data 'v2' "http://127.0.0.1:$port/k2")
  sleep 3
  g2=$(curl -s "http://127.0.0.1:$port/k2")
  alive=$(kill -0 "$pid2" 2>/dev/null && echo yes || echo no)
  kill -TERM "$pid2" 2>/dev/null; wait "$pid2" 2>/dev/null
  echo "$tag: put1=$c1 get1=[$g1] | put2=$c2 get2=[$g2] alive_after=$alive"
}

build 0cb304ec^ buggy
build 0cb304ec fixed

run_case "$BIN/raftexample_buggy" buggy 12380 12379 | tee "$HERE/results/summary.txt"
run_case "$BIN/raftexample_fixed" fixed 12480 12479 | tee -a "$HERE/results/summary.txt"

b=$(grep '^buggy:' "$HERE/results/summary.txt" | grep -q 'alive_after=no' && echo CRASH || echo OTHER)
f=$(grep '^fixed:' "$HERE/results/summary.txt" | grep -q 'get2=\[v2\]' && echo CLEAN || echo OTHER)
printf 'buggy=%s fixed=%s\n' "$b" "$f" | tee "$HERE/results/verdict.txt"
[ "$b" = CRASH ] && [ "$f" = CLEAN ]
