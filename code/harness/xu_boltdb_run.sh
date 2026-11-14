#!/usr/bin/env bash
# 运行某个 case 的 buggy / fixed 版本
#
# 用法：
#   bash run.sh <case> <buggy|fixed> [--race] [程序参数...]
#
#   case 取值：02 | 03（或写全名 02-close-race 等）
#   --race    用 -race 编译运行（case 03 触发 deadlock 时不要加，原因见其 README）
#
# 环境变量：
#   WORK     工作目录，默认 ./_work
#   GOROOT   Go 1.6.4 的根目录，默认 /usr/local/go-versions/go1.6.4
set -euo pipefail

CASE=${1:-}; VARIANT=${2:-}
if [ -z "$CASE" ] || [ -z "$VARIANT" ]; then
  echo "用法: bash run.sh <02|03> <buggy|fixed> [--race] [参数...]"; exit 1
fi
shift 2

RACE=0
if [ "${1:-}" = "--race" ]; then RACE=1; shift; fi

case "$CASE" in
  02|02-close-race)      DIR=02-close-race ;;
  03|03-begin-lock-leak) DIR=03-begin-lock-leak ;;
  *) echo "未知 case: $CASE"; exit 1 ;;
esac

WORK="${WORK:-$PWD/_work}"
GOROOT="${GOROOT:-/usr/local/go-versions/go1.6.4}"
GP="$WORK/$DIR/$VARIANT"
export GOROOT
export GOPATH="$GP"
export PATH="$GOROOT/bin:$PATH"

if [ ! -d "$GP/src/github.com/boltdb/bolt" ]; then
  echo "缺少源码，请先执行: bash setup.sh"; exit 1
fi

echo "=== $DIR / $VARIANT (commit $(cat "$GP/SHA" 2>/dev/null | cut -c1-12)) ==="
echo "GOROOT=$GOROOT"
go version

mkdir -p "$GP/src/repro"
cp "$(dirname "$0")/cases/$DIR/main.go" "$GP/src/repro/main.go"
cd "$GP/src/repro"

if [ "$RACE" = "1" ]; then
  echo "--- 编译 (-race) ---"
  go build -race -o repro main.go
else
  echo "--- 编译 ---"
  go build -o repro main.go
fi

echo "--- 运行 ---"
set +e
"./repro" "$@"
rc=$?
set -e
echo "退出码: $rc"
exit $rc
