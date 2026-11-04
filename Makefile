# Replication of "Understanding Real-World Concurrency Bugs in Go" (ASPLOS'19)
#
# 所有目标都委托给 run.sh，保证 Windows（无 make）与 Linux 行为一致。
# Linux / macOS / CI 用 make；Windows 上直接 ./run.sh <target>。

SHELL := /usr/bin/env bash
RUN   := bash run.sh

.DEFAULT_GOAL := help
.PHONY: help setup-repos check-pins parse env-report goast mine static test clean

help:            ## 显示所有目标
	@$(RUN) help

setup-repos:     ## 克隆 6 个上游仓库并精确对齐论文的 commit
	@$(RUN) setup-repos

check-pins:      ## 校验仓库停留在 repo.lock.tsv 记录的 commit
	@$(RUN) check-pins

parse:           ## artifact -> repro/data/*.csv
	@$(RUN) parse

env-report:      ## 环境与快照汇总 -> repro/out/p0_env_report.md
	@$(RUN) env-report

goast:           ## 编译 Go AST 统计器到 $(BIN_DIR)
	@$(RUN) goast

mine:            ## P1 关键词挖掘（6 个仓库）
	@$(RUN) mine

static:          ## P2 静态原语统计（6 个仓库）
	@$(RUN) static

test: check-pins parse ## 冒烟测试：commit 对齐 + artifact 解析
	@echo "[ok] 冒烟测试通过"

clean:           ## 清理生成的报告与中间结果（保留 data/ 与 logs/）
	@rm -f repro/out/*.json repro/out/commits_*.csv
	@echo "[ok] 已清理 repro/out 下的中间结果"
