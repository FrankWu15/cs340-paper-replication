#!/usr/bin/env bash
# 拉取两个 case 所需的源码快照，并按 GOPATH 布局放好
#
# 用法：
#   bash setup.sh
#
# 环境变量：
#   WORK      工作目录，默认 ./_work
#   GOPROXY   源码下载代理前缀，默认 https://ghproxy.net/
#             如果本机可直连 GitHub，把 GOPROXY 设为空字符串即可
set -euo pipefail

WORK="${WORK:-$PWD/_work}"
PREFIX="${GOPROXY-https://ghproxy.net/}"

# case 目录名 : buggy commit : fixed commit
CASES=(
  "02-close-race:55af28c19cd84431e1f3c5b132a07c1deecff10b:e929eba364732aa3a7eb76e2c9c38b7d23b8a980"
  "03-begin-lock-leak:01bc9be72f46f0f1978b1f1581440c399b3a7684:defdb743cdca840890fea24c3111a7bffe5cc0a3"
)

fetch_zip() {  # $1=owner/repo  $2=sha  $3=目标目录
  local repo=$1 sha=$2 dst=$3
  if [ -f "$dst/db.go" ]; then
    echo "  已存在，跳过"
    return 0
  fi
  local tmp; tmp=$(mktemp -d)
  local url="${PREFIX}https://github.com/$repo/archive/$sha.zip"
  echo "  下载 $repo@${sha:0:8}"
  if ! curl -fsSL --retry 2 -o "$tmp/a.zip" "$url"; then
    echo "  下载失败：$url" >&2
    echo "  如果你能直连 GitHub，试试：GOPROXY= bash setup.sh" >&2
    rm -rf "$tmp"; return 1
  fi
  unzip -q -o "$tmp/a.zip" -d "$tmp/x"
  mkdir -p "$dst"
  cp -r "$tmp"/x/*/. "$dst"/
  rm -rf "$tmp"
}

mkdir -p "$WORK"

for line in "${CASES[@]}"; do
  name=${line%%:*}; rest=${line#*:}
  buggy=${rest%%:*}; fixed=${rest#*:}
  echo "=== $name ==="
  for variant in buggy fixed; do
    if [ "$variant" = buggy ]; then sha=$buggy; else sha=$fixed; fi
    gp="$WORK/$name/$variant"
    echo " [$variant]"
    fetch_zip boltdb/bolt "$sha" "$gp/src/github.com/boltdb/bolt"
    echo "$sha" > "$gp/SHA"
  done
done

echo
echo "完成。源码位于 $WORK"
