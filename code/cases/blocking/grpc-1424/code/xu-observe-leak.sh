#!/usr/bin/env bash
# grpc#1424 个人实验入口：真实 DialContext 路径下的协程残留观测
#
# 与 xu-run-1229.sh 的关系：
#   本脚本先用 xu-run-1229.sh 在专用源码目录里完成下载/核验/补测试（只跑 1 轮做基线），
#   再把 probe/xu_dialcontext_leak_test.go 原样复制到两侧源码树，用 go test 逐进程跑矩阵。
#   不修改产品代码，不覆盖 logs/xu/1229 已归档的证据。
#
# 实验矩阵（主实验 12 个独立进程 + 对照 12 个 + deadline 6 个）：
#   cancel    N=1,10  各 3 轮   两侧   —— 主实验
#   noblock   N=1,10  各 3 轮   两侧   —— 对照：排除探针自身/清理逻辑造成的残留
#   deadline  N=1     各 3 轮   两侧   —— 补充：外层 deadline 到期的真实路径
#
# 用法:
#   ./xu-observe-leak.sh              跑完整矩阵
#   XU_OBS_FORCE=1 ./xu-observe-leak.sh   覆盖已有输出目录后重跑
#   XU_OBS_JUDGE_ONLY=1 ./xu-observe-leak.sh  不重跑，只对已有归档重算汇总与判定
#
# 可覆盖变量:
#   XU1424_BUGGY / XU1424_FIXED  专用源码目录，默认 $HOME/grpc1424-leak/{buggy,fixed}
#   XU_OBS_LOG                   日志根目录，默认 <case>/logs/xu/leak-observation
#   XU_OBS_RES                   结果根目录，默认 <case>/results/xu/leak-observation
#   XU_WINDOW_MS                 每次调用返回后的观察窗口，默认 200
#   GO1424                       go 可执行文件
#
# 退出码: 0 观测成立（buggy 残留 = N、fixed 与非阻塞对照均为 0、每次调用都已返回）
#         2 buggy 未达到 N（未观测到）  3 fixed 或非阻塞对照仍有残留（对照被破坏）
#         4 源码/构建/环境问题，或有调用未返回（观测链不完整，结果不可用）
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CASE="$(dirname "$HERE")"
BUGGY="${XU1424_BUGGY:-$HOME/grpc1424-leak/buggy}"
FIXED="${XU1424_FIXED:-$HOME/grpc1424-leak/fixed}"
GOBIN="${GO1424:-/usr/local/go-versions/go1.22.9/bin/go}"
OUT="${XU_OBS_LOG:-$CASE/logs/xu/leak-observation}"
RES="${XU_OBS_RES:-$CASE/results/xu/leak-observation}"
PROBE="$CASE/probe/xu_dialcontext_leak_test.go"
WINDOW_MS="${XU_WINDOW_MS:-200}"
ROUNDS="${XU_OBS_ROUNDS:-3}"
JUDGE_ONLY="${XU_OBS_JUDGE_ONLY:-0}"

BUG_SHA=39c8c3866d926d95e11c03508bf83d00f2963f91
FIX_SHA=4e56696c6c5a8cd7b711a1eb8936463559361da5
H_BUG=c4bd8a8bce34ef57a7895048e7eb31b574c8323f088a60d6bc8ca695c132f301
H_FIX=4a1f8173e9c4b25992ccb9dff1a89460c8f1f0823a590110f613e306fa98a3d1

export GO111MODULE=on
export GOFLAGS=-mod=mod
export GOSUMDB=off
export GOPROXY="${GOPROXY:-https://goproxy.cn,direct}"
export GOPATH="${GOPATH:-$HOME/go}"
export GOMODCACHE="${GOMODCACHE:-$HOME/go/pkg/mod}"

PROBE_SHA=""
BUG_FAILS=0
FIX_RESIDUAL=0
BAD=0

log() { echo "$*"; }

# ---------------------------------------------------------------- 准备

check_probe() {
  [ -f "$PROBE" ] || { log "找不到探针: $PROBE"; return 1; }
  PROBE_SHA=$(sha256sum "$PROBE" | cut -d' ' -f1)
  log "  探针 sha256=$PROBE_SHA"
}

