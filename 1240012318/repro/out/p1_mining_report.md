# P1 · Bug 收集与分类：关键词挖掘结果

生成时间：2026-11-04
脚本：`scripts/01_mine_commits.py`　日志：`out/p1_mining.log`　明细：`out/commits_<app>.csv`

## 1. 对齐目标

论文 §4 用 11 个并发相关关键词过滤六个项目的 commit 历史，得到 **3211 个候选 commit**：

> race, deadlock, synchronization, concurrency, lock, mutex, atomic, compete, context, once, goroutine leak

我们的关键词表与论文原文逐项一致。

## 2. 关键发现：论文没有说明搜索范围，而这个数字对它极度敏感

论文只写 "searching their commit logs"，未说明匹配 **标题行** 还是 **整个 message**，也未说明
是否包含 **merge commit**。四种组合实测差异达 2.7 倍：

| 口径 | boltdb | etcd | grpc-go | docker | cockroachdb | kubernetes | 合计 | vs 3211 |
|---|---|---|---|---|---|---|---|---|
| **标题 · 排除 merge** | 15 | 414 | 167 | 543 | 1127 | 839 | **3105** | **−3.3%** |
| 标题 · 含 merge | 23 | 531 | 187 | 833 | 1581 | 1192 | 4347 | +35.4% |
| 全文 · 排除 merge | 21 | 546 | 199 | 949 | 2226 | 1214 | 5155 | +60.5% |
| 全文 · 含 merge | 36 | 822 | 259 | 1420 | 3117 | 2846 | 8500 | +164.7% |

（快照：147763 个 commit，即 P0 pin 的六个 commit）

**采用「标题 · 排除 merge」作为主口径**，理由不是"它最接近论文"，而是它有两条独立依据：

1. **merge commit 没有代码改动**，本身不可能引入或修复 bug。它命中关键词，往往只是因为 PR
   的分支名里带 `lock`、`race` 之类的词（如 `Merge pull request #9748 from gyuho/rename`）。
   论文研究的是修复提交，排除 merge 在方法上是自洽的。
2. **正文匹配会引入大量无关命中**。"lock" 会命中 "block"、"clock"；"context" 在 Go 项目里几乎
   出现在每个涉及 `context.Context` 的提交说明中。全文口径是标题口径的 1.66 倍，增量部分
   绝大多数与并发 bug 无关。

需要说明的是：**这一口径无法从论文反推证实**。−3.3% 的吻合也可能是巧合，因此本报告同时列出
四种口径的完整数字，最终报告应把它作为**区间**而非点值呈现（区间 3105–8500，主口径 3105）。

## 3. 分项目分布

| 项目 | commit 总数 | 候选命中 | 命中率 | 占候选总量 |
|---|---|---|---|---|
| kubernetes | 65684 | 839 | 1.28% | 27.0% |
| cockroachdb | 29485 | 1127 | 3.82% | 36.3% |
| docker | 35149 | 543 | 1.54% | 17.5% |
| etcd | 14101 | 414 | 2.94% | 13.3% |
| grpc-go | 2528 | 167 | 6.61% | 5.4% |
| boltdb | 816 | 15 | 1.84% | 0.5% |
| **合计** | **147763** | **3105** | **2.10%** | 100% |

命中率差异很大：grpc-go 每 15 个提交就有 1 个带并发关键词，kubernetes 则是 1/78。这与项目性质
一致 —— 通信库的提交天然围绕并发原语展开，而 k8s 的绝大多数提交在改 API 对象和控制器逻辑。

## 4. 与 artifact 的对齐（ground truth）

P0 阶段已从作者公开的 bug 表解析出 171 条 bug、169 个补丁、44 条带补丁的复现目标
（21 blocking / 23 non-blocking）。这是论文中**唯一有 ground truth 的部分**，对齐结果见
`data/p0_artifact_checks.md`（逐格一致，零误差）。

需要区分两件事：

- **候选 commit（3105）** 是关键词过滤的产物，只代表"可能相关"，**不是** bug 数；
- **171 个 bug** 是作者人工阅读 3211 个候选后确认的结果，我们直接采用其标注，不重做人工判定。

也就是说，P1 复现的是"筛选环节的规模"，不是"人工判定的结论"。人工判定无法复现（需要作者级
的领域判断），这一点必须在报告里明确列出。

## 5. 复现命令

```bash
./run.sh mine            # 六个仓库一起跑，输出 out/commits_<app>.csv
# 或单个仓库 + 校准表
python repro/scripts/01_mine_commits.py --repo 6app/etcd --app etcd \
    --out repro/out/commits_etcd.csv --calibrate
```

可调参数：`--scope subject|message`、`--merges include|exclude`、`--since/--until`、`--keywords`。

## 6. 结论

| 指标 | 论文 | 我们 | 偏差 | 判定 |
|---|---|---|---|---|
| 候选 commit 数 | 3211 | 3105 | −3.3% | 支持（落在 ±10% 内） |
| 关键词表 | 11 个 | 11 个，逐项一致 | — | 完全一致 |
| 分项目排序 | 论文未给 | cockroachdb > kubernetes > docker > etcd > grpc-go > boltdb | — | 无法比对 |

**局限**（写进报告的 validity threats）：

1. 论文未公布口径，主口径的选择带有推断成分；四种口径的全部数字已保留，可复核。
2. 未复现人工判定环节，171 这个数字直接取自 artifact。
3. 快照日期与论文存在 ≤41 个 commit 的差异已被 P0 消除（六仓 commit 数完全相等），
   但仍无法排除作者使用的是非主干分支的可能。
