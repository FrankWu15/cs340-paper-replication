# Table 6 / 7 / 9 / 10 / 11 复现

由 `code/analysis/05_stats_figures.py` 生成，数据源为 artifact 的两张 one-hot 标注表（blocking 85 行、non-blocking 86 行）。

**口径声明**：本报告复现的是论文的统计口径与算术，不是重读 171 条补丁——人工判读那一步（19 项里的第 3 项）我们主动跳过，全部沿用 artifact 标签。因此「五张表逐格一致」证明的是汇总与计算没走样，不代表独立复核过每一条标注。

逐格比对结果：**全部一致**。

## Table 6　blocking bug 的根因 × 应用

| cause | Docker | Kubernetes | etcd | CockroachDB | gRPC | BoltDB | Total |
|---|---|---|---|---|---|---|---|
| Mutex | 9 | 6 | 5 | 4 | 2 | 2 | 28 |
| RWMutex | 0 | 2 | 0 | 3 | 0 | 0 | 5 |
| Wait | 3 | 0 | 0 | 0 | 0 | 0 | 3 |
| Chan | 5 | 3 | 10 | 5 | 6 | 0 | 29 |
| Chan w/ | 2 | 6 | 5 | 0 | 2 | 1 | 16 |
| Lib | 2 | 0 | 1 | 0 | 1 | 0 | 4 |
| **Total** | 21 | 17 | 21 | 12 | 11 | 3 | 85 |

论文合计 28 / 5 / 3 / 29 / 16 / 4（N=85）；共享内存 36（42%）、消息传递 49（58%）。

## Table 7　blocking bug 的修复策略 × 根因

| cause | Adds | Moves | Changes | Removes | Misc. | Total |
|---|---|---|---|---|---|---|
| Mutex | 9 | 7 | 2 | 8 | 2 | 28 |
| RWMutex | 0 | 2 | 0 | 3 | 0 | 5 |
| Wait | 0 | 1 | 0 | 1 | 1 | 3 |
| Chan | 15 | 1 | 5 | 4 | 4 | 29 |
| Chan w/ | 6 | 3 | 2 | 4 | 1 | 16 |
| Lib | 1 | 0 | 0 | 1 | 2 | 4 |
| **Total** | 31 | 14 | 9 | 21 | 10 | 85 |

注：85 条 blocking bug 各有且仅有一个策略标记，行合计与列合计都是 85。

## Table 9　non-blocking bug 的根因 × 应用

| cause | Docker | Kubernetes | etcd | CockroachDB | gRPC | BoltDB | Total |
|---|---|---|---|---|---|---|---|
| traditional | 9 | 8 | 9 | 10 | 8 | 2 | 46 |
| anon. | 6 | 3 | 0 | 1 | 1 | 0 | 11 |
| waitgroup | 0 | 1 | 2 | 3 | 0 | 0 | 6 |
| lib | 1 | 0 | 2 | 2 | 1 | 0 | 6 |
| chan | 6 | 5 | 3 | 0 | 2 | 0 | 16 |
| msg lib | 1 | 0 | 0 | 0 | 0 | 0 | 1 |
| **Total** | 23 | 17 | 16 | 16 | 12 | 2 | 86 |

论文合计 46 / 11 / 6 / 6 / 16 / 1（N=86）；共享内存 69（80%）、消息传递 17（20%）。

## Table 10　non-blocking bug 的修复策略 × 根因

| cause | Adds | Moves | Bypass | Data Private | Misc. | Total |
|---|---|---|---|---|---|---|
| traditional | 27 | 4 | 5 | 10 | 0 | 46 |
| anon. | 5 | 2 | 0 | 4 | 0 | 11 |
| waitgroup | 3 | 2 | 1 | 0 | 0 | 6 |
| lib | 1 | 2 | 1 | 0 | 2 | 6 |
| chan | 6 | 7 | 3 | 0 | 0 | 16 |
| msg lib | 0 | 0 | 0 | 0 | 1 | 1 |
| **Total** | 42 | 17 | 10 | 14 | 3 | 86 |