prepare_sources() {
  log "== 1/4 用 xu-run-1229.sh 准备源码（1 轮基线）"
  XU1424_BUGGY="$BUGGY" XU1424_FIXED="$FIXED" XU1424_LOGDIR="$OUT/prep-baseline" \
    bash "$HERE/xu-run-1229.sh" 1 60 > /dev/null 2>&1
  local rc=$?
  if [ "$rc" -eq 4 ]; then
    log "  [env] 源码准备失败（rc=4），看 $OUT/prep-baseline/summary.txt"
    return 4
  fi
  [ "$rc" -ne 0 ] && log "  [warn] 基线 rc=$rc（非环境问题，继续）"
  local a b
  a=$(sha256sum "$BUGGY/clientconn.go" | cut -d' ' -f1)
  b=$(sha256sum "$FIXED/clientconn.go" | cut -d' ' -f1)
  [ "$a" = "$H_BUG" ] || { log "  buggy/clientconn.go 与 $BUG_SHA 不符: $a"; return 4; }
  [ "$b" = "$H_FIX" ] || { log "  fixed/clientconn.go 与 $FIX_SHA 不符: $b"; return 4; }
  log "  源码核验通过：buggy=$(cat "$BUGGY/.src_sha")  fixed=$(cat "$FIXED/.src_sha")"
}

install_probe() {
  log "== 2/4 复制探针到两侧源码树"
  local d
  for d in "$BUGGY" "$FIXED"; do
    cp "$PROBE" "$d/xu_dialcontext_leak_test.go" || return 1
    [ "$(sha256sum "$d/xu_dialcontext_leak_test.go" | cut -d' ' -f1)" = "$PROBE_SHA" ] \
      || { log "  $d 探针副本哈希不符"; return 1; }
  done
  log "  两侧探针一致"
}

write_env() {
  {
    echo "case=grpc1424-leak-observation"
    echo "date=$(date -Is)"
    echo "probe=$PROBE"
    echo "probe_sha256=$PROBE_SHA"
    echo "buggy_dir=$BUGGY"
    echo "fixed_dir=$FIXED"
    echo "buggy_sha=$(cat "$BUGGY/.src_sha")"
    echo "fixed_sha=$(cat "$FIXED/.src_sha")"
    echo "window_ms=$WINDOW_MS"
    echo "rounds=$ROUNDS"
    echo "goroot=$(dirname "$(dirname "$GOBIN")")"
    "$GOBIN" version
    echo "uname=$(uname -sr) $(uname -m)"
    sha256sum "$BUGGY/clientconn.go" "$BUGGY/xu_dialcontext_leak_test.go" \
              "$FIXED/clientconn.go" "$FIXED/xu_dialcontext_leak_test.go" \
              "$BUGGY/go.mod" "$BUGGY/go.sum" "$FIXED/go.mod" "$FIXED/go.sum"
  } > "$OUT/env.txt"
}

# ---------------------------------------------------------------- 单个进程

run_one() {  # side mode n round
  local side="$1" mode="$2" n="$3" round="$4"
  local dir="$OUT/$side/$mode/N$n/round$round"
  local rc verdict

  mkdir -p "$dir"
  (
    cd "$( [ "$side" = buggy ] && echo "$BUGGY" || echo "$FIXED" )" || exit 1
    XU_SIDE="$side" XU_MODE="$mode" XU_N="$n" XU_ROUND="$round" \
    XU_OUT="$dir" XU_WINDOW_MS="$WINDOW_MS" \
      timeout $(( n * 3 + 120 )) "$GOBIN" test . -run '^TestXuDialContextLeak$' \
        -count=1 -vet=off -timeout $(( n * 3 + 90 ))s -v > "$dir/stdout.log" 2>&1
  )
  rc=$?

  if grep -q '\[build failed\]' "$dir/stdout.log" 2>/dev/null; then
    verdict=BUILD_ERROR
  elif [ ! -f "$dir/metrics.json" ]; then
    verdict=NO_METRICS
  elif [ "$rc" -ne 0 ]; then
    verdict="TEST_FAIL(rc=$rc)"
  else
    verdict=OK
  fi

  cat > "$dir/env.json" <<EOF
{"version":"$side","source_sha":"$( [ "$side" = buggy ] && cat "$BUGGY/.src_sha" || cat "$FIXED/.src_sha" )","probe_sha256":"$PROBE_SHA","exit_code":$rc,"verdict":"$verdict","raw_log":"$dir/stdout.log"}
EOF

  printf '  %-6s %-8s N=%-2s r=%s  %s\n' "$side" "$mode" "$n" "$round" "$verdict"
  [ "$verdict" = OK ] || BAD=$((BAD+1))
  return 0
}

