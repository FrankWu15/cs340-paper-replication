#!/bin/bash
# etcd#3060 (fix 7f95780b): etcdserver raft internal var 初始化竞争
# buggy = fix^ = 00c32ef02 (2015-06-29)，依赖在仓库自带 Godeps/_workspace
set -u
R=/home/li/gopath/src/github.com/coreos/etcd
export GO111MODULE=off PATH=/usr/local/go1.10.8/bin:$PATH
L="$HOME/repro-1121/logs"
mkdir -p "$L"
cd "$R" || exit 9

run_side() {
  rev="$1"; tag="$2"
  git checkout -q "$rev" || { echo "checkout fail $rev"; return 1; }
  export GOPATH="$R/Godeps/_workspace:/home/li/gopath"
  echo "[$tag] HEAD=$(git rev-parse --short HEAD) date=$(git log -1 --format=%ad --date=short)"
  go test -race -count=1 -run 'TestSyncTrigger' -timeout 300s ./etcdserver > "$L/etcd3060_${tag}.log" 2>&1
  echo "[$tag] exit=$?"
  grep -c "WARNING: DATA RACE" "$L/etcd3060_${tag}.log" 2>/dev/null | sed "s/^/[$tag] races=/"
  tail -5 "$L/etcd3060_${tag}.log"
}

run_side 00c32ef02 buggy
run_side 7f95780bfb5d72c651e870d0cc65c6f2b88700d8 fixed
