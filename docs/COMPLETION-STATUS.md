# 实验完成情况（只列实验，不含报告格式与仓库管理）

- 快照：`origin/main` = `cd642c8`（2026-11-21，含 11-18 的 etcd 三条）；11-21 批次（#4033/#4474/#6278 + Table 6/7/9/10/11 统计）尚未推送
- 口径：论文 *Understanding Real-World Concurrency Bugs in Go*（ASPLOS'19）自报的实验活动
- 说明：本文只回答「论文做了哪些实验、我们做到哪」，不含 v1.0、LICENSE、commit 署名、报告写作等非实验项

---

## 1. 论文 41 条目标的复现覆盖

| 应用          | 论文目标（去重） |    已复现 |     覆盖率 |     未做 |
| ----------- | -------: | -----: | ------: | -----: |
| etcd        |       13 |      6 |     46% |      7 |
| grpc-go     |       10 |      7 |     70% |      3 |
| boltdb      |        4 |      3 |     75% |      1 |
| docker      |        8 |      1 |     13% |      7 |
| kubernetes  |        4 |      0 |      0% |      4 |
| cockroachdb |        2 |      0 |      0% |      2 |
| **合计**      |   **41** | **17** | **41%** | **24** |

按类型：blocking **13/21**（62%）、non-blocking **4/20**（20%）。

仓库里共有 **28 个 bug 点**：17 条落在论文 41 条内，另 11 条在集合外（`defdb743c`、`1cc69980`、etcd#6873、etcd double-lock、k8s#62464、#20697、etcd#4997、grpc#1546、k8s#9926、docker `0d9e543`、Moby#16309），集合外的不能计入分子。

**etcd 6 条**：11-18 的 #6937/#5509/#4679（DEADLOCK/CLEAN，minimal 复现体）；11-21 的 #4033（HANG/PASS）、#4474（CRASH/CLEAN）、#6278（DEADLOCK/CLEAN），三条都跑在真实 etcd 源码上。详见 `ALL/11-21/README.md`。

另有 3 条 etcd（#3593/#8183/#3060）尝试后**未复现**：补丁修的是测试/初始化自身的脆弱竞态，`-race` 跑 1~100 轮均 0 报告，原始日志在 `ALL/11-21/results/logs/`。

---

## 2. 论文实验逐项对照（19 项）

| #  | 论文实验                     | 论文产出           | 仓库现状                                                                                    | 状态               |
| -- | ------------------------ | -------------- | --------------------------------------------------------------------------------------- | ---------------- |
| 1  | 六个应用元信息                  | Table 1        | `data/bug_table_application.csv` + `report/appendix/p0_repo_pin.md`，commit 数已对齐         | ✅                |
| 2  | 11 关键词过滤                 | → 3,211 候选     | `p1_limitation.md`：全文口径重算 4,544，按补丁反推 3,105                                             | 🟡 数字接近，漏斗未复现    |
| 3  | 人工判读候选                   | → 171 个真 bug   | 不做，全部采用 artifact 标签（有声明）                                                                | ⬜ 主动跳过           |
| 4  | 二维分类                     | Table 5        | 用 artifact 标签重算，与原表一致                                                                   | ✅                |
| 5  | bug 生命周期                 | Fig 4          | `report/appendix/p6_lifecycle.md` + `report/figures/fig4_bug_lifetime.svg`，63 条（3/6 应用） | ✅ 缩小规模           |
| 6  | 复现 bug                   | §4，41 条        | 仓库共 **28 个 bug 点**，其中 **17 条落在论文 41 条内**，另 11 条在集合外                                     | 🟡 17/41，仓库 28   |
| 7  | goroutine 创建点            | Table 2        | `p2_static.md`，Total 列平均偏差 4.5%                                                         | ✅                |
| 8  | gRPC-C 线程创建点             | §3.1 对照        | v1.10.0 源码实测：核心路径 **5 个**创建点、147.1K 行、0.034/KLOC，与论文 5 / 0.03 一致                        | ✅                |
| 9  | 动态创建点测量                  | Table 3        | Go 侧三组实测：1000 并发 → **1019 goroutine**，÷论文比值 201.46 = 5.06（C 线程池 5 线程），自洽；存活时间列口径不可对齐    | 🟡 比值列复现         |
| 10 | 并发原语用量                   | Table 4        | `p2_static.md` §4，Mutex 合计偏差 +1.8%                                                      | ✅                |
| 11 | gRPC-C 原语对照              | 746 vs 786     | `report/grpc_c_vs_go.md`：C 侧 v1.11/v1.12 **精确 746**、5.51/KLOC；Go 侧 771（−1.9%）、8 类原语     | ✅                |
| 12 | 原语比例时间演化（Fig 2/3）        | Fig 2 / Fig 3  | `report/fig23_evolution.md` + 两张 SVG：6 应用 × 14 季度，逐点偏差 0.5–3.3 pp；etcd 漂移 −12.9 pp      | ✅                |
| 13 | blocking 致因分布            | Table 6        | `05_stats_figures.py` → `results/tables/table6_blocking_cause_app.csv`，6×6 逐格与论文一致      | ✅                |
| 14 | blocking 修复策略 + lift     | Table 7        | 同脚本，Table 7 逐格一致；lift Mutex×Moves **1.52**、Chan×Adds **1.42** 与论文同值                     | ✅                |
| 15 | 内置死锁检测器                  | Table 8，2/21   | `docs/P5-CHECKLIST.md` + `results/data/p5_checklist.csv`                                | 🟡 6/13 检出（见 §3） |
| 16 | non-blocking 致因分布        | Table 9        | 同脚本，6×6 逐格一致                                                                            | ✅                |
| 17 | non-blocking 修复策略 + lift | Table 10 / 11  | Table 10、Table 11 逐格一致；lift anon.×Data Private **2.23**、chan×Moves **2.21** 与论文同值       | ✅                |
| 18 | `-race` 检出率              | Table 12，10/20 | 5 条已测、3 条检出                                                                             | 🟡 3/6（见 §3）     |
| 19 | 自研匿名函数检测器                | §7，无数字         | 无                                                                                       | ❌ 不在范围           |



