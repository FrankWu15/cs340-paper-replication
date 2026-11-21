#!/bin/bash
# etcd#8183 (fix c678dcbd): compactor 测试里 fakeRevGetter.rev 的 data race
# buggy = 4dd7ef0a6 (2017-06-27)，glide.lock 精确还原 42 个依赖
set -u
R=/home/li/gopath/src/github.com/coreos/etcd
export GO111MODULE=off PATH=/usr/local/go1.10.8/bin:$PATH GOPATH=/home/li/gopath
L="$HOME/repro-1121/logs"
mkdir -p "$L"
cd "$R" || exit 9

git checkout -q 4dd7ef0a6 || exit 8
echo "[deps] HEAD=$(git rev-parse --short HEAD) glide=$(grep -c '^- name:' glide.lock)"
awk '/^- name:/{n=$3} /^  version:/{print n" "$2}' glide.lock > /tmp/deps8183.txt
total=$(wc -l < /tmp/deps8183.txt); fail=0
while read -r n v; do
  d="$GOPATH/src/$n"
  if [ ! -d "$d/.git" ]; then
    mkdir -p "$(dirname "$d")"
    git clone -q --no-checkout "https://$n" "$d" >> "$L/deps8183.log" 2>&1 || { echo "CLONEFAIL $n"; fail=$((fail+1)); continue; }
  fi
  git -C "$d" checkout -q "$v" >> "$L/deps8183.log" 2>&1 || { echo "COFAIL $n $v"; fail=$((fail+1)); }
done < /tmp/deps8183.txt
echo "[deps] total=$total fail=$fail"

run_side() {
  rev="$1"; tag="$2"
  git checkout -q "$rev" || return 8
  echo "[$tag] HEAD=$(git rev-parse --short HEAD) $(git log -1 --format=%ad --date=short)"
  go test -race -count=1 -v -run 'TestRevisionCompactor' -timeout 300s ./compactor > "$L/etcd8183_${tag}.log" 2>&1
  rc=$?
  echo "[$tag] exit=$rc races=$(grep -c 'WARNING: DATA RACE' "$L/etcd8183_${tag}.log" || true) pass=$(grep -c '^--- PASS' "$L/etcd8183_${tag}.log" || true)"
  head -20 "$L/etcd8183_${tag}.log"
}

run_side 4dd7ef0a6 buggy
run_side c678dcbd fixed