论文把 Adds+Moves 合称「限制时序」，合计 59/86 = 69%。

## Table 11　non-blocking 补丁里用到的同步原语

| cause | Mutex | Channel | Atomic | WaitGroup | Cond | Misc. | None | Marks |
|---|---|---|---|---|---|---|---|---|
| traditional | 24 | 3 | 6 | 0 | 0 | 0 | 13 | 46 |
| anon. | 3 | 2 | 3 | 0 | 0 | 0 | 3 | 11 |
| waitgroup | 2 | 0 | 0 | 4 | 3 | 0 | 0 | 9 |
| lib | 0 | 2 | 1 | 1 | 0 | 1 | 2 | 7 |
| chan | 3 | 11 | 0 | 2 | 1 | 2 | 1 | 20 |
| msg lib | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 1 |
| **Total** | 32 | 19 | 10 | 7 | 4 | 3 | 19 | 94 |

注：一条 bug 的补丁里可以出现多种原语，故格子总和 94 大于 bug 数 86（论文未报「多于一个原语」的条数，artifact 的 `more than one` 列为 10）。最后一行是原语标记的合计，与论文 Total 行 32 / 19 / 10 / 7 / 4 / 3 / 19 一致。

## lift：blocking × 修复策略（N=85）

左表只过滤 cause（样本 > 10），即论文字面口径；右表两侧都要求 > 10。

| lift | cause | fix | n_AB | n_A | n_B |
|---|---|---|---|---|---|
| 1.63 | Chan | Changes | 5 | 29 | 9 |
| 1.52 | Mutex | Moves | 7 | 28 | 14 |
| 1.42 | Chan | Adds | 15 | 29 | 31 |
| 1.18 | Chan w/ | Changes | 2 | 16 | 9 |
| 1.17 | Chan | Misc. | 4 | 29 | 10 |
| 1.16 | Mutex | Removes | 8 | 28 | 21 |
| 1.14 | Chan w/ | Moves | 3 | 16 | 14 |
| 1.03 | Chan w/ | Adds | 6 | 16 | 31 |

| lift | cause 样本 | fix 样本 | cause | fix |
|---|---|---|---|---|
| 1.52 | 28 | 14 | Mutex | Moves |
| 1.42 | 29 | 31 | Chan | Adds |
| 1.17 | 29 | 10 | Chan | Misc. |
| 1.16 | 28 | 21 | Mutex | Removes |
| 1.14 | 16 | 14 | Chan w/ | Moves |
| 1.03 | 16 | 31 | Chan w/ | Adds |
| 1.01 | 16 | 21 | Chan w/ | Removes |
| 0.88 | 28 | 31 | Mutex | Adds |

论文：Mutex×Moves = 1.52（最强）、Chan×Adds = 1.42（第二），「其余均低于 1.16」。

## lift：non-blocking × 修复策略（N=86）

| lift | cause | strategy | n_AB | n_A | n_B |
|---|---|---|---|---|---|
| 2.23 | anon. | Data Private | 4 | 11 | 14 |
| 2.21 | chan | Moves | 7 | 16 | 17 |
| 1.61 | chan | Bypass | 3 | 16 | 10 |
| 1.34 | traditional | Data Private | 10 | 46 | 14 |
| 1.20 | traditional | Adds | 27 | 46 | 42 |
| 0.93 | traditional | Bypass | 5 | 46 | 10 |
| 0.93 | anon. | Adds | 5 | 11 | 42 |
| 0.92 | anon. | Moves | 2 | 11 | 17 |

| lift | cause 样本 | 策略样本 | cause | strategy |
|---|---|---|---|---|
| 2.23 | 11 | 14 | anon. | Data Private |
| 2.21 | 16 | 17 | chan | Moves |
| 1.61 | 16 | 10 | chan | Bypass |
| 1.34 | 46 | 14 | traditional | Data Private |
| 1.20 | 46 | 42 | traditional | Adds |
| 0.93 | 46 | 10 | traditional | Bypass |
| 0.93 | 11 | 42 | anon. | Adds |
| 0.92 | 11 | 17 | anon. | Moves |