# ---------------------------------------------------------------- 汇总

build_summary() {
  log "== 4/4 生成 summary.csv"
  mkdir -p "$RES"
  python3 - "$OUT" "$RES/summary.csv" <<'PY'
import csv, glob, json, os, sys

root, out_csv = sys.argv[1], sys.argv[2]
rows = []
for mp in sorted(glob.glob(os.path.join(root, '*', '*', 'N*', 'round*', 'metrics.json'))):
    d = os.path.dirname(mp)
    m = json.load(open(mp, encoding='utf-8'))
    ep = os.path.join(d, 'env.json')
    e = json.load(open(ep, encoding='utf-8')) if os.path.exists(ep) else {}
    per = [c.get('target_stacks_after') for c in m.get('per_call', [])]
    rows.append({
        'version': m.get('version') or e.get('version', ''),
        'source_sha': e.get('source_sha', ''),
        'probe_sha256': e.get('probe_sha256', ''),
        'n': m.get('n'),
        'round': m.get('round'),
        'context_mode': m.get('context_mode', ''),
        'returned_calls': m.get('returned_calls'),
        'context_errors': m.get('context_errors'),
        'target_stacks_before': m.get('target_stacks_before'),
        'target_stacks_after': m.get('target_stacks_after'),
        'observation_window_ms': m.get('observation_window_ms'),
        'exit_code': e.get('exit_code', ''),
        'raw_log': os.path.relpath(e.get('raw_log', d), os.path.dirname(root)),
        'lbwatcher_stacks_after': m.get('lbwatcher_stacks_after'),
        'goroutines_before': m.get('goroutines_before'),
        'goroutines_after': m.get('goroutines_after'),
        'per_call_target_after': '/'.join(str(x) for x in per),
        'verdict': e.get('verdict', ''),
    })

cols = ['version', 'source_sha', 'probe_sha256', 'n', 'round', 'context_mode',
        'returned_calls', 'context_errors', 'target_stacks_before', 'target_stacks_after',
        'observation_window_ms', 'exit_code', 'raw_log',
        'lbwatcher_stacks_after', 'goroutines_before', 'goroutines_after',
        'per_call_target_after', 'verdict']
with open(out_csv, 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    for r in sorted(rows, key=lambda x: (x['context_mode'], x['version'], x['n'], x['round'])):
        w.writerow(r)
print(f"  {len(rows)} 行 -> {out_csv}")

# 判定：cancel/deadline 期望 buggy=n、fixed=0；noblock 期望两侧都 0；
# 每个进程的 N 次调用都必须返回（没返回时"残留数 = N"可能只是卡住，不能当观测成立）。
bad_fix = [r for r in rows if r['context_mode'] != 'noblock' and r['version'] == 'fixed' and r['target_stacks_after']]
weak = [r for r in rows if r['context_mode'] != 'noblock' and r['version'] == 'buggy' and r['target_stacks_after'] != r['n']]
ctrl = [r for r in rows if r['context_mode'] == 'noblock' and r['target_stacks_after']]
not_ret = [r for r in rows if str(r['returned_calls']) != str(r['n'])]
print(f"  对照: fixed 残留 {len(bad_fix)} 行, buggy 未达 N {len(weak)} 行, "
      f"noblock 残留 {len(ctrl)} 行, 调用未全部返回 {len(not_ret)} 行")
with open(os.path.join(os.path.dirname(out_csv), 'verdict.txt'), 'w') as f:
    f.write(f"bad_fix={len(bad_fix)}\nweak={len(weak)}\nctrl={len(ctrl)}\n"
            f"not_returned={len(not_ret)}\nrows={len(rows)}\n")
sys.exit(0)
PY
}

print_table() {
  python3 - "$RES/summary.csv" <<'PY'
import csv, sys
rows = list(csv.DictReader(open(sys.argv[1], encoding='utf-8')))
w = max(len(r['verdict']) for r in rows) if rows else 8
print(f"  {'version':8s} {'mode':9s} {'N':>2s} {'round':>5s} {'returned':>8s} {'target':>6s} {'g':>7s}  verdict")
for r in rows:
    print(f"  {r['version']:8s} {r['context_mode']:9s} {r['n']:>2s} {r['round']:>5s} "
          f"{r['returned_calls']:>8s} {r['target_stacks_after']:>6s} "
          f"{r['goroutines_before']+'->'+r['goroutines_after']:>7s}  {r['verdict']}")
PY
}

# ---------------------------------------------------------------- 验收

# 三项都必须满足才算观测成立：缺陷版达到 N、修复版为 0、非阻塞对照为 0，
# 且每个进程的 N 次调用全部返回（没返回时残留数不可信）。
finish() {
  local vf="$RES/verdict.txt"
  if [ -f "$vf" ]; then
    # shellcheck disable=SC1090
    . "$vf"
    FIX_RESIDUAL="${bad_fix:-0}"
    BUG_FAILS="${weak:-0}"
    CTRL_RESIDUAL="${ctrl:-0}"
    NOT_RETURNED="${not_returned:-0}"
  else
    FIX_RESIDUAL=0; BUG_FAILS=0; CTRL_RESIDUAL=0; NOT_RETURNED=1
  fi
  echo "  ---"
  print_table

  local rc result
  if [ "$BAD" -gt 0 ]; then
    result="ENV_ERROR"; rc=4
  elif [ "$NOT_RETURNED" -gt 0 ]; then
    # 有调用没返回：残留数不可信，不能算作观测成立
    result="INCOMPLETE"; rc=4
  elif [ "$FIX_RESIDUAL" -gt 0 ]; then
    result="FIXED_RESIDUAL"; rc=3
  elif [ "$CTRL_RESIDUAL" -gt 0 ]; then
    result="CONTROL_RESIDUAL"; rc=3
  elif [ "$BUG_FAILS" -gt 0 ]; then
    result="NOT_OBSERVED"; rc=2
  else
    result="OBSERVED"; rc=0
  fi
  echo "############ RESULT: $result"
  echo "############ DONE grpc1424-leak-observation"
  return "$rc"
}

# ---------------------------------------------------------------- 主流程

main() {
  echo "############ grpc1424 真实 DialContext 协程残留观测  window=${WINDOW_MS}ms  rounds=$ROUNDS"

  if [ "$JUDGE_ONLY" = "1" ]; then
    log "== 只判定：不重跑，直接对 $OUT 的归档重算汇总"
    build_summary || return 4
    finish
    return $?
  fi

  [ -x "$GOBIN" ] || { log "找不到 go: $GOBIN（用 GO1424 指定）"; return 4; }
  mkdir -p "$OUT" "$RES" || return 4

  check_probe || return 4
  prepare_sources || return $?
  install_probe || return 4
  write_env

  log "== 3/4 跑矩阵"
  local mode n r
  for mode in cancel noblock; do
    for n in 1 10; do
      for r in $(seq 1 "$ROUNDS"); do
        run_one buggy "$mode" "$n" "$r"
        run_one fixed "$mode" "$n" "$r"
      done
    done
  done
  for r in $(seq 1 "$ROUNDS"); do
    run_one buggy deadline 1 "$r"
    run_one fixed deadline 1 "$r"
  done

  build_summary || return 4
  finish
}

# 目录先建好并做非空检查：tee 会在 main 启动前就创建 summary.txt，
# 所以「是否已有归档」必须在开启管道之前判断。
mkdir -p "$OUT" "$RES" || { echo "无法创建输出目录: $OUT"; exit 4; }

# 只判定模式：对已有归档重算，不重跑，也不覆盖归档里的 summary.txt
if [ "$JUDGE_ONLY" = "1" ]; then
  main
  exit $?
fi

if [ -n "$(ls -A "$OUT" 2>/dev/null)$(ls -A "$RES" 2>/dev/null)" ] && [ "${XU_OBS_FORCE:-0}" != "1" ]; then
  echo "输出目录已有内容: $OUT"
  echo "确需重跑请加 XU_OBS_FORCE=1（只清空本实验子目录，不碰 logs/xu/1229）"
  exit 4
fi
if [ "${XU_OBS_FORCE:-0}" = "1" ]; then
  rm -rf "${OUT:?}"/* "${RES:?}"/*
  echo "已清空本实验目录（XU_OBS_FORCE=1）"
fi

main 2>&1 | tee "$OUT/summary.txt"
rcs=("${PIPESTATUS[@]}")
rc=${rcs[0]}
tee_rc=${rcs[1]:-0}
if [ "$tee_rc" -ne 0 ]; then
  echo "写 $OUT/summary.txt 失败，本次记录不完整（main 退出码 $rc）" >&2
  exit 4
fi
exit "$rc"
