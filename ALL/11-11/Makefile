# 薄封装：所有逻辑都在 run.sh 里，Windows 无 make 时直接跑 ./run.sh
SHELL := /usr/bin/env bash

.PHONY: help setup-repos check-pins parse static compare static-all feasibility audit test clean

help:
	@bash run.sh help

setup-repos:
	@bash run.sh setup-repos

check-pins:
	@bash run.sh check-pins

parse:
	@bash run.sh parse

static:
	@bash run.sh static

compare:
	@bash run.sh compare

static-all:
	@bash run.sh static-all

feasibility:
	@bash run.sh feasibility

audit:
	@bash run.sh audit

test:
	@bash run.sh test

clean:
	@rm -rf results/data/*.json results/logs/_meta
	@echo "[ok] 已清理生成物，data/ 与 results/logs/<case>/ 保留"
