#!/usr/bin/env bash
# 统一入口。Windows 上没有 make 也能用，因此以本脚本为准；
# Makefile 只是同一套目标的薄封装。
#
#   ./run.sh help
#   ./run.sh setup-repos     克隆 6 个上游仓库并对齐论文 commit
#   ./run.sh check-pins      校验仓库是否停在 data/repo.lock.tsv 的 commit
#   ./run.sh parse           artifact -> data/*.csv
#   ./run.sh static          6 仓库 AST 统计 -> results/data/
#   ./run.sh compare         与论文 Table 2/4 逐格对照
#   ./run.sh feasibility     41 条目标 bug 可行性分级
#   ./run.sh repro grpc-793  单条 bug 的 buggy/fixed 对照
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
ROOT="$(pwd)"
# shellcheck disable=SC1091
source code/analysis/_paths.sh

if command -v python3 >/dev/null 2>&1; then
  PY="${PYTHON:-python3}"
else
  PY="${PYTHON:-python}"
fi

UNTIL="${UNTIL:-2018-05-21}"
APPS=(boltdb etcd grpc-go docker cockroachdb kubernetes)
A="$ROOT/code/analysis"

usage() {
  cat <<'EOF'
统一入口（Windows 无 make 也可用；Makefile 是同一套目标的薄封装）

  ./run.sh help                 显示本说明
  ./run.sh setup-repos          克隆 6 个上游仓库并精确对齐论文 commit（约 430MB）
  ./run.sh check-pins           校验仓库是否停在 data/repo.lock.tsv 记录的 commit
  ./run.sh parse                artifact -> data/*.csv
  ./run.sh env-report           环境与快照汇总 -> results/data/p0_env_report.md
  ./run.sh goast                编译 Go AST 统计器到 $BIN_DIR
  ./run.sh mine                 P1 关键词挖掘（UNTIL 默认 2018-05-21）
  ./run.sh static               P2 静态原语统计（6 个仓库）
  ./run.sh compare              P2 与论文 Table 2/4 逐格对照
  ./run.sh static-all           static + compare
  ./run.sh feasibility          P4 前置：41 个目标 bug 可行性表
  ./run.sh audit                bug 表一致性审计
  ./run.sh repro <case>         单条 bug 复现，case 见 code/cases/ 目录名
  ./run.sh logs                 grpc 四条的一键日志归集（虚机内执行）

可用环境变量: REPO_ROOT ARTIFACT_DIR DATA_DIR OUT_DIR BIN_DIR GO_MODERN PYTHON UNTIL
EOF
}

case "${1:-help}" in
  help|-h|--help) usage ;;

  setup-repos)
    bash "$A/00_setup_repos.sh"
    echo
    bash "$A/00_pin_exact.sh"
    ;;

  check-pins)  "$PY" "$A/check_pins.py" ;;

  parse)       "$PY" "$A/00_parse_artifact.py" --artifact "$ARTIFACT_DIR" ;;

  env-report)  "$PY" "$A/00_env_report.py" ;;

  test)
    "$PY" "$A/check_pins.py" || exit 1
    "$PY" "$A/00_parse_artifact.py" --artifact "$ARTIFACT_DIR" || exit 1
    echo "[ok] 冒烟测试通过"
    ;;

  goast)
    if [[ -z "${GO_MODERN:-}" ]]; then
      echo "[x] 未找到 go。请在 code/analysis/local.env 里设置 GO_MODERN，或把 go 放进 PATH。" >&2
      exit 1
    fi
    ext=""
    case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) ext=".exe" ;; esac
    mkdir -p "$BIN_DIR"
    ( cd "$ROOT/code/tools" && "$GO_MODERN" build -o "$BIN_DIR/goast$ext" ./goast ) \
      && echo "[ok] $BIN_DIR/goast$ext"
    ;;

  mine)
    for app in "${APPS[@]}"; do
      echo "=== $app ==="
      "$PY" "$A/01_mine_commits.py" \
        --repo "$REPO_ROOT/$app" --app "$app" \
        --until "$UNTIL" --out "$OUT_DIR/commits_${app}.csv" --calibrate || echo "[!] $app 失败"
    done
    ;;

  static)
    for app in "${APPS[@]}"; do
      echo "=== $app ==="
      "$PY" "$A/02_static_metrics.py" \
        --repo "$REPO_ROOT/$app" --app "$app" \
        --goast-cmd "${BIN_DIR}/goast" \
        --out "$OUT_DIR/static_${app}.json" || echo "[!] $app 失败"
    done
    ;;

  compare)
    "$PY" "$A/03_compare_paper.py" \
      --static-dir "$OUT_DIR" --out "$OUT_DIR/table2_table4_compare.md"
    ;;

  static-all) bash "$0" static && bash "$0" compare ;;

  feasibility)
    "$PY" "$A/06_feasibility.py" \
      --bugs "$DATA_DIR/bugs_master.csv" \
      --artifact "$ARTIFACT_DIR" --repos "$REPO_ROOT" \
      --commits-dir "$OUT_DIR" \
      --out-data "$DATA_DIR/feasibility_44.csv" \
      --out-report "$OUT_DIR/p4_feasibility_report.md"
    ;;

  audit)
    "$PY" "$A/07_audit_bug_table.py" \
      --data-dir "$DATA_DIR" --report "$OUT_DIR/bug_table_audit.md"
    ;;

  repro)
    case="${2:?用法: ./run.sh repro <case>  （如 grpc-793）}"
    runner="$ROOT/code/cases/$case/run.sh"
    [[ -x "$runner" || -f "$runner" ]] || { echo "[x] 没有这个 case: $case" >&2; exit 1; }
    shift 2
    bash "$runner" "$@"
    ;;

  logs)
    bash "$ROOT/code/harness/p4_grpc_logs.sh"
    ;;

  *)
    echo "[x] 未知目标: $1" >&2
    usage
    exit 1
    ;;
esac
