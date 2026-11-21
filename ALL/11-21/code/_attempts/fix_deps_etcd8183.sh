#!/bin/bash
# 修复 #8183 的 5 个依赖：golang.org/x/* 走 GitHub 镜像；bolt/grpc 强制 checkout
set -u
R=/home/li/gopath/src/github.com/coreos/etcd
export GO111MODULE=off PATH=/usr/local/go1.10.8/bin:$PATH GOPATH=/home/li/gopath
L="$HOME/repro-1121/logs"
cd "$R" || exit 9
git checkout -q 4dd7ef0a6

# 1) golang.org/x/* -> github.com/golang/*
awk '/^- name: golang\.org\/x\//{n=$3} /^  version:/{print n" "$2}' glide.lock | while read -r n v; do
  sub=${n#golang.org/x/}
  d="$GOPATH/src/$n"
  rm -rf "$d"
  mkdir -p "$(dirname "$d")"
  if git clone -q "https://github.com/golang/$sub" "$d" >> "$L/deps8183.log" 2>&1; then
    git -C "$d" checkout -q "$v" >> "$L/deps8183.log" 2>&1 && echo "OK  $n $v" || echo "COFAIL $n $v"
  else
    echo "CLONEFAIL $n"
  fi
done

# 2) bolt / grpc：强制丢掉本地改动再 checkout
for pair in "github.com/boltdb/bolt 583e8937c61f1af6513608ccc75c97b6abdf4ff9" "google.golang.org/grpc b15215fb911b24a5d61d57feec4233d610530464"; do
  set -- $pair; d="$GOPATH/src/$1"; sha="$2"
  [ -d "$d/.git" ] || { echo "MISSING $1"; continue; }
  git -C "$d" checkout -q -- . 2>/dev/null
  if git -C "$d" checkout -q "$sha" 2>>"$L/deps8183.log"; then echo "OK  $1 $sha"
  else git -C "$d" fetch -q origin && git -C "$d" checkout -q "$sha" && echo "OK(fetch) $1" || echo "COFAIL $1"; fi
done

echo "=== rebuild test ==="
run_side() {
  rev="$1"; tag="$2"
  git checkout -q "$rev" || return 8
  echo "[$tag] HEAD=$(git rev-parse --short HEAD)"
  go test -race -count=1 -v -run 'TestRevisionCompactor' -timeout 300s ./compactor > "$L/etcd8183_${tag}.log" 2>&1
  rc=$?
  echo "[$tag] exit=$rc races=$(grep -c 'WARNING: DATA RACE' "$L/etcd8183_${tag}.log" || true) pass=$(grep -c '^--- PASS' "$L/etcd8183_${tag}.log" || true)"
  head -12 "$L/etcd8183_${tag}.log"
}
run_side 4dd7ef0a6 buggy
run_side c678dcbd fixed
