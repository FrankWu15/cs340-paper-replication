#!/bin/bash
# docker#27782 —— 真实源码复现驱动
# buggy = 修复提交的父提交；fixed = 修复提交本身。
set -u
REPO=/home/li/gopath/src/github.com/docker/docker
HERE=$(cd "$(dirname "$0")" && pwd)
export GOROOT=/home/li/toolchain/go1.7.6
export PATH=$GOROOT/bin:/home/li/bin:$PATH
export GOPATH=/home/li/gopath
export CC=/home/li/bin/gcc-nopie
export CGO_CFLAGS="-D_GNU_SOURCE -O2 -w"
RUNS=${RUNS:-3}
BUGGY=6314bec641b473571c0160d85bdc70250342185a
FIXED=a69a59ffc7e3d028a72d1195c2c1535f447eaa84
mkdir -p "$HERE/logs"

run_side() {
    local label=$1 sha=$2
    cd "$REPO" || exit 1
    git -c advice.detachedHead=false checkout -q "$sha" || exit 1
    for i in $(seq 1 "$RUNS"); do
        go test -run TestFollowLogsClosedConsumer -timeout 60s -v ./daemon/logger/jsonfilelog \
            > "$HERE/logs/${label}_run${i}.log" 2>&1
        printf '%-6s run%s: %s\n' "$label" "$i" \
            "$(grep -m1 'VERDICT' "$HERE/logs/${label}_run${i}.log" || echo 'NO VERDICT')"
    done
}

echo "go: $($GOROOT/bin/go version)"
run_side buggy "$BUGGY"
run_side fixed "$FIXED"
