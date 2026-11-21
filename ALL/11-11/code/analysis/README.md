# analysis —— P0–P2 分析脚本

全部通过 `_paths.sh` 解析路径，不写死绝对路径。入口在仓库根的 `run.sh` / `Makefile`。

## 按阶段

| 阶段 | 文件 | 作用 |
|---|---|---|
| P0 | `00_setup_repos.sh` | 克隆 6 个仓库（支持 `--filter=tree:0` 拉大树） |
| P0 | `00_pin_exact.sh` | 沿 first-parent 回退，找到 commit 数与论文完全相等的提交 |
| P0 | `check_pins.py` | 校验当前 HEAD 是否等于 `data/repo.lock.tsv` |
| P0 | `00_parse_artifact.py` | artifact 的 169 个补丁 → `data/*.csv` |
| P0 | `00_env_report.py` | 工具链、磁盘、仓库状态汇总 |
| P1 | `01_mine_commits.py` | 用并发关键词过滤 commit 历史 |
| P2 | `02_static_metrics.py` | 调 `goast` 统计并发原语，按 KLOC 归一化 |
| P2 | `03_compare_paper.py` | 与论文 Table 2 / Table 4 逐格对照 |
| P4 | `06_feasibility.py` | 44 行 → 41 条目标的 A/B/C 分级 |
| P4 | `07_audit_bug_table.py` | 总表与 artifact 原表的一致性审计 |

## 环境

机器相关配置写在 `local.env`（不入库），模板见 `local.env.example`：

```bash
cp code/analysis/local.env.example code/analysis/local.env
```

不填也能跑，会退回 PATH 里的 `go`，二进制放系统临时目录。

## 上游仓库与 artifact

两者都很大、不入库。查找顺序：环境变量 → `local.env` → `<root>/6app`、`<root>/artifact`
→ 同级的 `../6app`、`../go-concurrency-bugs-master`。

## Windows 注意事项

`goast` 必须编译成 `.exe`，否则 Go 的 `os/exec` 找不到；`run.sh goast` 已处理。
自编译的 exe 不要放桌面目录，Windows 会报 `winapi error #5`，脚本默认放 `$TMPDIR`。
