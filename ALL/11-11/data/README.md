# data —— 输入数据（只读）

脚本的输入，全部由 `make parse` 或人工整理产生，**不要手工改**。
重新生成：`make parse`（依赖论文 artifact，见 `_paths.sh` 里的 `ARTIFACT_DIR`）。

| 文件 | 行数 | 来源 | 内容 |
|---|---|---|---|
| `repo.lock.tsv` | 6 | 人工校准 | 6 仓库的 URL 与论文 commit |
| `artifact_manifest.csv` | 170 | artifact 原表 | 论文给出的 bug 清单 |
| `bug_table_application.csv` | 7 | 论文 Table 1 | 6 个项目的 Stars / LOC / bug 数 |
| `bug_table_blocking.csv` | 86 | 论文 Table 5 上半 | 阻塞类 bug 明细 |
| `bug_table_non_blocking.csv` | 87 | 论文 Table 5 下半 | 非阻塞类 bug 明细 |
| `bugs_master.csv` | 172 | 上面两张表合并 | 全量总表（171 条 bug） |
| `feasibility_44.csv` | 45 | `make feasibility` | 44 行目标的 A/B/C 分级 |
| `repro_targets.csv` | 45 | `make parse` | 最终选定的复现目标 |

## 两个容易误会的点

**41 条不是 41 行。** `Reproduced?=1` 的集合去重后是 41 条 bug，对应 CSV 里的 44 行，
差额是 `etcd#4876` 占了 4 行（同一 bug 的多个修复点）。

**`feasibility_44.csv` 会被 `make feasibility` 覆盖。** 它是脚本产出，不是手工数据；
要改分级口径请改脚本，不要直接编辑这个文件。

**重跑前必须先 `make mine`。** `06_feasibility.py` 靠 `results/data/commits_*.csv`
判断某个修复提交是否落在候选集里（`in_repo` 列）。这些文件不存在时该列会全部算成 0，
A/B/C 分布虽不变（仍是 A=14 B=28 C=2），但 `in_repo` 会从 42/44 掉到 2/44，
而且会**直接覆盖**本目录里的表。重跑前先备份，或先补上 P1 的输出。
