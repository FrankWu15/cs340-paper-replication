# analysis —— P0–P2 分析脚本

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
