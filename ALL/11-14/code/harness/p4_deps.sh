#!/usr/bin/env bash
# p4_deps.sh —— 反复编译，自动补齐缺失的依赖包
# 用法: p4_deps.sh <repo_dir> <pkg_subdir>
set -u
REPO=${1:?repo}
PKG=${2:-.}
export GOPATH=$HOME/gopath
export GO111MODULE=off
export GOROOT=/usr/local/go1.10.8
export PATH=$GOROOT/bin:$PATH

cd "$REPO/$PKG" || exit 1
for i in $(seq 1 15); do
  # 用 go test -c 编译测试二进制但不运行，才能暴露 _test.go 里的依赖
  out=$(go test -vet=off -c -o /tmp/_probe.test . 2>&1)
  missing=$(printf '%s\n' "$out" | grep -oE 'cannot find package "[^"]+"' | sed 's/cannot find package "//; s/"$//' | sort -u)
  if [ -z "$missing" ]; then
    echo "DEPS_OK after $((i-1)) rounds"
    printf '%s\n' "$out" | head -5
    exit 0
  fi
  echo "--- round $i: $(printf '%s' "$missing" | wc -w) missing"
  for p in $missing; do
    printf '  get %-55s' "$p"
    if timeout 120 go get -d "$p" >/tmp/depget.log 2>&1; then echo OK; else echo "FAIL($(tail -1 /tmp/depget.log | cut -c1-60))"; fi
  done
done
echo "DEPS_GIVEUP"
