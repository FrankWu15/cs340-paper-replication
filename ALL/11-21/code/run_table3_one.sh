#!/bin/bash
# Table 3 单次测量：起 server + client，稳定后 SIGQUIT 抓 goroutine 栈与线程数
# 用法: run_one.sh <label> <concurrency> <duration>
set -u
L=$HOME/repro-1121/table3
mkdir -p "$L"
label=$1; conc=$2; dur=${3:-60}

export GRPC_GO_LOG_SEVERITY_LEVEL=info
export GRPC_GO_LOG_VERBOSITY_LEVEL=0

pkill -f /tmp/bench_server 2>/dev/null
pkill -f /tmp/bench_client 2>/dev/null
sleep 1

/tmp/bench_server -duration 300 > "$L/${label}_server.out" 2>&1 &
spid=$!
sleep 2
port=$(ss -ltnp 2>/dev/null | grep "pid=$spid," | sed -n 's/.*:\([0-9]\+\) .*/\1/p' | head -1)
echo "[$label] server pid=$spid port=$port"
if [ -z "$port" ]; then echo "[$label] PORT_FAIL"; kill $spid 2>/dev/null; exit 1; fi

/tmp/bench_client -server "127.0.0.1:${port}" -max_concurrent_rpcs "$conc" -duration "$dur" > "$L/${label}_client.out" 2>&1 &
cpid=$!
echo "[$label] client pid=$cpid conc=$conc"

sleep 12
echo "[$label] client_threads=$(awk '/^Threads:/{print $2}' /proc/$cpid/status 2>/dev/null)"
echo "[$label] server_threads=$(awk '/^Threads:/{print $2}' /proc/$spid/status 2>/dev/null)"

kill -QUIT "$cpid" 2>/dev/null
sleep 2
kill -QUIT "$spid" 2>/dev/null
sleep 2

echo "[$label] client_goroutines=$(grep -c '^goroutine ' "$L/${label}_client.out" 2>/dev/null)"
echo "[$label] server_goroutines=$(grep -c '^goroutine ' "$L/${label}_server.out" 2>/dev/null)"
echo "[$label] client stats:"; grep -E "Count|Mean|QPS|50%|90%|Elapsed" "$L/${label}_client.out" | head -8
echo "[$label] done"
