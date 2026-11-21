#!/bin/bash
# docker#256 —— 真实源码复现驱动
# 从仓库里取出对应提交的 archive.go（逐字节相同，未做任何修改），
# 与驱动一起用 `go test archive.go <test>` 单独编译运行。
set -u
REPO=/home/li/work/gp
HERE=$(cd "$(dirname "$0")" && pwd)
export GOROOT=/home/li/toolchain/go1.5.4
export PATH=$GOROOT/bin:/home/li/bin:$PATH
RUNS=${RUNS:-3}
BUGGY=1d6929c8bc6cbc5ad63dce083869460b6bb377ad
FIXED=58befe3081726ef74ea09198cd9488fb42c51f51

run_side() {
    local label=$1 sha=$2
    local dir="$HERE/$label"
    rm -rf "$dir"; mkdir -p "$dir"
    git -C "$REPO" show "$sha:archive.go" > "$dir/archive.go" || exit 1
    cp "$HERE/zz_repro_cmdstream_test.go" "$dir/"
    cd "$dir" || exit 1
    for i in $(seq 1 "$RUNS"); do
        go test archive.go zz_repro_cmdstream_test.go -timeout 60s -v \
            > "$HERE/logs/${label}_run${i}.log" 2>&1
        printf '%-6s run%s: %s\n' "$label" "$i" \
            "$(grep -m1 'VERDICT' "$HERE/logs/${label}_run${i}.log" || echo 'NO VERDICT')"
    done
}

mkdir -p "$HERE/logs"
echo "go: $($GOROOT/bin/go version)"
run_side buggy "$BUGGY"
run_side fixed "$FIXED"
