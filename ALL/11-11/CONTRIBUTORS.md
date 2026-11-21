# 贡献记录

去掉了按学号分层后，路径不再能区分谁做了什么，这份表就是唯一的归属记录。
新完成一项就补一行，`首次提交` 填该内容第一次进入仓库的 commit 短 SHA。

## 分析阶段

| 模块 | 内容 | 负责人 | 首次提交 |
|---|---|---|---|
| P0 环境固定 | `00_setup_repos.sh`、`00_pin_exact.sh`、`repo.lock.tsv` | 李振炜 icecream1293 | — |
| P0 artifact 解析 | `00_parse_artifact.py`，171 行 bug 总表 | 李振炜 icecream1293 | — |
| P1 关键词筛选 | `01_mine_commits.py` | 李振炜 icecream1293 | — |
| P2 静态统计 | `goast` + `02_static_metrics.py` | 李振炜 icecream1293 | — |
| P2 论文对照 | `03_compare_paper.py`，Table 2 / Table 4 | 李振炜 icecream1293 | — |
| P4 可行性分级 | `06_feasibility.py`，41 条 A/B/C | 李振炜 icecream1293 | — |
| P4 表一致性审计 | `07_audit_bug_table.py` | 李振炜 icecream1293 | — |
| P4 通用驱动 | `p4_case.sh`、`p4_deps.sh`、`p4_logs.sh` | 李振炜 icecream1293 | — |

## Bug 复现

| case | 症状 | 负责人 | 首次提交 |
|---|---|---|---|
| `boltdb-341` | `Close()` 提前返回 | 李振炜 icecream1293（探针）、许汝轩 Semliii（并行验证） | — |
| `boltdb-392` | mmap 竞态 | 吴德诚 FrankWu15 | — |
| `boltdb-194` | `beginTx` 漏解锁 | 许汝轩 Semliii | — |
| `boltdb-7fb06fee` | 并发读写 meta 撕裂 | 李振炜 icecream1293 | — |
| `grpc-793` | 二次 GracefulStop 自死锁 | 李振炜 icecream1293 | — |
| `grpc-1293` | 删除在途流不通知 | 李振炜 icecream1293 | — |
| `grpc-1424` | `doneChan` 永不关闭 | 李振炜 icecream1293（复现）、许汝轩 Semliii（独立验证） | — |
| `grpc-1687` | `send on closed channel` | 李振炜 icecream1293 | — |
| `moby-17176` | devmapper 漏解锁 | 朱奕铭 DreamingZhu111 | — |

## 报告

| 章节 | 负责人 | 状态 |
|---|---|---|
| 01 引言 | 待定 | 未开始 |
| 02 方法 | 李振炜 icecream1293 | 草稿 |
| 03 静态统计 | 李振炜 icecream1293 | 草稿 |
| 04 bug 复现 | 全员 | 未开始 |
| 05 检测器评测 | 待定 | 未开始 |
| 06 局限 | 待定 | 未开始 |
