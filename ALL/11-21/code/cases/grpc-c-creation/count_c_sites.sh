#!/bin/bash
# 统计 gRPC-C 的线程创建点（对应论文 Table 2 的 gRPC-C 一行）
# 用法: count_c_sites.sh <grpc源码根目录>
set -u
R=${1:?need grpc source dir}
cd "$R" || exit 9

echo "## 1. 物理线程创建 API（严格口径）"
echo "pthread_create:"
grep -rn "pthread_create" src include --include=*.c --include=*.cc --include=*.h --include=*.hpp 2>/dev/null | grep -v third_party | sed 's/^/  /'
echo "CreateThread:"
grep -rn "CreateThread" src include --include=*.c --include=*.cc --include=*.h --include=*.hpp 2>/dev/null | grep -v third_party | sed 's/^/  /'
echo "std::thread 构造（产品代码 src/）:"
grep -rn "std::thread(\|new std::thread" src --include=*.cc --include=*.h 2>/dev/null | grep -v third_party | sed 's/^/  /'

echo
echo "## 2. gRPC 自有线程封装 gpr_thd_new 的调用点"
grep -rn "gpr_thd_new" src --include=*.c --include=*.cc --include=*.h 2>/dev/null | grep -v third_party | sed 's/^/  /'

echo
echo "## 3. 代码行数（.c/.cc/.h/.hpp）"
cnt(){ find "$1" -type f \( -name "*.c" -o -name "*.cc" -o -name "*.h" -o -name "*.hpp" \) -print0 2>/dev/null | xargs -0 cat 2>/dev/null | wc -l; }
echo "src/all      $(cnt src)"
echo "src/core     $(cnt src/core)"
echo "src/cpp      $(cnt src/cpp)"
echo "include      $(cnt include)"
echo "src+include  $(( $(cnt src) + $(cnt include) ))"
