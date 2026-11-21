# analysis —— P0–P6 分析脚本

论文复现的前半段：把「论文说了什么」变成能核对的数字。脚本按流水线编号，
`_paths.sh` 提供路径与 Go 工具链变量，`local.env` 可覆盖。

| 脚本 | 做什么 | 产出 |
|---|---|---|
| `00_parse_artifact.py` | 解析官方 artifact（`bug table.xlsx` 等），导出 bug 表 | `data/bug_table_{blocking,non_blocking,application}.csv`、`bugs_master.csv` |
| `00_env_report.py` | 记录环境快照（Go 版本、内核、工具链路径） | 环境记录 |
| `01_mine_commits.py` | 从 6 个仓库的 commit 历史里按关键词筛并发缺陷 | 候选提交集 |
| `02_static_metrics.py` | 调 `code/tools/goast` 统计 5 类同步原语（mutex/chan/atomic/waitgroup/cond） | 每仓库 LOC、per-KLOC、原语计数 |
| `03_compare_paper.py` | 与论文 Table/Figure 的数字比对 | 差异表（见 `report/appendix/p2_static.md`） |
| `06_feasibility.py` | 44 条目标的可行性筛选（能不能在本机复现） | `data/feasibility_44.csv` |
| `07_audit_bug_table.py` | 审计 bug 表：`Reproduced?` 三值统计、空行来源 | 审计结论（见 `p1_limitation.md`） |
| `check_pins.py` | 校验 6 仓库 commit 数是否与论文一致 | 通过/不通过 |
| `04_lifecycle.py` | 由申报/修复时间算 bug 生命周期 CDF（论文 Figure 4） | `data/bug_lifetime.csv`、`data/lifecycle_cdf.csv`、`report/figures/fig4_bug_lifetime.svg` |
| `05_stats_figures.py` | 从 artifact one-hot 表重算 Table 6/7/9/10/11 与两组 lift，内置论文数字自检（任一格不符非零退出） | `data/tables/*.csv`、`report/appendix/tables_6_11.md` |
| `08_evolution.py` | 6 应用 × 14 季度采样，统计原语比例随时间的演化（Figure 2/3 的自测数据） | `data/evolution_primitive_usage.csv` |
| `09_fig23.py` | 反解论文 PDF 的矢量曲线并插值到 14 个刻度，与我们的实测画在同一张图（辅助脚本 `extract_fig23.py`） | `report/figures/fig{2,3}_*.svg`、`data/fig23_compare.csv` |

## 三个测量子目录（论文 §3.1 / §3.2 的 C 侧对照）

不与 Go 侧流水线混号，各自一个目录，内含脚本、原始输出与说明：

| 目录 | 做什么 | 产出 |
|---|---|---|
| `grpc-c-creation/` | 数 gRPC-C 线程创建点，验证 Table 2 第七行的 5 与 0.03/KLOC | 创建点清单、版本敏感性（v1.10/1.11/1.12/1.20） |
| `grpc-c-primitives/` | 数 gRPC-C 的 `gpr_mu_*` 调用，验证 §3.2 的 746 | 746 精确命中，C vs Go 对照表 |
| `table3-dynamic/` | 实测运行时 goroutine 数，验证 Table 3 的 201.46 比值 | 1000 并发 → 1019 goroutine，比值 5.06 |

## 已知结论（这三条别再重算）

- P1 的 3,105 与论文 3,211 **只是数字接近**，不是复现了筛选漏斗：44 个补丁 commit 里只有 34 个
  落在候选集，全文口径重算得 4,544（高 41%），说明论文还有未写明的过滤条件。
- bug 表 89 行空白**不是缺失**：原表 `Reproduced?` 本就三值（1 有 44 行、0 有 38 行、空白 89 行），
  填 0 会凭空造出 89 条假记录。对外口径统一为「41 个已复现 bug，对应 44 个补丁 commit」。
- A 档不等于能跑：`boltdb#341` 是 A 档，但补丁自带测试完全无效（`TestDB.Close()` 劫持了
  `bolt.DB.Close()`），只能用独立探针。判据见 `code/cases/non-blocking/boltdb-341/`。

## 依赖

Python 3（`openpyxl`）、`code/tools/goast`（`go build ./...` 后放 `bin/`）。
跑之前先 `00_setup_repos.sh` + `00_pin_exact.sh` 把 6 个仓库钉到论文 commit。
