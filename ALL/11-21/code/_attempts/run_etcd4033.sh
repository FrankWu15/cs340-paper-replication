#!/bin/bash
# etcd#4033 (fix b7cf2385): raftexample proposal channel 死锁
# buggy = b7cf2385^ = bff857dc2；buggy 侧需从 fix 移植补丁自带的 raftexample_test.go
set -u
R=/home/li/gopath/src/github.com/coreos/etcd
export GO111MODULE=off PATH=/usr/local/go1.10.8/bin:$PATH
L="$HOME/repro-1121/logs"
mkdir -p "$L"
cd "$R" || exit 9

# --- buggy ---
git checkout -q bff857dc2 || exit 8
git show b7cf2385:contrib/raftexample/raftexample_test.go > contrib/raftexample/raftexample_test.go || exit 7
export GOPATH="$R/Godeps/_workspace:/home/li/gopath"
echo "[buggy] HEAD=$(git rev-parse --short HEAD) testfile=$(wc -l < contrib/raftexample/raftexample_test.go) lines"
timeout 150 go test -race -count=1 -run 'TestProposeOnCommit' -timeout 60s -v ./contrib/raftexample > "$L/etcd4033_buggy.log" 2>&1
echo "[buggy] exit=$?"
grep -c "WARNING: DATA RACE" "$L/etcd4033_buggy.log" | sed 's/^/[buggy] races=/'
tail -12 "$L/etcd4033_buggy.log"

# --- fixed ---
git checkout -q b7cf2385 || exit 8
echo "[fixed] HEAD=$(git rev-parse --short HEAD)"
export GOPATH="$R/Godeps/_workspace:/home/li/gopath"
timeout 150 go test -race -count=1 -run 'TestProposeOnCommit' -timeout 60s -v ./contrib/raftexample > "$L/etcd4033_fixed.log" 2>&1
echo "[fixed] exit=$?"
grep -c "WARNING: DATA RACE" "$L/etcd4033_fixed.log" | sed 's/^/[fixed] races=/'
tail -8 "$L/etcd4033_fixed.log"
