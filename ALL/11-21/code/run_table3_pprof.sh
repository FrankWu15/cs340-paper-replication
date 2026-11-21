#!/bin/bash
# Table 3: goroutine 生命周期测量
# 用 server 的 pprof(/debug/pprof/goroutine?debug=2) 周期采样，按 goroutine ID 统计存活时长
# 用法: run_table3_pprof.sh <label> <concurrency> <duration> <samples>
set -u
L=$HOME/repro-1121/table3
mkdir -p "$L"
label=$1; conc=$2; dur=${3:-40}; rounds=${4:-60}

export GRPC_GO_LOG_SEVERITY_LEVEL=info
export GRPC_GO_LOG_VERBOSITY_LEVEL=0

pkill -f /tmp/bench_server 2>/dev/null
pkill -f /tmp/bench_client 2>/dev/null
sleep 1

/tmp/bench_server -duration 300 > "$L/${label}_server.out" 2>&1 &
spid=$!
sleep 2
port=$(ss -ltnp 2>/dev/null | grep "pid=$spid," | sed -n 's/.*:\([0-9]\+\) .*/\1/p' | head -1)
pport=$(grep -o "Server profiling address: .*" "$L/${label}_server.out" | head -1 | awk '{print $NF}' | sed 's/.*://')
echo "[$label] server=$spid port=$port pprof=$pport"
[ -z "$port" ] && { echo "[$label] PORT_FAIL"; kill $spid 2>/dev/null; exit 1; }

/tmp/bench_client -server "127.0.0.1:${port}" -max_concurrent_rpcs "$conc" -duration "$dur" > "$L/${label}_client.out" 2>&1 &
cpid=$!
sleep 8

echo "[$label] sampling $rounds rounds x 200ms"
mkdir -p "$L/${label}_pprof"
rm -f "$L/${label}_pprof"/*.txt
t0=$(date +%s%N)
for i in $(seq 1 "$rounds"); do
  curl -s -m 2 "http://127.0.0.1:${pport}/debug/pprof/goroutine?debug=2" > "$L/${label}_pprof/$(printf '%03d' $i).txt" 2>/dev/null
  sleep 0.2
done
t1=$(date +%s%N)
echo "[$label] sample_window_s=$(echo "scale=2; ($t1-$t0)/1000000000" | bc)"

echo "[$label] threads client=$(awk '/^Threads:/{print $2}' /proc/$cpid/status 2>/dev/null) server=$(awk '/^Threads:/{print $2}' /proc/$spid/status 2>/dev/null)"
kill -TERM "$cpid" 2>/dev/null
sleep 1
kill -TERM "$spid" 2>/dev/null
echo "[$label] done"
