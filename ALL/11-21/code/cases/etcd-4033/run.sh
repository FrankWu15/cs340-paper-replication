#!/usr/bin/env bash
# etcd#4033 双侧复现
# buggy = bff857dc2（+ 从 fix 移植 raftexample_test.go），fixed = b7cf2385
# 用法：bash run.sh          （虚拟机内，仓库需在 $GOPATH/src/github.com/coreos/etcd）
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
R="${ETCD_REPO:-/home/li/gopath/src/github.com/coreos/etcd}"
GO="${GO:-/usr/local/go1.10.8/bin/go}"
mkdir -p "$HERE/logs" "$HERE/results"

export GO111MODULE=off
export PATH="$(dirname "$GO"):$PATH"
export GOPATH="$R/Godeps/_workspace:$(go env GOPATH 2>/dev/null || echo /home/li/gopath)"
cd "$R" || { echo "repo not found: $R"; exit 9; }

run_side() {
  rev="$1"; tag="$2"; prep="$3"
  rm -f contrib/raftexample/raftexample_test.go
  git checkout -q "$rev" || { echo "checkout fail $rev"; return 8; }
  if [ "$prep" = "port" ]; then
    git show b7cf2385:contrib/raftexample/raftexample_test.go > contrib/raftexample/raftexample_test.go || return 7
  fi
  echo "[$tag] HEAD=$(git rev-parse --short HEAD)  test=$(wc -l < contrib/raftexample/raftexample_test.go) lines"
  timeout 120 $GO test -count=1 -run 'TestProposeOnCommit' -timeout 45s -v ./contrib/raftexample \
    > "$HERE/logs/etcd4033_${tag}.log" 2>&1
  echo "[$tag] exit=$?"
  if grep -q "test timed out" "$HERE/logs/etcd4033_${tag}.log"; then echo "[$tag] symptom=HANG"
  elif grep -q "^--- PASS" "$HERE/logs/etcd4033_${tag}.log"; then echo "[$tag] symptom=PASS"
  else echo "[$tag] symptom=OTHER"; fi
}

run_side bff857dc2 buggy port
run_side b7cf2385 fixed none

b=$(grep -q "test timed out" "$HERE/logs/etcd4033_buggy.log" && echo HANG || echo OTHER)
f=$(grep -q "^--- PASS" "$HERE/logs/etcd4033_fixed.log" && echo PASS || echo OTHER)
printf 'buggy=%s fixed=%s\n' "$b" "$f" | tee "$HERE/results/verdict.txt"
[ "$b" = HANG ] && [ "$f" = PASS ]
