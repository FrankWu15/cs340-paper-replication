#!/usr/bin/env bash
# 构建 / 运行入口。Windows 上没有 make 也能用，因此以这个脚本为准；
# Makefile 只是同一套目标的薄封装。
#
#   ./run.sh help
#   ./run.sh setup-repos
#   ./run.sh check-pins
#   ./run.sh parse
#   ./run.sh env-report
#   ./run.sh goast
#   ./run.sh mine          # 6 个仓库批量关键词挖掘（--until 可覆盖）
#   ./run.sh static        # 6 个仓库批量静态统计
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
# shellcheck disable=SC1091
source repro/scripts/_paths.sh

if command -v python3 >/dev/null 2>&1; then
  PY="${PYTHON:-python3}"
else
  PY="${PYTHON:-python}"
fi

UNTIL="${UNTIL:-2018-05-21}"
APPS=(boltdb etcd grpc-go docker cockroachdb kubernetes)

usage() {
  cat <<'EOF'
构建 / 运行入口（Windows 无 make 也可用；Makefile 是同一套目标的薄封装）

  ./run.sh help                 显示本说明
  ./run.sh setup-repos          克隆 6 个上游仓库并精确对齐论文 commit（~430MB）
  ./run.sh check-pins           校验仓库是否停在 repo.lock.tsv 记录的 commit
  ./run.sh parse                artifact -> repro/data/*.csv
  ./run.sh env-report           环境与快照汇总 -> repro/out/p0_env_report.md
  ./run.sh goast                编译 Go AST 统计器到 $BIN_DIR
  ./run.sh mine                 P1 关键词挖掘（6 个仓库，UNTIL 默认 2018-05-21）
  ./run.sh static               P2 静态原语统计（6 个仓库）
  ./run.sh compare              P2 与论文 Table 2/4 逐格对照
  ./run.sh static-all           static + compare
  ./run.sh feasibility          P4 前置：41 个目标 bug 可行性表
  ./run.sh audit                bug 表一致性审计（41 vs 44 口径、空白来源）

可用环境变量: REPO_ROOT LOG_DIR OUT_DIR BIN_DIR GO_MODERN GO_LEGACY PYTHON UNTIL
EOF
}

case "${1:-help}" in
  help|-h|--help)
    usage
    ;;

  setup-repos)
    bash repro/scripts/00_setup_repos.sh
    echo
    bash repro/scripts/00_pin_exact.sh
    ;;

  check-pins)
    "$PY" repro/scripts/check_pins.py
    ;;

  test)
    "$PY" repro/scripts/check_pins.py || exit 1
    "$PY" repro/scripts/00_parse_artifact.py || exit 1
    echo "[ok] 冒烟测试通过"
    ;;

  parse)
    "$PY" repro/scripts/00_parse_artifact.py
    ;;

  env-report)
    "$PY" repro/scripts/00_env_report.py
    ;;

  goast)
    if [[ -z "${GO_MODERN:-}" ]]; then
      echo "[x] 未找到 go。请在 repro/local.env 里设置 GO_MODERN，或把 go 放进 PATH。" >&2
      exit 1
    fi
    # Windows 上必须带 .exe，否则 CreateProcess 找不到
    ext=""
    case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) ext=".exe" ;; esac
    mkdir -p "$BIN_DIR"
    ( cd repro && "$GO_MODERN" build -o "$BIN_DIR/goast$ext" ./tools/goast ) \
      && echo "[ok] $BIN_DIR/goast$ext"
    ;;

  mine)
    mkdir -p "$OUT_DIR"
    for app in "${APPS[@]}"; do
      echo "=== $app ==="
      "$PY" repro/scripts/01_mine_commits.py \
        --repo "$REPO_ROOT/$app" --app "$app" \
        --until "$UNTIL" --out "$OUT_DIR/commits_${app}.csv" --calibrate || echo "[!] $app 失败"
    done
    ;;

  static)
    mkdir -p "$OUT_DIR"
    for app in "${APPS[@]}"; do
      echo "=== $app ==="
      "$PY" repro/scripts/02_static_metrics.py \
        --repo "$REPO_ROOT/$app" --app "$app" \
        --goast-cmd "${BIN_DIR}/goast" \
        --out "$OUT_DIR/static_${app}.json" || echo "[!] $app 失败"
    done
    ;;

  compare)
    "$PY" repro/scripts/03_compare_paper.py \
      --static-dir "$OUT_DIR" --out "$OUT_DIR/table2_table4_compare.md"
    ;;

  feasibility)
    "$PY" repro/scripts/06_feasibility.py \
      --bugs repro/data/bugs_master.csv \
      --artifact go-concurrency-bugs-master --repos "$REPO_ROOT" \
      --commits-dir "$OUT_DIR" \
      --out-data repro/data/feasibility_44.csv \
      --out-report "$OUT_DIR/p4_feasibility_report.md"
    ;;

  audit)
    "$PY" repro/scripts/07_audit_bug_table.py \
      --data-dir repro/data \
      --report "$OUT_DIR/bug_table_audit.md"
    ;;

  static-all)
    bash "$0" static && bash "$0" compare
    ;;

  *)
    echo "[x] 未知目标: $1" >&2
    usage
    exit 1
    ;;
esac
