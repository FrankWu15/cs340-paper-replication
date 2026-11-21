#!/bin/bash
# 编译 gRPC-Go 2018 版 benchmark 客户端/服务端，供 Table 3 动态测量
set -u
export GOPATH=/home/li/gopath GO111MODULE=off PATH=/usr/local/go1.10.8/bin:$PATH
R=$GOPATH/src/google.golang.org/grpc
cd "$R" || exit 9
orig=$(git rev-parse --short HEAD)
echo "orig HEAD=$orig" > /tmp/grpc_orig_head
echo "=== checkout 2018"
git checkout -q f6692351 || { echo "CHECKOUT_FAIL"; exit 8; }
echo "HEAD=$(git rev-parse --short HEAD) $(git log -1 --format=%ad --date=short)"
echo "=== build server"
go build -o /tmp/bench_server ./benchmark/server 2>&1 | head -15
echo "server_rc=$? exists=$(test -x /tmp/bench_server && echo yes || echo no)"
echo "=== build client"
go build -o /tmp/bench_client ./benchmark/client 2>&1 | head -15
echo "client_rc=$? exists=$(test -x /tmp/bench_client && echo yes || echo no)"
