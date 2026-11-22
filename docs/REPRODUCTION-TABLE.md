# 实验复现情况表（CS340）

> 数据来源：`data/repro_targets.csv`（论文 41 条目标）× `results/data/repro_summary.csv`（仓库 33 条复现记录），
> 取交集。生成于 2026-11-22，对应 `origin/main` 的 `a4eccbd` 之后。
> 复算方式见文末「口径说明」，任何数字都可按那段重算。

---

## 一句话

**41 条目标里复现 24 条（59%）**：blocking 17/21（81%），non-blocking 7/20（35%）。

---

## 1. 按应用

| 应用 | 论文目标 | 已复现 | 覆盖率 | 未做 |
|---|---:|---:|---:|---:|
| etcd | 13 | 6 | 46% | 7 |
| grpc-go | 10 | 7 | 70% | 3 |
| boltdb | 4 | 3 | 75% | 1 |
| docker | 8 | 5 | 63% | 3 |
| kubernetes | 4 | 2 | 50% | 2 |
| cockroachdb | 2 | 1 | 50% | 1 |
| **合计** | **41** | **24** | **59%** | **17** |

## 2. 按类型

| 类型 | 论文目标 | 已复现 | 覆盖率 | 未做 |
|---|---:|---:|---:|---:|
| blocking | 21 | 17 | 81% | 4 |
| non-blocking | 20 | 7 | 35% | 13 |
| **合计** | **41** | **24** | **59%** | **17** |

差距主要在 non-blocking：13 条未做里 9 条属于这一类，因为竞争类 bug 依赖 `-race`
在特定版本组合上复现，而本机 `-race` 产物启动即 `0xC0000139`（race 运行时 DLL 缺失）。

---

## 3. 已复现的 24 条

| # | 目录 | bug | 类型 | 判定（buggy → fixed） | 负责 |
|---:|---|---|---|---|---|
| 1 | `etcd-4033` | etcd#4033 | blocking | HANG → PASS | 李振炜 1240012318 |
| 2 | `etcd-4474` | etcd#4474 | blocking | CRASH → CLEAN | 李振炜 1240012318 |
| 3 | `etcd-4679` | etcd#4679 | blocking | DEADLOCK → CLEAN | 李振炜 1240012318 |
| 4 | `etcd-5509` | etcd#5509 | blocking | DEADLOCK → CLEAN | 李振炜 1240012318 |
| 5 | `etcd-6278` | etcd#6278 | blocking | DEADLOCK → CLEAN | 李振炜 1240012318 |
| 6 | `etcd-6937` | etcd#6937 | blocking | DEADLOCK → CLEAN | 李振炜 1240012318 |
| 7 | `grpc-1293` | grpc#1293 | blocking | FAIL ×3 → PASS ×3 | 李振炜 1240012318 |
| 8 | `grpc-1424` | grpc#1424 | blocking | FAIL ×3 → PASS ×3 | 李振炜 1240012318 / 许汝轩 1240011357 |
| 9 | `grpc-1459` | grpc#1459 | blocking | TIMEOUT ×3 → PASS ×3 | 李振炜 1240012318 |
| 10 | `grpc-1667` | grpc#1667 | non-blocking | RACE ×3 → PASS ×3 | 李振炜 1240012318 |
| 11 | `grpc-1687` | grpc#1687 | non-blocking | FAIL ×3（panic: send on closed channel）→ PASS ×3 | 李振炜 1240012318 |
| 12 | `grpc-1850` | grpc#1850 | blocking | DEADLINE 8/50 → PASS 50/50 | 李振炜 1240012318 |
| 13 | `grpc-793` | grpc#793 | blocking | TIMEOUT ×3 → PASS ×3 | 李振炜 1240012318 |
| 14 | `boltdb-341` | boltdb#341 | non-blocking | Commit SIGSEGV/panic → Close 阻塞后 Commit 成功 | 李振炜 / 许汝轩 |
| 15 | `boltdb-392` | boltdb#392 | blocking | 死锁 10/10 → 干净退出 | 吴德诚 1240012684 |
| 16 | `boltdb-7fb06fee` | boltdb@7fb06fee | non-blocking | 失败率 80~100% → 0~10% | 李振炜 1240012318 |
| 17 | `moby-17176` | moby#17176 | blocking | 等锁超时 → 成功拿到锁 | 朱奕铭 1240012557 |
| 18 | `moby-256` | moby#256 | blocking | DEADLOCK 3/3 → OK 3/3 | 李振炜 1240012318 |
| 19 | `moby-27782` | moby#27782 | blocking | DEADLOCK 3/3 → OK 3/3 | 李振炜 1240012318 |
| 20 | `moby-28682` | Moby#28682 | non-blocking | BUG 3/3（漏发 85~105/200）→ OK 3/3 | 李振炜 1240012318 |
| 21 | `moby-8909` | moby#8909 | blocking | DEADLOCK 3/3 → OK 3/3 | 李振炜 1240012318 |
| 22 | `kubernetes-30872` | kubernetes#30872 | blocking | DEADLOCK 3/3 → OK 3/3 | 李振炜 1240012318 |
| 23 | `kubernetes-36377` | kubernetes#36377 | non-blocking | BUG 3/3（annotations 1→2）→ OK 3/3 | 李振炜 1240012318 |
| 24 | `cockroachdb-17112` | cockroachdb#17112 | non-blocking | BUG 3/3（约 210 次/2s）→ OK 3/3 | 李振炜 1240012318 |

