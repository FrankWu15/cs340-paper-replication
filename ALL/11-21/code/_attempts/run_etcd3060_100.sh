#!/bin/bash
# etcd#3060: 100 轮 -race（论文 Table 12 口径：每条跑 100 次）
set -u
R=/home/li/gopath/src/github.com/coreos/etcd
export GO111MODULE=off PATH=/usr/local/go1.10.8/bin:$PATH
L="$HOME/repro-1121/logs"
cd "$R" || exit 9

run_side() {
  rev="$1"; tag="$2"
  git checkout -q "$rev" || return 1
  export GOPATH="$R/Godeps/_workspace:/home/li/gopath"
  echo "[$tag] HEAD=$(git rev-parse --short HEAD)"
  go test -race -count=100 -v -run 'TestSyncTrigger' -timeout 900s ./etcdserver > "$L/etcd3060_${tag}_100.log" 2>&1
  rc=$?
  races=$(grep -c "WARNING: DATA RACE" "$L/etcd3060_${tag}_100.log" || true)
  passes=$(grep -c "^--- PASS: TestSyncTrigger" "$L/etcd3060_${tag}_100.log" || true)
  fails=$(grep -c "^--- FAIL" "$L/etcd3060_${tag}_100.log" || true)
  echo "[$tag] exit=$rc races=$races pass=$passes fail=$fails"
}

run_side 00c32ef02 buggy
run_side 7f95780bfb5d72c651e870d0cc65c6f2b88700d8 fixed
