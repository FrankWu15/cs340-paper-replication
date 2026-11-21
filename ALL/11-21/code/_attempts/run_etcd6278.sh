#!/bin/bash
# etcd#6278 (fix 9497e967): Election 前缀与既有 key 重叠，等错 key 导致 Campaign 死锁
# buggy = 48f4a7d03 (2016-08-29)，移植 fix 自带的 TestElectionOnPrefixOfExistingKey
set -u
R=/home/li/gopath/src/github.com/coreos/etcd
export GO111MODULE=off PATH=/usr/local/go1.10.8/bin:$PATH GOPATH=/home/li/gopath
L="$HOME/repro-1121/logs"
mkdir -p "$L"
cd "$R" || exit 9

git checkout -q 48f4a7d03 || exit 8
echo "[deps] HEAD=$(git rev-parse --short HEAD) glide=$(grep -c '^- name:' glide.lock)"

# 全量依赖：x/* 用 GitHub 镜像，其它直连；已存在的强制对齐版本
awk '/^- name:/{n=$3} /^  version:/{print n" "$2}' glide.lock > /tmp/deps6278.txt
while read -r n v; do
  case "$n" in
    golang.org/x/*) url="https://github.com/golang/${n#golang.org/x/}" ;;
    google.golang.org/grpc) url="https://github.com/grpc/grpc-go" ;;
    *) url="https://$n" ;;
  esac
  d="$GOPATH/src/$n"
  if [ ! -d "$d/.git" ]; then
    mkdir -p "$(dirname "$d")"
    git clone -q --no-checkout "$url" "$d" >> "$L/deps6278.log" 2>&1 || { echo "CLONEFAIL $n"; continue; }
  fi
  git -C "$d" checkout -q -- . 2>/dev/null
  git -C "$d" checkout -q "$v" >> "$L/deps6278.log" 2>&1 || echo "COFAIL $n $v"
done < /tmp/deps6278.txt
echo "[deps] done"

# 移植补丁自带测试
git show 9497e967:integration/v3_election_test.go \
  | sed -n '/^func TestElectionOnPrefixOfExistingKey/,/^}$/p' >> integration/v3_election_test.go
echo "[port] $(grep -c 'func TestElectionOnPrefixOfExistingKey' integration/v3_election_test.go) test(s) appended"

echo "=== buggy ==="
go test -count=1 -v -run 'TestElectionOnPrefixOfExistingKey' -timeout 300s ./integration > "$L/etcd6278_buggy.log" 2>&1
echo "[buggy] exit=$?"
grep -E "^(=== RUN|--- PASS|--- FAIL|ok|FAIL)|timed out|deadlock|Campaign" "$L/etcd6278_buggy.log" | head -10

git checkout -q -- integration/v3_election_test.go
git checkout -q 9497e967 || exit 8
echo "=== fixed HEAD=$(git rev-parse --short HEAD) ==="
go test -count=1 -v -run 'TestElectionOnPrefixOfExistingKey' -timeout 300s ./integration > "$L/etcd6278_fixed.log" 2>&1
echo "[fixed] exit=$?"
grep -E "^(=== RUN|--- PASS|--- FAIL|ok|FAIL)" "$L/etcd6278_fixed.log" | head -6