---

## 3. P5 检测器实测明细

### Table 8（内置死锁检测器，13 个 blocking 点）

| 分类                       | 已测 |    检出 | 说明                                              |
| ------------------------ | -: | ----: | ----------------------------------------------- |
| `real-repo`（链接真实源码/官方测试） |  6 | **1** | 只有 boltdb-392；grpc 793/1293/1424/1459/1850 全部不报 |
| `minimal`（自写最小重实现）       |  5 | **5** | cockroachdb、etcd#6873×2、k8s#62464/#20697        |
| 合计                       | 11 |     6 | 未测 2：`boltdb-begin-lock-leak`、`moby-17176`      |

与论文 2/21 的对话方式：只能拿 `real-repo` 那行比，即 **1/6**；`minimal` 的 5/5 只证明复现体确实死锁，不能算「Go 抓到了真实 bug」。

grpc 五条的死锁**成立**（SIGQUIT 栈可证），但不报的原因已实测确认：`checkdead()` 要求全体 goroutine 睡死且 timers 为空、netpoll 无事件，真实 server 永远有 IO/select 协程存活。证据在 `results/logs/p5-1118/`。

### Table 12（`-race`，6 个 non-blocking 点）

| bug               | 形态                                      | 运行次数 |  检出 | 首次命中 |
| ----------------- | --------------------------------------- | ---: | --: | ---: |
| etcd#4997         | index 一致性                               |  100 | 100 |    1 |
| kubernetes#9926   | capabilities 字段                         |  100 | 100 |    1 |
| grpc#1667         | map 并发读写                                |   10 |  10 |    1 |
| boltdb `7fb06fee` | 读事务共享 `db.meta`                         |   20 |   0 |    — |
| grpc#1687         | send on closed channel（order violation） |    3 |   0 |    — |
| boltdb#341        | Close 不等写事务                             |   未跑 |   — |    — |

实测 **3/6**，方向与论文一致：纯 data race 能报，order/atomicity 类天然检不到（论文 lib 0/2、chan 0/1 同理）。

---

## 4. Table 6/7/9/10/11 与 lift 明细

脚本 `ALL/11-21/code/analysis/05_stats_figures.py`，报告 `ALL/11-21/report/tables_6_11.md`。

五张表由 artifact 的两张 one-hot 标注表直接交叉统计（blocking 85 行、non-blocking 86 行），**逐格与论文一致，0 处差异**；脚本内置 `PAPER` 参考字典，任何一格对不上就以非零码退出。

两处归类例外（由论文表格数字反推，已写进脚本注释）：`moby#25384` 六个根因列全空但 `WaitGroup=1`，按 Wait 计；`kubernetes#11298` 双标 `wait related` + `mixing lock/wait & channel`，按 Chan w/ 计。只改归类，不改原始标注。

lift 对照：

| 组合                      |       论文 |   本文 | 判定      |
| ----------------------- | -------: | ---: | ------- |
| Mutex × Moves           | 1.52（最强） | 1.52 | ✅       |
| Chan × Adds             | 1.42（第二） | 1.42 | ✅       |
| anon. × Data Private    |     2.23 | 2.23 | ✅       |
| misusing chan × Moves   |     2.21 | 2.21 | ✅       |
| misusing chan × Channel |  2.7（最强） | 3.11 | ⚠ 差 15% |

两点如实记录：

1. **论文一句表述与其 Table 7 不自洽。** 正文称「其余均低于 1.16」，但按同一公式 Chan×Changes = 1.63，高于它报的 1.42 与 1.52。只有把「样本数 > 10」同时作用到 fix 侧（Chan×Changes 的 fix 样本为 9）时，排序才回到 1.52 / 1.42。论文未说明过滤作用在哪一维，报告里两种口径都给出。
2. **`chan × Channel` 的 2.7 无法用 Table 11 的 19 复算出来。** 需 `n(Channel)=22` 或 `N≈75`，推测论文 `P(B)` 数的是「补丁中出现 channel 的次数」而非「用了 channel 的 bug 数」。这条不硬凑。

---

## 5. 一句话结论

实验侧已经完成的是「**静态测量 + 一部分复现 + 两个检测器实验 + 两张时间图 + 五张统计表 + 两处跨语言对照**」：  
Table 1/2/4/5/6/7/9/10/11 九张可交（其中六张逐格与论文一致），41 条复现 17/41（仓库 28 个 bug 点），Table 8/12 有实测但分母小，Fig 4 已出图（63/171 条），Fig 2/3 已出图（6 应用 × 14 季度），Table 3 比值列已复现，gRPC-C 与 gRPC-Go 的原语对照已补（746 精确命中）。

真正缺的只剩三处**口径问题**，不是没做：

1. Table 3 的存活时间列口径不可对齐（见 `ALL/11-21/report/table3_dynamic.md`）；
2. Table 8 的 real-repo 分母只有 6 条（minimal 5 条不能混算）；
3. Fig 2/3 里 CockroachDB 形状不符（MAE 3.3 pp、r≈0），与 Table 4 里它 Total −18% 是同一件事。

另有 **41 条里还剩 24 条**未复现，集中在 docker（7）、kubernetes（4）、etcd（7）、cockroachdb（2）、grpc（3）、boltdb（1）。
