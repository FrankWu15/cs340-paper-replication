#!/bin/bash
# docker#8909 —— 真实源码复现驱动
# buggy = 修复提交的父提交；fixed = 修复提交本身。两侧跑同一份测试。
set -u
REPO=/home/li/gopath/src/github.com/docker/docker
HERE=$(cd "$(dirname "$0")" && pwd)
export GOROOT=/home/li/toolchain/go1.5.4
export PATH=$GOROOT/bin:/home/li/bin:$PATH
export GOPATH=$REPO/vendor:/home/li/gopath
export CC=/home/li/bin/gcc-nopie
export CGO_CFLAGS="-D_GNU_SOURCE -O2 -w"
TAGS="exclude_graphdriver_btrfs exclude_graphdriver_devicemapper"
RUNS=${RUNS:-3}
BUGGY=4d4a7b81bf82e243bca07af815cb1fe03193b135
FIXED=03ea2166b66632ee7cdd824d7acd87b15c9bccb2
mkdir -p "$HERE/logs"

run_side() {
    local label=$1 sha=$2
    cd "$REPO" || exit 1
    git -c advice.detachedHead=false checkout -q "$sha" || exit 1
    for i in $(seq 1 "$RUNS"); do
        go test -tags "$TAGS" -run TestExitedFilter -timeout 120s -v ./daemon \
            > "$HERE/logs/${label}_run${i}.log" 2>&1
        printf '%-6s run%s: %s\n' "$label" "$i" \
            "$(grep -m1 'VERDICT' "$HERE/logs/${label}_run${i}.log" || echo 'NO VERDICT')"
    done
}

echo "go: $($GOROOT/bin/go version)"
run_side buggy "$BUGGY"
run_side fixed "$FIXED"
