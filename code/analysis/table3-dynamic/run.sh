#!/bin/bash
# Table 3 复现入口：编译 → 起 server/client → pprof 采样 → 解析
# 依赖：Linux x86_64、ss、curl、python3；Go 侧源码为 grpc-go f6692351
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
SRC=${1:?用法: run.sh <grpc-go 2018 源码目录>}
LABEL=${2:-life_sync}
CONC=${3:-1}
DUR=${4:-35}

echo "== 1. 编译 =="
cd "$SRC"
GOFLAGS=-mod=mod GOPROXY=https://goproxy.cn,direct GOSUMDB=off \
  GOOS=linux GOARCH=amd64 CGO_ENABLED=0 \
  go build -o /tmp/bench_server_clean ./benchmark/server
GOFLAGS=-mod=mod GOPROXY=https://goproxy.cn,direct GOSUMDB=off \
  GOOS=linux GOARCH=amd64 CGO_ENABLED=0 \
  go build -o /tmp/bench_client ./benchmark/client

echo "== 2. 采样（100 轮 × 300ms） =="
BIN=/tmp/bench_server_clean bash "$HERE/../../run_table3_life.sh" "$LABEL" "$CONC" "$DUR" 100 0.3

echo "== 3. 解析 =="
python3 "$HERE/../../parse_life.py" "$HOME/repro-1121/table3" "$LABEL" 30.9 "$DUR"
