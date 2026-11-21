#!/bin/bash
# Table 3: goroutine 生命周期测量（双端 pprof 采样，从程序启动起采样）
# 用法: run_table3_life.sh <label> <concurrency> <client_duration> <rounds> <gap>
set -u
L=$HOME/repro-1121/table3
mkdir -p "$L"
label=$1; conc=$2; dur=${3:-35}; rounds=${4:-100}; gap=${5:-0.3}
BIN=${BIN:-/tmp/bench_server_clean}

export GRPC_GO_LOG_SEVERITY_LEVEL=info
export GRPC_GO_LOG_VERBOSITY_LEVEL=0

pkill -f /tmp/bench_server 2>/dev/null
pkill -f /tmp/bench_client 2>/dev/null
sleep 1

$BIN -duration 300 > "$L/${label}_server.out" 2>&1 &
spid=$!
sleep 2
spport=$(grep -o "Server profiling address:.*" "$L/${label}_server.out" | head -1 | sed 's/.*://')
sports=$(ss -ltnp 2>/dev/null | grep "pid=$spid," | sed -n 's/.*:\([0-9]\+\) .*/\1/p')
port=$(echo "$sports" | grep -vx "$spport" | head -1)
echo "[$label] server=$spid grpc=$port pprof=$spport"
[ -z "$port" ] && { echo "[$label] PORT_FAIL"; kill $spid 2>/dev/null; exit 1; }

mkdir -p "$L/${label}_sp" "$L/${label}_cp"
rm -f "$L/${label}_sp"/*.txt "$L/${label}_cp"/*.txt

/tmp/bench_client -server "127.0.0.1:${port}" -max_concurrent_rpcs "$conc" -duration "$dur" > "$L/${label}_client.out" 2>&1 &
cpid=$!
sleep 0.5
cpport=$(grep -o "Client profiling address:.*" "$L/${label}_client.out" | head -1 | sed 's/.*://')
echo "[$label] client=$cpid pprof=$cpport dur=${dur}s"

t0=$(date +%s%N)
for i in $(seq 1 "$rounds"); do
  f=$(printf '%04d' $i)
  curl -s -m 2 "http://127.0.0.1:${spport}/debug/pprof/goroutine?debug=2" > "$L/${label}_sp/$f.txt" 2>/dev/null &
  p1=$!
  curl -s -m 2 "http://127.0.0.1:${cpport}/debug/pprof/goroutine?debug=2" > "$L/${label}_cp/$f.txt" 2>/dev/null &
  p2=$!
  wait $p1 $p2
  sleep "$gap"
done
t1=$(date +%s%N)
win=$(echo "scale=2; ($t1-$t0)/1000000000" | bc)
echo "[$label] window_s=$win"
echo "[$label] threads client=$(awk '/^Threads:/{print $2}' /proc/$cpid/status 2>/dev/null) server=$(awk '/^Threads:/{print $2}' /proc/$spid/status 2>/dev/null)"

kill -TERM "$cpid" 2>/dev/null
sleep 1
kill -TERM "$spid" 2>/dev/null
echo "[$label] done"
