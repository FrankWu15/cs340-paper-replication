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

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"

case "$CASE" in
  02|02-close-race)
    DIR=02-close-race
    SRC="$ROOT/code/cases/non-blocking/boltdb-341/code/main.go" ;;
  03|03-begin-lock-leak)
    DIR=03-begin-lock-leak
    SRC="$ROOT/code/cases/blocking/boltdb-begin-lock-leak/code/main.go" ;;
  *) echo "未知 case: $CASE"; exit 1 ;;
esac
[ -f "$SRC" ] || { echo "缺少触发程序: $SRC"; exit 1; }

WORK="${WORK:-$HERE/_work}"
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
cp "$SRC" "$GP/src/repro/main.go"
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
