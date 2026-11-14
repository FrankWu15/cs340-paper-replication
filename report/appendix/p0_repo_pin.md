# P0 · 仓库固定与 artifact 校验

## 1. 六个仓库精确对齐论文（切点 2018-05-21）

`--before` 是左闭右开，论文的计数落在 5-20 结束与 5-21 全天之间，说明取样时点是 5-21 当天。
用 `code/repro/scripts/00_pin_exact.sh` 沿 first-parent 回溯 `rev-list --count`，逐仓库定位到计数与论文相等的 commit：

| 项目        | commit         | 日期       | commit 数 | 论文  | 差异 |
|-------------|----------------|------------|-----------|-------|------|
| boltdb      | `fd01fc79c553` | 2018-03-02 |       816 |   816 |   +0 |
| etcd        | `346589edd1dc` | 2018-05-21 |     14101 | 14101 |   +0 |
| grpc-go     | `f66923519395` | 2018-05-21 |      2528 |  2528 |   +0 |
| docker      | `9bd5d9912f0c` | 2018-05-22 |     35149 | 35149 |   +0 |
| cockroachdb | `cc4511e1be86` | 2018-05-22 |     29485 | 29485 |   +0 |
| kubernetes  | `1f0d9505790c` | 2018-05-22 |     65684 | 65684 |   +0 |

6/6 完全相等，0 误差。完整 SHA 见 `code/repo.lock.tsv`。

## 2. artifact 数量对账

| 项                             | 解析值  | 论文    | 差异 |
|--------------------------------|---------|---------|------|
| blocking / non-blocking bug 行 | 85 / 86 | 85 / 86 |    0 |
| 合计                           | 171     | 171     |    0 |
| 有独立补丁的 bug               | 169     | —       |    — |
| 唯一 uid                       | 167     | —       |   −4 |

## 3. Reproduced? 分布（P4 的 ground truth）

| 分组         | 标 1 | 标 0 | 空白 | 论文 |
|--------------|------|------|------|------|
| blocking     |   21 |   12 |   52 |   21 |
| non-blocking |   23 |   26 |   37 |   20 |

空白是原表原貌，无值可补（详见 `report/p4_feasibility.md` §3）。

## 4. 致因维度自校验

一行同时标 shared 与 message 时按 message 计（论文即如此，共 1 行：kubernetes#11298）。

| 分组         | shared_memory | message_passing | 合计 | 论文    |
|--------------|---------------|-----------------|------|---------|
| blocking     |            36 |              49 |   85 | 36 / 49 |
| non-blocking |            69 |              17 |   86 | 69 / 17 |

## 5. 需要披露的三处口径差异

1. **169 个补丁 vs 171 个 bug**：`boltdb#392`、`boltdb#240` 在原表里没有 commit hash（作者把 BugID 填进了 commit hash 列）。这两个恰好是论文中内置 deadlock detector 唯二能检出的 bug。
2. **171 行 = 167 个唯一 uid**：4 行是同一 bug 的多段修复（`moby#21311`×2、`etcd#4876`×4），统计 bug 数须按 uid 去重。
3. **Reproduced?=1 共 44 行，对应 41 个 bug**：论文的 41 = 21 + 20 是 bug 级计数，差异全部来自一个 bug 对应多个补丁 commit。

---

复现命令：`cd code && ./run.sh parse`（artifact → `code/repro/data/` 下的 7 张 CSV）、`./run.sh env-report`（环境汇总）。