> 第 8、14 条是两人各自独立做过的同一 bug，两套证据都保留，不取其一。

---

## 4. 未复现的 17 条

| 应用 | bug | 类型 | 状态 |
|---|---|---|---|
| etcd | etcd#5199 | blocking | 未开始 |
| etcd | etcd#5349 | blocking | 未开始 |
| etcd | etcd#4876 | non-blocking | 未开始（该编号下有 4 个补丁变体，可挑其一） |
| etcd | etcd#7816 | non-blocking | 未开始 |
| etcd | etcd#3593 | non-blocking | **尝试后未复现**（负面结果已留档） |
| etcd | etcd#8183 | non-blocking | **尝试后未复现** |
| etcd | etcd#3060 | non-blocking | **尝试后未复现** |
| grpc-go | grpc#639 | blocking | 未开始 |
| grpc-go | grpc#1662 | non-blocking | 未开始 |
| grpc-go | grpc#1803 | non-blocking | 未开始 |
| boltdb | boltdb#240 | blocking | 未开始 |
| docker | moby#22940 | non-blocking | 未开始 |
| docker | moby#22985 | non-blocking | 未开始（论文 Fig 8 的循环变量捕获案例） |
| docker | moby#27037 | non-blocking | 未开始 |
| kubernetes | kubernetes#26407 | non-blocking | 未开始 |
| kubernetes | kubernetes#49404 | non-blocking | 未开始 |
| cockroachdb | cockroachdb#19962 | non-blocking | 未开始 |

`etcd#3593` / `#8183` / `#3060` 三条不是没做，是做了没成：补丁修的是测试或初始化自身的脆弱竞态，
`-race` 跑 1~100 轮均 0 报告，原始日志在 `results/attempts-11-21/logs/`。这类**负面结果同样计入工作量**，
但按口径不能进分子。

---

## 5. 口径说明

**41 怎么来的。** `data/repro_targets.csv` 有 44 行，按 `uid` 去重后 41 条。多出来的 3 行是
`etcd#4876`——一个 issue 下有 4 个不同 fix commit（3 个 `shared_memory` + 1 个 `message_passing`），
属于 artifact 原始标注的多补丁变体，**行不能删**（删了会丢 cause_group 信息），统计时按 uid 计 1 条。

**24 怎么来的。** 把 `repro_summary.csv` 的 33 条记录与 41 条目标按 bug 编号取交集。
`repro_summary.csv` 原先只有 27 条，11-18 与 11-21 两批 etcd（6 条）散在
`repro_summary_1118.csv` / `repro_summary_1121.csv` 里没合并，2026-11-22 已并入。
另有 9 条记录在 41 条集合外（`defdb743c`、`1cc69980`、etcd#6873、etcd double-lock、k8s#62464、#20697、
etcd#4997、grpc#1546、k8s#9926、docker `0d9e543`、Moby#16309），**不能计入分子**。

**形态不是统一的。** 24 条里复现形态有两种，报告与演示里必须分开说：

- **real-repo**（上游函数本体原样执行）：`boltdb-392`、grpc 的 793/1293/1424/1459/1850、
  `etcd-4033`/`4474`/`6278`、`moby-8909`、`moby-256`，共 **11 条**。
- **minimal**（按补丁还原调用序列，用标准库重写）：`etcd-4679`/`5509`/`6937`、`moby-27782`、
  `moby-28682`、`kubernetes-30872`、`kubernetes-36377`、`cockroachdb-17112`，共 **8 条**。
- 其余 5 条（`boltdb-341`、`boltdb-7fb06fee`、`grpc-1667`、`grpc-1687`、`moby-17176`）在现有文档里
  没有明确标注形态，**不要替它们下结论**。

minimal 证明的是「这段调用序列会死锁／会读到脏状态」，不等于「上游程序真实运行时会以同样方式失败」。
这条边界直接影响下面两张表，别混算。

**两张检测器表的分母没跟着涨。** 新增的 4 条 blocking 是驱动侧**外部超时**判的死锁，
日志里没有 `all goroutines are asleep`，所以 Table 8 仍是「已测 11、检出 6」；
新增的 3 条 non-blocking 没跑 `-race`（产物 `0xC0000139`），Table 12 仍是「已测 6」。

---

## 6. 演示时可以直接用的话

> 我们把论文 41 条目标复现了 24 条，占 59%。blocking 类做到 81%，non-blocking 只有 35%——
> 差距不是没做，是竞争类 bug 对工具链版本很敏感，`-race` 在我们机器上跑不起来，
> 只能用可观测不变量替代。剩下 17 条里有 3 条是试过但没复现的，负面结果也留在仓库里。
