# P4 前置 · 目标 bug 清单与可行性分档

数据源：`results/data/feasibility_44.csv`（逐条 18 列）。补丁特征解析自 artifact 的 `.txt`（内含完整 unified diff），不走 `git show`，避免 treeless clone 触发网络拉取。

## 1. 口径：44 行 ≠ 41 个 bug

| 口径                                    | blocking | non-blocking | 合计   |
|-----------------------------------------|----------|--------------|--------|
| 行级（补丁 commit 数，artifact 的 `1`） |       21 |           23 | **44** |
| bug 级（唯一 BugID）                    |       21 |           20 | **41** |
| 论文正文                                |       21 |           20 | **41** |

bug 级恰好等于论文的 41，说明 artifact 与论文不矛盾，差异全部来自一个 bug 对应多个补丁 commit。

审计结论（`bugs_master.csv` 逐行对回原表）：171 行 = 85 + 86，(uid, sha) 唯一键 171 个，**搬运值不一致 0 处**；2 行在原表找不到，正是无补丁的 `boltdb#392`、`boltdb#240`（commit hash 为空）。

`Reproduced?` 三值分布：`1` 44 行（41 bug）/ `0` 38 行（37 bug）/ **空白 89 行**。空白是原表原貌，无值可补——强行填 `0` 会凭空造出 89 条"尝试过但失败"的假记录。据此推断作者实际尝试了 78 个 bug（41 成功 + 37 失败），其余 89 个未纳入实验。**此为推断，非论文原文**。

## 2. 分档总览

按**补丁 commit** 计（44 行）：

| 档  | 含义                                    | 条数   |
|-----|-----------------------------------------|--------|
| A   | 补丁自带新增测试，可直接 `go test -run` | **14** |
| B   | 仅改产品代码，需自写触发程序            | **28** |
| C   | 阻塞（无补丁 / commit 不在库）          | **2**  |

fix commit 在本地快照 **42/44**；在 P1 候选集合 **34/44**；fix 日期晚于 pin 日期 **0/44**。

| 项目        | 条数 | A   | B   | C   |
|-------------|------|-----|-----|-----|
| etcd        |   16 |   4 |  12 |   0 |
| grpc-go     |   10 |   5 |   5 |   0 |
| docker      |    8 |   3 |   5 |   0 |
| boltdb      |    4 |   2 |   0 |   2 |
| kubernetes  |    4 |   0 |   4 |   0 |
| cockroachdb |    2 |   0 |   2 |   0 |

## 3. 多补丁 bug 必须整组回滚

只有 `etcd#4876` 一个 bug 有 4 个补丁 commit（`91dc6b29a6`、`2c83362e63`、`e129223dbe`、`4bdfc0a46d`）。补丁被拆成多段时，单独回滚任意一段通常不足以复现，**必须整组一起回滚**。同一 bug 内各行的复现状态完全一致，说明 artifact 是按 bug 判定，不是按 commit 逐行判定。

## 4. 与 P1 候选集的交叉验证（P1 的实质缺陷）

44 行中 34 行的 fix commit 落在 P1 的 3,105 个候选里，缺失 10 条：

| 原因                                | 条数  | 性质              |
|-------------------------------------|-------|-------------------|
| artifact 无 fix commit              | 2     | 必然缺失          |
| 是 merge commit（P1 排除 merge）    | 3     | 必然缺失          |
| **commit 标题不含关键词、正文才含** | **5** | **P1 的实质缺陷** |

那 5 条全部被论文标为"已复现"，正文均命中关键词：

- `moby#27782` · `a69a59ff` · *Decouple removing the fileWatcher from reading* —— 命中 race / deadlock / lock
- `etcd#4474` · `0cb304ec` · *contrib/raftexample: fix restart path* —— 命中 deadlock / lock
- `grpc#1293` · `7df48bee` · *transport: fix error handling on Stream deletion* —— 命中 lock / context
- `etcd#7816` · `3ce31acd` · *v3client: wrap watch ctxs with blank ctx* —— 命中 race
- `etcd#3060` · `7f95780b` · *etcdserver: init raft internal var early* —— 命中 race

若论文用标题匹配，它们根本进不了人工筛选环节。改用全文口径重算得 4,544（覆盖这 5 条，但总数高 41%），说明论文还有未写明的过滤条件。

> **结论：不能用「−3.3%」声称复现了论文的筛选漏斗。** 详见 `report/p1_limitation.md`。

## 5. A 档不等于「能直接跑」

`boltdb#341` 是 A 档，但补丁自带的测试完全无效（`TestDB.Close()` 劫持了 `bolt.DB.Close()` 的调用）。真正跑起来还差三关：回滚到修复前版本（treeless clone 会联网拉 tree）、用 Go 1.10 编译（2015–2018 的代码现代 Go 大概率编译失败）、并发 bug 需重复 N 次统计。

**剩余 13 条 A 档必须逐条确认测试真的调用到了被修复的函数。**

建议执行顺序（依赖从轻到重）：① `boltdb@7fb06fee` → ② `boltdb#341` → ③ `etcd#5199`（可 `go test ./clientv3/...` 单包跑）。Kubernetes 与 CockroachDB 全部为 B 档且编译体量最大，放到模板验证通过之后。

---

复现：`cd code && ./run.sh feasibility`（生成可行性表）、`./run.sh audit`（生成审计结论，仅需 `repro/data/`）。
