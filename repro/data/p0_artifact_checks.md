# P0 artifact 一致性校验

- artifact：`C:\Users\Li\Desktop\work-app\操作系统\output\go-concurrency-bugs-master`
- 生成时间：2026-11-04 13:48

## 数量对账

| 项 | 本仓库解析 | 论文 | 差异 |
|---|---|---|---|
| blocking bug 行 | 85 | 85 | +0 |
| non-blocking bug 行 | 86 | 86 | +0 |
| 合计 | 171 | 171 | +0 |
| 补丁文件 | 169 | — | — |
| 无补丁的 bug | 2 | — | — |
| 唯一 uid | 167 | 171 | -4 |
| 有 BugID 的行 | 154 | — | — |

## Reproduced? 分布（P4 的 ground truth）

| 分组 | 标 1 | 标 0 | 空白 | 论文 |
|---|---|---|---|---|
| blocking | 21 | 12 | 52 | 21 |
| non-blocking | 23 | 26 | 37 | 20 |

## 致因维度自校验（论文核心结论）

口径：一行同时标了 shared 和 message 时按 message 计（论文即如此，共 1 行：kubernetes#11298）。

| 分组 | shared_memory | message_passing | 合计 | 论文 |
|---|---|---|---|---|
| blocking | 36 | 49 | 85 | 36 / 49 |
| （其中混合型 1 行，message 占比 57.6%） | | | | |
| non-blocking | 69 | 17 | 86 | 69 / 17 |

## 与论文的口径差异（需在报告中披露）

1. **补丁 169 个 vs bug 171 个**：2 个 BoltDB blocking bug 在表里没有 commit hash（作者把 BugID 直接填进了 commit hash 列），所以没有独立补丁。这两个恰好就是论文中内置 deadlock detector 唯二能检出的 bug。
2. **171 行对应 167 个唯一 uid**：4 行是同一 bug 的多处修复（Moby#21311×2, etcd#4876×4），统计'bug 数'时需按 uid 去重。
3. **Reproduced?=1 共 44 条**（blocking 21 + non-blocking 23），论文说的 41 = 21 + 20，non-blocking 多出 3 条；推测论文的 20 是'进入 detector 评测'的子集，P4 以 `repro_targets.csv` 为准，P5 再按论文口径筛。

## 无独立补丁的 bug（2 条）

| BugID | app | behavior | Reproduced |
|---|---|---|---|
| boltdb#392 | boltdb | blocking | 1 |
| boltdb#240 | boltdb | blocking | 1 |