论文：anon.×Data Private = 2.23、misusing chan×Moves = 2.21。

## lift：non-blocking × 补丁原语（N=86）

| lift | cause | primitive | n_AB | n_A | n_B |
|---|---|---|---|---|---|
| 3.58 | chan | Misc. | 2 | 16 | 3 |
| 3.11 | chan | Channel | 11 | 16 | 19 |
| 2.35 | anon. | Atomic | 3 | 11 | 10 |
| 1.54 | chan | WaitGroup | 2 | 16 | 7 |
| 1.40 | traditional | Mutex | 24 | 46 | 32 |
| 1.34 | chan | Cond | 1 | 16 | 4 |
| 1.28 | traditional | None | 13 | 46 | 19 |
| 1.23 | anon. | None | 3 | 11 | 19 |

| lift | cause 样本 | 原语样本 | cause | primitive |
|---|---|---|---|---|
| 3.11 | 16 | 19 | chan | Channel |
| 2.35 | 11 | 10 | anon. | Atomic |
| 1.40 | 46 | 32 | traditional | Mutex |
| 1.28 | 46 | 19 | traditional | None |
| 1.23 | 11 | 19 | anon. | None |
| 1.12 | 46 | 10 | traditional | Atomic |
| 0.82 | 11 | 19 | anon. | Channel |
| 0.73 | 11 | 32 | anon. | Mutex |

论文：misusing chan×Channel = 2.7（最强）。

## lift 数值与论文逐条对照

| 分组 | 组合 | 论文 | 本文 | 判定 |
|---|---|---|---|---|
| blocking | Mutex × Moves | 1.52 | 1.52 | 一致 |
| blocking | Chan × Adds | 1.42 | 1.42 | 一致 |
| non-blocking | anon. × Data Private | 2.23 | 2.23 | 一致 |
| non-blocking | chan × Moves | 2.21 | 2.21 | 一致 |
| non-blocking | chan × Channel | 2.70 | 3.11 | 差 +0.41 |

## 与论文的三处对话

**1）Table 6/7/9/10/11 五张表逐格一致。** 85 + 86 条标注一行不差，说明我们对 artifact 列名的映射与论文的统计口径相同。这是后面 lift 可比的前提。

**2）blocking lift 的排序取决于「>10」过滤在哪一维生效。** 论文只写「categories that have more than 10 blocking bugs」，没说 fix 类别是否也过滤。按字面只过滤 cause，Chan×Changes = 1.63（5·85/(29·9)）会排第一，与论文「Mutex×Moves 最强、Chan×Adds 第二」矛盾；把 fix 侧也要求 ≥10 后，Chan×Changes（fix 样本 9）与 Chan w/×Changes（2）被排除，排序立刻回到 1.52 / 1.42，只剩 Chan×Misc. = 1.17 比论文的「below 1.16」高 0.01（精确值 1.172，四舍五入边界），以及 Mutex×Removes = 1.16 正好压在 1.16 上。也就是说论文的排序只在「双侧过滤」这一口径下站得住，而正文没写清过滤作用在哪一维；我们不替他选口径，两种都列出来。

**3）non-blocking 三个 lift 中两个精确命中。** anon.×Data Private = 2.23（论文 2.23）、chan×Moves = 2.21（论文 2.21），排序也对。chan×Channel 我们算 3.11，论文报 2.7，差 15%。要凑出 2.7，需要 n(Channel)=22（而非 Table 11 的 19）或 N≈75——推测论文在 P(B) 里算的是「补丁中出现 channel 的次数」而非「用了 channel 的 bug 数」，一条 bug 的补丁可以出现多个 channel 操作。这一点论文没写清，我们不硬凑。

