#!/bin/bash
# etcd#4033 复现：不带 -race（blocking 类走超时+栈判定，论文不要求 -race）
# buggy = bff857dc2 + 移植 fix 自带测试；fixed = b7cf2385
set -u
R=/home/li/gopath/src/github.com/coreos/etcd
export GO111MODULE=off PATH=/usr/local/go1.10.8/bin:$PATH
L="$HOME/repro-1121/logs"
mkdir -p "$L"
cd "$R" || exit 9

run_side() {
  rev="$1"; tag="$2"; prep="$3"
  rm -f contrib/raftexample/raftexample_test.go
  git checkout -q "$rev" || return 8
  if [ "$prep" = "port" ]; then
    git show b7cf2385:contrib/raftexample/raftexample_test.go > contrib/raftexample/raftexample_test.go || return 7
  fi
  export GOPATH="$R/Godeps/_workspace:/home/li/gopath"
  echo "[$tag] HEAD=$(git rev-parse --short HEAD) test=$(wc -l < contrib/raftexample/raftexample_test.go) lines"
  timeout 120 go test -count=1 -run 'TestProposeOnCommit' -timeout 45s -v ./contrib/raftexample > "$L/etcd4033_${tag}.log" 2>&1
  echo "[$tag] exit=$?"
  grep -q "test timed out" "$L/etcd4033_${tag}.log" && echo "[$tag] symptom=HANG(test timed out)"
  grep -q "^--- PASS" "$L/etcd4033_${tag}.log" && echo "[$tag] symptom=PASS"
  tail -4 "$L/etcd4033_${tag}.log"
}

run_side bff857dc2 buggy port
run_side b7cf2385 fixed none
