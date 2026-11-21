# 《Understanding Real-World Concurrency Bugs in Go》(ASPLOS'19) 复现方案

> 原文：Tengfei Tu, Xiaoyu Liu, Linhai Song, Yiying Zhang. *Understanding Real-World Concurrency Bugs in Go*. ASPLOS'19.
> 数据与修复补丁：https://github.com/system-pclub/go-concurrency-bugs
> 可执行步骤见 `repro/README.md`；本文档说明"为什么这么做"。
>
> ---
>
> **进度标注（2026-11-17 核对）**
>
> 原文的方法与论证未改动，只在每节末尾追加【现状】，并在流程图、步骤号、验收清单上打标记。
>
> `✅ 完成并可复核` · `🟡 部分完成` · `⬜ 未开始` · `❌ 不在本次范围`
>
> 核对对象是统一结构交付目录 `output/ALL/11-14/`（与 GitHub 远端 `main` 一致，810 个文件）。括号里的数字都能在该目录里查证，出处写在每节【现状】的第一句。

---

## 0. 先明确"复现"在这里指什么

这不是一篇可以 `python main.py` 跑出图表的实验型论文，而是一篇**实证研究（empirical study）+ 工具评测**。它的"实验"由 5 类活动组成，复现时必须分开对待：

| # | 论文活动 | 对应产出 | 可复现性 |
|---|---|---|---|
| 1 | 从 6 个 Go 项目挖掘并人工判定 171 个并发 bug | Table 5 | 数据可复现，**人工判定不可复现**（本次直接采用 artifact 标签，见 §0.6） |
| 2 | 静态统计 goroutine 创建点、并发原语使用率 | Table 2、Table 4、Fig 2、Fig 3 | 工具未开源，需**重实现** |
| 3 | gRPC-Go vs gRPC-C 运行时 goroutine/线程测量 | Table 3 | 需跑 benchmark + 插桩，**可重实现** |
| 4 | 实际复现 41 个 bug（21 blocking + 20 non-blocking） | Table 8、Table 12 的输入 | **可复现**，但要重建老编译环境 |
| 5 | 评测 Go 内置 deadlock detector 与 `-race` detector | Table 8、Table 12 | **可复现**，工作量集中在第 4 步 |
| 6 | 统计相关性（lift）、bug 生命周期 CDF | Table 6/7/9/10/11、Fig 4 | 有标注数据即可，**纯脚本** |

**要对的靶子数字（验收基准）**

- 171 个 bug = 85 blocking + 86 non-blocking = 105 shared-memory 致因 + 66 message-passing 致因
- 关键词过滤命中 **3211** 个候选 commit
- blocking bug 中 **58%**（49/85）由 message passing 引起 ← 核心反直觉结论
- 内置 deadlock detector 只检出 **2/21**（BoltDB#392、BoltDB#240）
- `-race` 在 100 次运行内检出 **10/20**
- blocking bug 补丁平均 **6.8** 行；约 90% 靠调整同步原语修复
- 最强 lift：Mutex→Moves 1.52；Chan→Adds 1.42；chan 致因→chan 修复 2.7；anon→data private 2.23

**复现分级（建议按 A→B→C 顺序推进）**

- **A 级（必须做，2 周内可闭环）**：拉取 artifact 仓库 → 重建 41 个 bug 的编译/触发环境 → 重跑两个 detector → 复现 Table 8 / Table 12。
- **B 级（论文卖点，需要写工具）**：AST 静态统计复现 Table 2 / Table 4 / Fig 2 / Fig 3；gRPC benchmark 复现 Table 3。
- **C 级（只做复核不做重现）** ❌ 按 §0.6 取消：171 个 bug 的人工分类。原计划只能做"标注一致性检验"（双人标注 + Cohen's kappa），但既然标签全部采用 artifact、没有第二套独立判定，kappa 无意义。改为在报告里声明这是**已放弃的环节**，并把由此产生的 6 张表定性为"重排版"。

---

## 0.5 现状总览

按论文自报的活动（上表 6 类）反推成 19 个可执行操作，覆盖情况如下。**方案本身覆盖 18/19，唯一没写进方案的是论文 §7 的自研检测器**；下面是执行层面的完成度。

| 阶段 | 计划产出 | 状态 | 实测数字 / 说明 |
|---|---|---|---|
| P0 环境与数据 | 6 仓库 pin、artifact 解析 | ✅ | 6/6 commit 数零误差（816 / 14101 / 2528 / 35149 / 29485 / 65684）；`bugs_master.csv` 171 行、`artifact_manifest.csv` 169 条补丁、`repro_targets.csv` 41 条、`feasibility_44.csv` 44 条 |
| P1 收集与分类 | 3211 候选、171 人工判定、Table 5、kappa | 🟡 | 关键词四种匹配口径都测过，标题口径 3,105（−3.3%）落在 ±10% 内，但候选清单未落库；**人工判定与 kappa 明确不做**，分类标签全部采用 artifact（口径见 §0.6）；Table 5 重算 85/86、105/66 逐格一致 |
| P2 静态测量 | Table 2、Table 4、Fig 2/3、gRPC-C 对照 | 🟡 | Table 2 平均偏差 4.5%（grpc-go 0.909，超论文上限 0.83 达 9.5%）；Table 4 的 Mutex 居首、chan 18%~43% 两条结论成立，Once/atomic 判为不可比；**Fig 2/3 未做**；**gRPC-C 对照未做** |
| P3 动态测量 | Table 3 | ⬜ | 无脚本、无 `dynamic.csv`，全库无 `ping_pong` / `qps_unconstrained` 字样 |
| P4 Bug 复现 | 41 条（21 + 20） | 🟡 | **19/41**：blocking 13、non-blocking 6；每条都有 buggy/fixed 双侧对照与原始日志 |
| P5 检测器评测 | Table 8、Table 12 | 🟡 | Table 8 只做了 boltdb-392 一格（10/10 检出，稳定复现论文点名的 2 条之一）；Table 12 **0/20**，没有任何 non-blocking bug 在 `-race` 下跑过 |
| P6 统计与图表 | lift、Fig 4、Table 6/7/9/10/11 | 🟡 | 5 张表所需标签已在 `data/bug_table_blocking.csv`(85 行) / `bug_table_non_blocking.csv`(86 行) 里，重算逐格与论文一致，**但汇总表未产出**；`bugs_master.fix_strategy` 171 行全空；**lift 与 Fig 4 未做** |
| 论文 §7 自研检测器 | — | ❌ | 论文只有一句"已发现几个新 bug"，无可复现数字；本方案原本也没列 |

**一句话**：**P0 完成，P1 做了一半，P2 / P4 / P5 / P6 部分完成，P3 未开始。** 按论文的 19 项操作算：完整完成 **3** 项（Table 5、Table 2、Table 4）、部分完成 **8** 项（Table 1、关键字过滤、复现 19/41、Table 8 一格，以及 Table 6/7/9/10/11 与 lift 这 4 项"数据齐、未出表"）、完全未动 **6** 项（Fig 4、gRPC-C 两项、Table 3、Fig 2/3、Table 12）、**明确不做 2 项**（人工判定、§7 自研检测器）。逐项对照见 §7。

**补齐成本最低的三件事**（按性价比）：① P6 的 5 张表 + 2 组 lift，纯统计，数据在手；② P5 的 Table 8 补满 13 条，`p4_case.sh` 已有；③ P5 的 Table 12，6 条 non-blocking 各跑 `-race` ×100。

---

## 0.6 口径声明：不做人工分类，分类标签全部采用 artifact

**决定**：P1 的人工判定环节（含双人标注与 Cohen's kappa）**不做**。171 条 bug 的 behavior（blocking / non-blocking）、cause（shared memory / message passing）、致因细分、修复策略、补丁内原语，**全部直接采用论文 artifact 的逐 bug 标签表**。

**为什么可以这样做**：artifact 的 `bug_table_blocking.csv`（85 行）与 `bug_table_non_blocking.csv`（86 行）里逐 bug 的标签是齐的，重算结果与论文逐格一致——

| 论文表 | 论文值 | artifact 标签重算 |
|---|---|---|
| Table 5 分类总表 | 85 / 86、105 / 66 | 一致 |
| Table 6 blocking 致因 | 28 / 5 / 3 / 29 / 16 / 4 | 一致 |
| Table 7 blocking 修复 | 31 / 14 / 9 / 21 / 10 | 一致 |
| Table 9 non-blocking 致因 | 46 / 11 / 6 / 6 / 16 / 1 | 一致 |
| Table 10 non-blocking 修复 | 42 / 17 / 10 / 14 / 3 | 一致 |
| Table 11 补丁内原语 | 32 / 19 / 10 / 7 / 4 / 3 / 19 | 一致 |

也就是说，人工再标一遍**不会带来新信息，只会带来分歧**——论文自己也没报告一致率，没有可对照的基准。

**代价（必须写进报告，不能省）**：

1. **这 6 张表从"复现"降级为"重排版（recount / re-tabulate）"**。我们验证的是"标签 → 统计量"这一步算得对，不是"从 3,211 个候选里判出 171 条"这一步判得对。报告里必须写成前者。
2. **独立贡献只剩三块**：P2 用自研 `goast` 重算静态指标、P4 亲手复现 19 条、P5 亲手跑两个检测器。这三块才是能主张"我们做了"的部分。
3. **P1 的验收入口从"流程可审计"改为"标签可追溯"**：不再要求 `commits.csv` 支撑抽样链，改为要求每张表都能指到 artifact 的哪一列、哪一行。
4. **风险条目 3 从"未做"变成"已声明的限制"**：不能写成"来不及做"，要写成"该环节依赖研究者判断、论文未公开判定规则，故采用其公开标签，不重复判定"。

**顺带的好处**：Table 6/7/9/10/11 与两组 lift 变成纯统计，`bugs_master.fix_strategy` 171 行全空这件事也不再是缺口——从 artifact 的两张表直接算即可，不必回填主表。

---

## 1. 整体流程（六阶段流水线）

```
✅ P0 环境与数据准备                                          ← 6/6 零误差
   ├─ 6 个上游仓库（pin 到 2018-05 快照）+ artifact 仓库          ✅
   └─ Go 1.10/1.11 旧工具链 + GOPATH/vendor 模式 + 现代 Go 用于对照  🟡 1.10.8 已用，现代 Go 对照未做
        │
🟡 P1 Bug 收集与分类 ─────────────────────────────► Table 5     ← Table 5 已对齐，人工判定未做
   ├─ 关键词 git log 过滤 → commits.csv（目标 3211）              🟡 3,105（−3.3%），commits.csv 未落库
   ├─ 分层随机抽样 → 人工判定（blocking? / 致因? / 修复策略?）      ⬜ 未做
   └─ 与 artifact 的 bug table.xlsx 对齐（校验标注质量）           ✅ 85/86、105/66 逐格一致
        │
🟡 P2 静态测量 ───────────────────────────────────► Table 2 / Table 4 / Fig 2 / Fig 3
   ├─ goast：go/ast 遍历，统计 goroutine 创建点与 7 类原语          ✅ Table 2 偏差 4.5%、Table 4 两结论成立
   ├─ 月度快照 checkout → 时间演化曲线                            ⬜ Fig 2/3 未做
   └─ gRPC-C 对照组：clang AST / pthread_* 计数                   ⬜ 未做
        │
⬜ P3 动态测量 ───────────────────────────────────► Table 3     ← 全阶段未开始
   ├─ gRPC 官方 benchmark 三种 workload                          ⬜
   ├─ Go 侧：runtime/trace 统计 goroutine 生命周期                ⬜
   └─ C 侧：/proc/<pid>/task 采样线程数                          ⬜
        │
🟡 P4 Bug 复现（核心工作量）───────────────────────► repro.csv（41 条）  ← 19/41（13 blocking + 6 non-blocking）
   ├─ 定位 buggy commit（fix commit 的 parent / git log -S 找引入点）  ✅ 19 条都定了 buggy 版本
   ├─ 检出 → 编译 → 按 bug report 触发 → 症状判定                 ✅ 双侧对照齐全
   └─ 非确定性处理：N 次重跑 + sleep 注入 + GOMAXPROCS 调整        ✅ grpc-1850 用 50 次循环把命中率做到 16~20%
        │
🟡 P5 检测器评测 ─────────────────────────────────► Table 8 / Table 12
   ├─ 内置 deadlock detector：看 "all goroutines are asleep - deadlock!"  🟡 仅 boltdb-392 一格（10/10）
   └─ go build -race：100 次重跑，统计检出率与首检出次数            ⬜ Table 12 为 0/20
        │
🟡 P6 统计与图表 ─────────────────────────────────► Fig 4 / Table 6,7,9,10,11
   ├─ lift = P(AB) / P(A)·P(B) + 卡方/Fisher 显著性                ⬜ 未算
   └─ bug 生命周期 CDF（引入 commit 时间 → 修复 commit 时间）        ⬜ Fig 4 未做
      （Table 6/7/9/10/11 的逐 bug 标签已在 data/ 里，只差统计脚本  🟡 数据齐、未出表）
```

---

## 2. 工具与依赖清单

| 类别 | 工具 | 版本/说明 | 用途 |
|---|---|---|---|
| 版本控制 | git | ≥2.30 | 克隆、`git log --grep` 过滤、按时间取快照 |
| Go（旧） | Go **1.10 / 1.11** | 关键。论文数据窗口为 2015-02 ~ 2018-05，Docker/K8s/etcd 老 commit 用的是 GOPATH + vendor / dep，现代 Go 直接编不过 | P4 编译 buggy 版本；P5 跑内置 detector |
| Go（新） | Go 1.21+ | 对照实验：新版 `-race` 与旧版检出率差异 | P5 补充实验 |
| 静态分析 | `tools/goast`（本仓库自研） | go/ast + go/parser，无需 cgo | P2 统计创建点与原语使用 |
| 静态分析（C） | clang `-Xclang -ast-dump` 或 `cloc` + grep | gRPC-C 只有 lock，统计 `pthread_create` / `pthread_mutex_*` | P2 对照组 |
| 代码量 | `cloc --json` 或 `gocloc` | 计算每 KLOC 归一化 | Table 2、Table 4 |
| 运行时测量 | `runtime/trace`、`pprof`、`runtime.NumGoroutine` | Go 自带 | P3 goroutine 数量/时长 |
| 运行时测量（C） | `/proc/<pid>/task`、`perf sched` | Linux | P3 线程数/时长 |
| Benchmark | gRPC 官方 `benchmarks` 套件（qps 驱动） | 三种 workload：`g_sync_ping_pong`、`sync_ping_pong`、`qps_unconstrained` | P3 |
| 复现沙箱 | Docker + 每项目一个 Dockerfile | Docker/K8s/CRDB 需要 root、网络命名空间、多进程 | P4 隔离与可重复 |
| 统计绘图 | Python 3.10+、pandas、numpy、scipy、matplotlib | 见 `scripts/04_stats_figures.py` | P6 |
| 标注 | ~~双人独立标注 + Cohen's kappa~~ | **按 §0.6 取消**：标签全部采用 artifact，无第二套独立判定可比 | P1 |
| 辅助 | `timeout`、`gdb`、`SIGQUIT`（Go 会打印全部 goroutine 栈） | 判定 blocking 的关键手段 | P4/P5 |

> **平台建议**：在 Linux（或 WSL2 / Ubuntu 容器）里做 P3/P4/P5。Windows 上 `-race` 需要 cgo + gcc，且 Docker/K8s 老版本行为差异大；本仓库脚本可在 Windows 编辑，但执行建议在 Linux。

**【现状】这份清单里真正用上的只有一半**

| 用上了 | 没用上 | 说明 |
|---|---|---|
| git、Go 1.10.8（GOPATH）、自研 `goast`、`cloc`/代码行统计、`timeout` + SIGQUIT 判 hang、pandas | clang AST、`runtime/trace`、`/proc/<pid>/task`、gRPC 官方 benchmark、scipy、`sklearn` 的 kappa、perf | 没用上的六项分别对应 P3（两项半）、P2 的 gRPC-C 对照、P6 的显著性检验；其中 `sklearn`/kappa 已按 §0.6 **明确取消**，其余五项落在未完成阶段 |

另外，实际执行时的 Go 版本比清单里写的"1.10/1.11"更分散：**共五个主版本**——1.6.4（boltdb-begin-lock-leak、boltdb-341）、1.10.8（grpc 全系、boltdb-7fb06fee）、1.8.7 + 1.26.8 双跑（etcd、kubernetes 部分）、1.26.8（boltdb-392、cockroachdb、k8s-62464）、1.18.1（moby-17176）。不是混乱，是"老代码必须用老工具链"的必然结果，但**这份差异目前没有任何文档记录**，评审看不出 pin 在哪里。

---

## 3. 各阶段详细步骤

### P0 环境与数据准备 ✅（已完成，实测结果见 `report/appendix/p0_repo_pin.md`）

**关键动作：把上游仓库 pin 到论文的数据收集日。** 这一步决定了后面所有数字能否对齐。

切点 **2018-05-21** 不是估的：artifact 的 `bug table.xlsx / application` 表里 Date 列的 Excel 序列号是 43241，六行全是这个值。取 `--before=2018-05-22` 才能包含当天全天。

**路径策略**（不写死，换机器不用改代码）：

| 项 | 默认位置 | 覆盖方式 |
|---|---|---|
| 上游仓库 | 项目根下 `6app/`（也认 `repos/`） | `REPO_ROOT` |
| pin 表 / 日志 | `repro/logs/` | `LOG_DIR` |
| 报告 / 中间结果 | `repro/out/` | `OUT_DIR` |
| 二进制（goast） | 系统临时目录 | `BIN_DIR` |
| Go 工具链 | `PATH` 里的 `go` | `GO_MODERN` / `GO_LEGACY` |

解析逻辑集中在 `scripts/_paths.sh`（bash）与 `00_env_report.py` 顶部的同名函数（python），
两者优先级一致：环境变量 > `repro/local.env` > 项目内自动探测。

机器相关项写 `repro/local.env`（不进版本库，模板 `local.env.example`）。
之所以要单独掏出这个文件：这台 Windows 上「放在 Desktop 下的自编译 exe」会被系统策略
拒绝读写文件（`winapi error #5`），所以 `BIN_DIR` 指向 `C:/gs/bin`；Linux 上没有这个限制。

**实测切割结果**（`scripts/00_setup_repos.sh` 取上界 → `scripts/00_pin_exact.sh` 精确对齐）：

| 项目 | 最终 commit | 日期 | commit 数 | 论文 | 误差 | 克隆方式 | 已 checkout |
|---|---|---|---|---|---|---|---|
| BoltDB | `fd01fc79c553` | 2018-03-02 | 816 | 816 | **0** | 完整 | 是 |
| etcd | `346589edd1dc` | 2018-05-21 | 14101 | 14101 | **0** | 完整 | 是 |
| gRPC-Go | `f66923519395` | 2018-05-21 | 2528 | 2528 | **0** | 完整 | 是 |
| Docker | `9bd5d9912f0c` | 2018-05-22 | 35149 | 35149 | **0** | treeless | 是 |
| CockroachDB | `cc4511e1be86` | 2018-05-22 | 29485 | 29485 | **0** | treeless | 否（按需） |
| Kubernetes | `1f0d9505790c` | 2018-05-22 | 65684 | 65684 | **0** | treeless | 否（按需） |

**6/6 全部零误差**。这个结果不是一次 clone 就有的，中间有两步：

第一步 `--before=2018-05-22` 钉到的是「含 5-21 全天」的上界，必然偏大：BoltDB +0、gRPC-Go +3、etcd +6、Docker +11、CRDB +41、K8s +41。

偏差的来源是 `--before=DATE` **左闭右开**：`--before=2018-05-21` 是「截至 5-20 结束」，`--before=2018-05-22` 才是「含 5-21 全天」。两个上界都测出来，能看到论文值严格夹在中间，说明作者是 5-21 当天某个时刻取样：

| 项目 | 截至 5-20 结束 | 截至 5-21 结束 | 论文报告 | 论文落在当天的 |
|---|---|---|---|---|
| etcd | 14088 | 14107 | **14101** | 第 13 / 19 个 |
| gRPC-Go | 2527 | 2531 | **2528** | 第 1 / 4 个 |
| Docker | 35143 | 35160 | **35149** | 第 6 / 17 个 |
| CockroachDB | 29474 | 29526 | **29485** | 第 11 / 52 个 |
| Kubernetes | 65680 | 65725 | **65684** | 第 4 / 45 个 |

第二步 `00_pin_exact.sh` 从 5-21 上界沿 first-parent 往回走，逐步算 `rev-list --count`，找到计数**与论文完全相等**的 commit。first-parent 链上计数单调不减（普通提交 +1，merge 提交 +1 + 侧分支提交数），往回走单调下降、线性收敛，实测最多 19 步就到：

| 项目 | 5-21 上界 | 计数 | 回溯步数 | 精确 commit | 计数 |
|---|---|---|---|---|---|
| BoltDB | `fd01fc79c553` | 816 | 0 | `fd01fc79c553` | 816 |
| etcd | `7940113906db` | 14107 | 7 | `346589edd1dc` | 14101 |
| gRPC-Go | `c16e07b13065` | 2531 | 4 | `f66923519395` | 2528 |
| Docker | `da99009bbb11` | 35160 | 5 | `9bd5d9912f0c` | 35149 |
| CockroachDB | `7c7818fd6d8e` | 29526 | 17 | `cc4511e1be86` | 29485 |
| Kubernetes | `e85b81bbee09` | 65725 | 19 | `1f0d9505790c` | 65684 |

值得做这一步的原因：P2 的 LOC 统计、P4 的源码快照都锚在与论文同一时刻的代码上，后面任何数字对不上时就不会再有"是不是快照新了几个 commit"这种噪声。原始推导记录在 `C:/gs/logs/pin_exact.tsv`。

**两个关键技巧（都是踩坑后得出的）**：

1. **必须用 `--first-parent` 取切点**。不加的话 `rev-list -1 --before=DATE` 会挑到"同一天合并进来的侧分支 commit"，它的祖先链可能很短——moby 上实测得到 2560 个 commit，而正确值是 35160。
2. **大仓库用 `--filter=tree:0 --no-checkout`**。moby 完整 pack 超过 1GB，代理下反复中断且每次重试都从头开始；tree:0 只拉 commit 对象（34MB），`git log --grep` 和 `rev-list --count` 都照常工作。P2/P4 真要读代码时，再对单个 commit 执行 `git checkout <sha>` 按需拉取。

```bash
# 完整流程（已跑通）
bash scripts/00_setup_repos.sh          # 克隆 + 冻结，存在即跳过；可只传某个 app
python scripts/00_parse_artifact.py     # artifact → bugs_master.csv
python scripts/00_env_report.py --static
```

**旧工具链的验证**：用 Go 1.10.8 在 GOPATH 模式下成功编译了老版 BoltDB（`go build ./cmd/bolt`），说明 P4 的编译路径可行。注意 BoltDB 的主包在 `cmd/bolt` 而非仓库根目录，根目录是库包，`go build .` 只会产出 `.a` 归档。

**【现状】✅ 完成，且是整篇里最扎实的一段**

- 6 个仓库 pin 到论文数据收集日，commit 数 **6/6 零误差**；`--first-parent` 与 `--filter=tree:0` 两个技巧都写进了脚本，换机器可重跑。
- 论文 Table 1 的 commit 数已对齐；**LOC 在 P2 顺带算出**（六仓库平均绝对偏差 0.7%），但 Table 1 本身没有独立成表——Stars / Contributors / Description 是直接抄 artifact 的。
- 唯一遗留：`out/p0_env_report.md` 这个路径在交付目录里不存在，实际内容在 `report/appendix/p0_repo_pin.md`（已就地改正标题里的路径）。

---

### P1 Bug 收集与分类 🟡

1. **关键词过滤** ✅（脚本 `scripts/01_mine_commits.py`）。论文关键词：
   `race, deadlock, synchronization, concurrency, lock, mutex, atomic, compete, context, once, goroutine leak`
   其中 `context` / `once` / `goroutine leak` 是 Go 特有原语与特有问题，其余沿用传统并发 bug 研究的关键词表。
2. **去重与抽样** ❌ 不做（决定见 §0.6）：3211 个候选 commit 中随机抽样，逐条判断"是否修复并发 bug"。论文最终留下 171 个。
3. **二维分类** 🟡（这是论文方法论的核心，复现时要严格按定义执行）：
   - **行为维度**：blocking（有一个以上 goroutine 无法推进）vs non-blocking（都能结束但结果不对）。注意 blocking 定义**宽于 deadlock**，包含无环等待（如等一个永远没人 send 的 channel）。
   - **致因维度**：shared memory（Mutex/RWMutex/WaitGroup/Cond）vs message passing（chan / chan 与其他原语混用 / context、Pipe、time 等库）。
4. **修复策略分类** 🟡：Adds / Moves / Changes / Removes / Misc（照搬 Table 7、Table 10 的枚举）。
5. **一致性校验** ❌ 不做（决定见 §0.6）：两人独立标注 30% 样本，算 Cohen's kappa（论文未报告，但这是复现"人工环节"唯一可量化的办法）；再与 artifact 的 `bug table.xlsx` 比对，一致率作为你的复现质量指标。

**输出**：`data/bugs.csv`
```
bug_id, app, behavior, cause, cause_sub, fix_strategy, fix_primitive,
fix_commit, introduced_commit, introduced_date, fixed_date, report_url, notes
```

**【现状】🟡 第一步做得很细，第二、五步按 §0.6 明确不做**

| 步骤 | 状态 | 实测 |
|---|---|---|
| 1 关键词过滤 | ✅ | 测了 4 种匹配口径：标题 3,105（**−3.3%**，落在 ±10% 内）、全文 8,500（+164.7%）、中间两种 4,347 / 5,155。**但候选清单没有落库**——`find` 全库无 `commits.csv`，只有报告里的汇总数字 |
| 2 人工判定 171 | ❌ 不做 | 171 与全部标签直接取自 artifact。`p1_limitation.md` 已写明"未复现人工判定环节"，现在这条从"未完成"升级为"已声明的口径选择" |
| 3 二维分类 | 🟡 | `bugs_master.csv` 171 行：85 blocking / 86 non-blocking、105 shared-memory / 66 message-passing，**与论文 Table 5 逐格一致**；口径是 recount，不是 re-annotate（§0.6） |
| 4 修复策略分类 | 🟡 | artifact 的两张逐 bug 表自带标签，重算与 Table 7 / 10 / 11 完全一致；`bugs_master.fix_strategy` 仍 171 行全空，但**不再需要回填**——统计直接从 artifact 表算 |
| 5 一致性校验 | ❌ 不做 | kappa 取消。原先做的 34/44 候选交叉验证保留为旁证，但它验证的是关键词匹配口径，不是人工判定质量 |

**输出格式对不上**：方案要的是 `data/bugs.csv`（13 列），实际交付的是 `data/bugs_master.csv`（14 列，字段名不同，且 `fix_strategy` 空）。既然 §0.6 已定"统计直接读 artifact 两张表"，`bugs_master.csv` 就退为索引表，下游脚本**不要再依赖它的 `fix_strategy` 列**。

⚠️ 一处转述要改：验收清单 P4 那条写"论文自报 41/41 但承认有放弃项"，**论文原文没有这句话**。§4 只有一句 "we reproduced 21 blocking bugs and 20 non-blocking bugs"，没说从多少里挑、放弃多少。

---

### P2 静态测量 🟡

**为什么不能只用 grep**：`go func(){}()` 与 `go f()` 要区分（Table 2 的 normal vs anonymous），`sync.WaitGroup` 与同名变量要区分，channel 的 `make/send/recv` 是三种不同"使用"。必须走 AST。

`tools/goast` 的统计口径（口径必须写进文档，否则数字无法对齐）：

| 论文类别 | AST 判定规则 |
|---|---|
| GoStmt (normal) | `*ast.GoStmt` 且 `Call.Fun` 不是 `*ast.FuncLit` |
| GoStmt (anonymous) | `*ast.GoStmt` 且 `Call.Fun` 是 `*ast.FuncLit` |
| Mutex | 对 `sync.Mutex` / `sync.RWMutex` 类型变量调用 `Lock/Unlock/RLock/RUnlock` 的次数 |
| atomic | `atomic.*` 选择子调用 |
| Once | `Once.Do(...)` |
| WaitGroup | `WaitGroup.Add/Done/Wait` |
| Cond | `Cond.Wait/Signal/Broadcast` |
| chan | `make(chan ...)` + `ch <- x`（SendStmt）+ `<-ch`（UnaryExpr/ARROW） |
| Misc | `context.*`、`io.Pipe` 等 Go 特有消息传递库 |

执行：

```bash
python scripts/02_static_metrics.py --repo ../moby --app docker --out out/static_docker.json
```

时间演化（Fig 2 / Fig 3）⬜：以月为步长，`git rev-list -1 --before=<月末> master` 取快照，逐快照跑一遍 goast，得到"shared memory 占比 / message passing 占比"的时序 → `scripts/03_history_usage.py`。

gRPC-C 对照组 ⬜：`grep -c pthread_create` + `clang -Xclang -ast-dump` 统计锁使用（论文结论：gRPC-C 仅 5 个线程创建点、0.03/KLOC、只用 lock 且 746 处）。

**【现状】🟡 Table 2 / Table 4 完成，Fig 2/3 与 gRPC-C 两个"对照"没做**

- **Table 2 ✅**：自己写 `goast` 重算，六个项目平均偏差 4.5%。逐项：Docker 0.186 / 0.18（+3.3%）、etcd −9.1%（最大偏差）、gRPC-Go 0.909 / 0.83（**+9.5%，超出论文给的 0.18~0.83 上限**）、BoltDB 0.22 / 0.22。
- **Table 4 ✅ 但有保留**：Mutex 在六个项目均为占比最高、chan 落在 18.48%~42.99% 区间，两条支柱结论成立。Once 与 atomic 不可比——论文的归类规则与常规理解不同，没有原作者脚本无法判定，已在 `p2_static.md §4.3` 如实标注为不可比。
- **Fig 2 / Fig 3 ⬜**：`scripts/03_history_usage.py` 从未创建，`report/figures/` 只有一个 `.gitkeep`。这是纯时间开销（六仓库逐月 checkout 再跑 goast），评估为 2~3 天。
- **gRPC-C 对照 ⬜**：全库 0 处提及 gRPC-C。这是论文里唯一一个"跨语言对照"，缺了它，Observation 1（goroutine 更短更频繁）就只有 Go 侧数据，无法成立。
- 口径补充：方案没写 Fig 2/3 的步长、纵轴口径与 2015-02 起点怎么定，实际执行前必须补齐，否则做出来的曲线无法与论文对齐。

---

### P3 动态测量 ⬜（未开始）

1. 编译 gRPC-Go 与 gRPC-C 的 benchmark client/server（同一份 qps 场景配置）。
2. 三种 workload：`g_sync_ping_pong`、`sync_ping_pong`、`qps_unconstrained`。**注意**：因为 gRPC-C 更快，两者要跑"相同请求数"而不是"相同时长"。
3. 采集指标：
   - Go：`runtime/trace`（最准，能给出每个 goroutine 的起止时间）+ `NumGoroutine` 采样作交叉验证；
   - C：100ms 采样 `/proc/<pid>/task` 目录条目数。
4. 归一化：`归一化时长 = 所有 goroutine 平均存活时长 / 程序总运行时长`（论文强调不能比绝对值，因为两边总时长不同）。
5. 产出：`out/dynamic.csv`，列 = workload, side(client/server), goroutine/thread 比值, 归一化平均时长。

**【现状】⬜ 零进度，且是全篇最贵的一项**

全库检索 `ping_pong` / `qps_unconstrained` / `runtime/trace` / `/proc/<pid>/task` 均为 0 命中——不是"做了没记"，是真的没启动。原因是要先编出 gRPC-C（C++ 工具链 + 2018 年的 submodule），再配同一份 qps 场景，两侧同时插桩。评估 3~5 天，建议在报告里明确写"未覆盖 Table 3"，而不是拖到最后一天硬上。

---

### P4 单个 Bug 的复现流程（核心）🟡

对每个 bug 执行五步：

```bash
# 1) 定位 buggy 版本
fix=$(grep -o '^commit [0-9a-f]*' blocking-bugs/boltdb/defdb74*.txt | cut -d' ' -f2)
buggy=$(git rev-parse ${fix}^)      # 修复补丁的父提交 = 有 bug 的版本

# 2) 检出并编译（老项目需 GOPATH + vendor）
git checkout $buggy && GO111MODULE=off go build ./...

# 3) 用 bug report 里的触发方式运行，加超时
timeout 60 ./buggy_binary < trigger_args > run.log 2>&1

# 4) 症状判定（blocking）
#    方法 A：超时未退出 → 判定 hang
#    方法 B：向进程发 SIGQUIT，Go runtime 会 dump 全部 goroutine 栈，
#            检查是否有 goroutine 卡在 chan send/recv、sync.Mutex.Lock、Cond.Wait
kill -QUIT $pid

# 5) 重复 N 次统计成功率；失败则注入 sleep 放大窗口
for i in $(seq 1 $N); do ... ; done
```

**非确定性处理**（论文原话：有时要跑很多次，或手工加 sleep）：
- `GOMAXPROCS=1` 放大特定交错；
- 在关键临界区前后插 `time.Sleep`；
- 用 `-race` 会改变时序，**评测 detector 时要与"纯复现"分开跑**，否则会把"detector 改变了调度导致没复现"误判成"detector 没检出"。

**判定标准必须预先写死**，否则 41 个 bug 的结果不可比。建议每个 bug 填 `data/repro.csv`：
```
bug_id, app, behavior, buggy_commit, go_version, build_cmd, trigger_cmd,
runs, successes, symptom_type(hang/panic/wrong_output), evidence_log, reproduced(0/1)
```

**预期难点**：
- Docker / Kubernetes / CockroachDB 的触发往往需要一个完整集群（etcd 依赖、`--privileged`、多节点），需要写 compose 或 minikube 场景；
- 部分 commit 依赖已下线的私有仓库/旧版 `dep` 锁文件 → 用 `vendor/` 目录 + `GOFLAGS=-mod=vendor`；实在不行用 Go module 的 `replace` 打补丁；
- 论文自己承认有 bug 因"找不到依赖库"或"观察不到描述的症状"而放弃复现，复现时允许同样放弃，但要记录原因。

**【现状】🟡 19/41，验收线（≥25/41）未达成，差 6 条**

已复现的 19 条（`code/cases/`，一条 bug 一个自包含目录：README + 可运行代码 + 原始日志 + 截图）：

| 类 | 条数 | 目录 |
|---|---|---|
| blocking | **13** | `boltdb-392`、`boltdb-begin-lock-leak`、`cockroachdb-1cc69980`、`etcd-6873-double-lock`(2 条)、`grpc-793`、`grpc-1293`、`grpc-1424`、`grpc-1459`、`grpc-1850`、`kubernetes-62464-20697`(2 条)、`moby-17176` |
| non-blocking | **6** | `boltdb-341`、`boltdb-7fb06fee`、`etcd-4997`、`grpc-1667`、`grpc-1687`、`kubernetes-9926` |

- **质量是够的**：每条都有 buggy / fixed 双侧对照与原始输出，不存在"只有断言没有日志"的情况。
- **非确定性处理已落地**：grpc-1850 靠 50 次循环把命中率做到 16~20%（fixed 侧 50/50 PASS），并为此修正了判定口径——原来只认 `test timed out`，漏掉了 RPC 自身 deadline 先到的 `DeadlineExceeded`；grpc-1459 从第 3 次 RPC 起必死锁；grpc-1667 在 `-race` 下必报 `mapassign_fast64`。
- **未纳入的 22 条**：多数需要完整服务栈（Docker daemon、K8s 集群、etcd 多节点）才能触发，超出单机范围。报告里要写成主动的抽样说明，不要写成"来不及"。

⚠️ **一个会挡住 P5 / P6 的硬问题**：方案定义的 `data/repro.csv` 有 12 个字段，其中 `go_version` / `build_cmd` / `trigger_cmd` / `runs` / `successes` / `symptom_type` / `evidence_log` / `reproduced` 是**机器可读列**；实际交付的 `results/data/repro_summary.csv` 只有 11 列（`case, category, repo, bug_id, fix_commit, buggy_basis, trigger, buggy_verdict, fixed_verdict, owner, evidence`），判定结果写成了"死锁 10/10"这类中文描述。P5 要按 behavior 分组算检出率、P6 要算交叉表，都必须读数值列——**这张表不补字段，P5 / P6 的脚本写不出来**。补它约半小时（19 行，字段从各 case README 抄）。

---

### P5 检测器评测 🟡

**内置 deadlock detector** 🟡：Go runtime 调度器内置，永远开启，判定条件是"整个进程没有 goroutine 能推进"。直接把复现成功的 blocking bug 跑一遍，抓 `fatal error: all goroutines are asleep - deadlock!`。论文对每个 bug 只跑一次（因为这些 bug 的阻塞是可确定性触发的）。预期：21 个里只中 2 个（都是 BoltDB）。失败原因要能解释：①还有别的 goroutine 在跑就不算 deadlock；②只检查 Go 原语上的阻塞，不检查等外部系统资源的 goroutine。

**`-race` detector** ⬜：`go build -race`，每个 non-blocking bug 跑 100 次，统计"100 次内是否报告"。预期 10/20（traditional 7/13、anonymous 3/4、lib 0/2、chan 0/1），其中 6 个首次运行即报，4 个要跑接近 100 次。注意 `-race` 只覆盖 data race，atomicity violation / order violation 天然检不到。

**【现状】🟡 Table 8 只有一格，Table 12 完全没跑**

| 子项 | 状态 | 实测 |
|---|---|---|
| deadlock detector | 🟡 1/13 | 只有 `boltdb-392` 做过，**10/10 全中**——它恰好是论文点名能被检出的两条之一（另一条 BoltDB#240 未纳入本次集合）。其余 12 条没跑 |
| `-race` ×100 次 | ⬜ 0/6 | 没有任何 non-blocking bug 在 `-race` 下做过检出评测；`-race` 只出现在 boltdb-392 的环境说明与 grpc-1667 的复现里，不是检出率统计 |

- **验收线要重写**：论文是 2/21 与 10/20，我们的分母只有 13 与 6，方案写的"≤3/21 与 8~12/20"天然打不满。正确写法是"在 13 条中检出 x 条（y%），方向与论文一致"，不做比例复现的声明。
- **别把两个数并排放**：boltdb-392 的 10/10 是"这条 bug 自己的检出率"，论文的 2/21 是"全体集合的覆盖率"，并列成对比会被问穿。
- **`-race` 的环境坑**：`TestDB_Open_InitialMmapSize` 在 `-race` 下必失败（`unexpected that the reader blocks writer`），那是时序断言被拖慢导致的、不是 data race，混进分子会虚增检出率——这条 10-26 已经踩过一次。

---

### P6 统计与图表 🟡

- **lift** 🟡：`lift(A,B) = P(AB) / (P(A)·P(B))`。>1 正相关，=1 独立。论文只对样本量 >10 的类别计算（小样本无统计意义）。复现时建议补一个 Fisher 精确检验的 p 值，说明显著性——这是比原文更严谨的加分项。
- **Fig 4（bug 生命周期 CDF）** ⬜：需要 `introduced_date`。artifact 只给修复 commit，引入时间要用 `git log -S"<修复中改动的关键行>" --reverse` 或 `git blame <fix>^` 反查，属于 P4 的副产物。
- 所有表/图与脚本的映射写进 `README`，保证"图从数据来" 🟡。

**【现状】🟡 五张表的数据全在手，一张都没出；lift 与 Fig 4 未做**

`code/analysis/04_stats_figures.py` 从未创建，全库搜不到 `lift` / `kappa` / `cdf` 任何一个词。但**逐 bug 标签是齐的**——`data/bug_table_blocking.csv`(85 行) 与 `data/bug_table_non_blocking.csv`(86 行) 里，我逐列数过，重算结果与论文逐格一致：

| 论文表 | 论文值 | 用现有 CSV 重算 |
|---|---|---|
| Table 6 blocking 致因 | 28 / 5 / 3 / 29 / 16 / 4 | **28 / 5 / 3 / 29 / 16 / 4** ✅ |
| Table 7 blocking 修复 | 31 / 14 / 9 / 21 / 10 | **31 / 14 / 9 / 21 / 10** ✅ |
| Table 9 non-blocking 致因 | 46 / 11 / 6 / 6 / 16 / 1 | **46 / 11 / 6 / 6 / 16 / 1** ✅ |
| Table 10 non-blocking 修复 | 42 / 17 / 10 / 14 / 3 | **42 / 17 / 10 / 14 / 3** ✅ |
| Table 11 补丁内原语 | 32 / 19 / 10 / 7 / 4 / 3 / 19 | **32 / 19 / 10 / 7 / 4 / 3 / 19** ✅ |

也就是说**这 5 张表 + 2 组 lift 只需一个统计脚本**，半天工作量。但报告里必须写清"按 artifact 逐 bug 标签重算（recount），未独立复判（re-annotate）"，否则等于宣称自己重做了人工分类。`bugs_master.fix_strategy` 171 行全空，正是这一层没人碰过的证据。

- **lift 未算**：论文报了 6 个关键值（Mutex→Moves 1.52、Chan→Adds 1.42、chan→chan 2.7、anon→data private 2.23、misuse chan→Moves 2.21），全部可由现有标签算出，但一个都没算。
- **Fig 4 未做**：缺 `introduced_date`，要 `git blame` 反查 41 条的引入 commit，约一天。`feasibility_44.csv` 里已有 `fix_date`，缺的是前半截。
- **脚本映射缺失**：`report/figures/` 只有一个 `.gitkeep`，"图从数据来"这条目前无图可映射。

---

## 4. 工程结构

```
repro/                                    ← 实际交付改成了 code/ data/ docs/ report/ results/
├── 复现方案.md              # 本文档            ✅ docs/original-group-README.md 另存旧版
├── README.md                # 操作手册（命令级）  ✅ 但三段缺：clean-machine 步骤、期望输出、耗时
├── go.mod                   # tools/goast 模块（仅标准库）  ✅
├── config/apps.yaml         # 项目清单 / 关键词 / 原语口径 / 快照时间  🟡 并入 code/analysis/local.env 与脚本常量
├── tools/goast/main.go      # AST 静态统计器（P2）  ✅ code/tools/goast
├── scripts/
│   ├── 00_parse_artifact.py # P0 artifact → bugs_master.csv + 校验报告  ✅
│   ├── 00_setup_repos.sh    # P0 克隆 6 仓库并冻结快照              ✅（另有 00_pin_exact.sh 精确对齐）
│   ├── 00_env_report.py     # P0 环境与快照汇总                    ✅
│   ├── 01_mine_commits.py   # P1 关键词挖掘 → commits.csv          ✅ 脚本在，产物未落库
│   ├── 02_static_metrics.py # P2 调用 goast + KLOC 归一化          ✅
│   ├── 03_history_usage.py  # P2 月度快照 → Fig 2/3 时序            ⬜ 未创建
│   ├── 04_stats_figures.py  # P6 lift / CDF / 交叉表               ⬜ 未创建
│   └── 05_repro.sh          # P4 单 bug 复现驱动模板                🟡 改成 code/harness/p4_case.sh + 每 case 一个 run.sh
├── data/                    # bugs_master.csv（171 行主表）, artifact_manifest.csv（169 个补丁）  ✅ 实为 8 个文件
└── out/                     # 报告与图表                          🟡 out/ 改为 report/appendix + results/
```

**【现状】结构已改过一次，上面的树只作设计参考**

实际交付是 `code/{analysis,harness,tools,cases}` + `data` + `docs` + `report` + `results`，一条 bug 一个自包含目录（`code/cases/{blocking,non-blocking}/<bug>/`），说明、可运行代码、原始日志、截图同处。逐文件对照见 `docs/MIGRATION.md`。

- **多出来 4 个方案没列但实际在用的脚本**：`03_compare_paper.py`（与论文数字对照）、`06_feasibility.py`（44 条可行性分级）、`07_audit_bug_table.py`（标注表体检）、`check_pins.py`（校验 6 仓库 pin）。
- **`data/` 实际是 8 个文件**，不止上面写的 2 个：另有 `bug_table_application.csv`(Table 1)、`bug_table_blocking.csv`(85 行)、`bug_table_non_blocking.csv`(86 行)、`repo.lock.tsv`(6 仓库精确 commit)、`repro_targets.csv`(41 条)、`feasibility_44.csv`。
- **P4 的驱动脚本换了形态**：方案设想一个 `05_repro.sh` 通吃，实际拆成通用 `code/harness/p4_case.sh` + 每 case 一个 `run.sh`（因为每个 bug 的判定信号不同，通吃的模板反而更绕）。

---

## 5. 风险与已知偏差（写进报告里的"有效性威胁"）

1. **数字无法逐位对齐** ✅ 已解决：仓库持续演进，除非严格冻结快照。应对：冻结到 2018-05-31，并在报告中说明"快照 + 截止日期"。——实际冻结到 **2018-05-21**（论文数据收集日），6 仓库 commit 数 6/6 零误差。
2. **原作者工具未开源** 🟡 已应对但未收口：Table 2/3/4 只能"同方法重实现"，不是"精确复原"。应对：把统计口径显式写死，报告自己的数字 + 与论文的偏差方向（例如你的 chan 计数若包含 send/recv，比例会系统性偏高）。——Table 2 已重实现并记录偏差，Table 3 未做。
3. **人工分类不可复现** ❌ 已转为声明的口径（见 §0.6）：171 这个数字本身依赖研究者的判断。应对：**不做重复判定**，直接采用 artifact 的公开标签，并在报告里把 Table 5 / 6 / 7 / 9 / 10 / 11 明确定性为"重排版（recount）"而不是"复现"。——原计划的 kappa 检验一并取消：没有第二套独立标签，算不出有意义的一致性。
4. **工具链腐化** 🟡 已发生：Go 1.10 的 `dep`、已下线的私有依赖、`golang.org/x/...` 的 API 变更。应对：容器化 + 逐 bug 记录 Go 版本。——逐 case 的 Go 版本记在各自 README，但**没有汇总表**，且实际用了五个主版本（1.6.4 / 1.8.7 / 1.10.8 / 1.18.1 / 1.26.8），评审看不出 pin 在哪。
5. **`-race` 干扰时序** ✅ 已分离：导致复现率下降，被误读为"detector 无效"。应对：把"复现"与"检测"两套运行分离，并报告两者的成功率。——grpc-1850 / grpc-1459 / grpc-1667 都是先纯复现、再单独看 `-race`。
6. **现代 Go 的差异** ⬜ 未做：Go 1.14+ 引入异步抢占、1.20+ 改了 `-race` 实现，重跑结果可能优于论文（这是可写的发现，不是 bug）。——旧版与新版对照实验未启动。

---

## 6. 验收清单

- [x] **P1：候选 commit 数量与 3211 同量级（±10%）** —— 3,105（−3.3%），达标；"抽样判定流程可审计"按 §0.6 **改为"标签可追溯"**：每张表都要能指到 artifact 的哪一列、哪一行
- [ ] ~~**P1：与 artifact 的复现 bug 列表 100% 对齐**~~ —— 按 §0.6 该条作废：既然标签全部采用 artifact，与自身对齐不构成检验。实测 34/44 的候选交叉验证降级为关键词口径的旁证（分母 41 / 44 本就不是同一集合）
- [x] **P2：六项目创建点每 KLOC 落在 0.18~0.83；gRPC-Go ≫ gRPC-C 的定性结论成立** —— 前半达标（五项在内，**gRPC-Go 0.909 超上限 9.5%**）；后半**未做**（gRPC-C 对照缺失）
- [x] **P2：Mutex 在六项目中均为占比最高原语；chan 占比 18%~43% 区间** —— 两条均成立（18.48%~42.99%）
- [ ] **P3：三个 workload 下 goroutine 数均多于线程数，且归一化时长更短** —— 全阶段未开始
- [ ] **P4：≥ 25/41 成功复现** —— 实际 **19/41（46%）**，差 6 条。⚠️ 原句"论文自报 41/41 但承认有放弃项"**不是论文原话**，§4 只写了 reproduced 21 + 20，建议删掉这半句
- [ ] **P5：deadlock detector 检出 ≤ 3/21；`-race` 检出 8~12/20** —— 分母只有 13 / 6，这条验收线本身要重写为"在 13 条中检出 x 条，方向一致"
- [ ] **P6：lift 最强组合方向一致（Mutex→Moves、chan→chan）** —— 数据齐，lift 一个都没算
- [ ] **报告：显式列出所有"重实现"与"不可复现"的部分** —— 部分完成：P1 / P2 的偏差已写进 `report/appendix/`，P3 / P5 / P6 尚无对应报告

**合计：9 条里 3 条达标、1 条作废（§0.6）、5 条未达标。**

---

## 7. 论文做了什么、方案覆盖到哪（补充对照）

论文自报的实验活动可拆成 19 个可执行操作。**方案写进了 18 个，唯一遗漏是论文 §7 的自研匿名函数检测器**（原文只有一句"已发现几个新 bug，其中一个被开发者确认"，无数字，不可复现）。逐项位置与状态：

| # | 论文操作 | 出处 | 方案里在哪 | 状态 |
|---|---|---|---|---|
| 1 | 6 个应用元信息 | §2.4 Table 1 | P0 | 🟡 commit 数已对齐，LOC 在 P2 顺带算出，未独立成表 |
| 2 | 11 关键词过滤 → 3,211 | §4 | P1 第 1 步 | 🟡 3,105，清单未落库 |
| 3 | 人工判定 → 171 | §4 | P1 第 2、5 步 | ❌ 不做，标签全部采用 artifact（§0.6） |
| 4 | 二维分类 Table 5 | §4 | P1 第 3 步 | ✅ 85/86、105/66 一致（重算） |
| 5 | bug 生命周期 Fig 4 | §4 | P6 | ⬜ |
| 6 | 复现 41 条 | §4 | P4 | 🟡 19/41 |
| 7 | Table 2 创建点 | §3.1 | P2 | ✅ 平均偏差 4.5% |
| 8 | gRPC-C 线程创建点 | §3.1 | P2 末段 | ⬜ |
| 9 | Table 3 动态测量 | §3.1 | P3 | ⬜ |
| 10 | Table 4 原语用量 | §3.2 | P2 | ✅ 两条结论成立 |
| 11 | gRPC-C 原语对照（746 vs 786） | §3.2 | P2 末段 | ⬜ |
| 12 | Fig 2 / Fig 3 时序 | §3.2 | P2 时间演化 | ⬜ |
| 13 | Table 6 blocking 致因 | §5.1 | P1 第 3 步 + P6 | 🟡 按 artifact 标签重算，未出表 |
| 14 | Table 7 + lift | §5.2 | P1 第 4 步 + P6 | 🟡 同上，lift 未算 |
| 15 | Table 8 死锁检测 | §5.3 | P5 | 🟡 1/13 |
| 16 | Table 9 non-blocking 致因 | §6.1 | P1 + P6 | 🟡 按 artifact 标签重算，未出表 |
| 17 | Table 10 / 11 + lift | §6.2 | P1 第 4 步 + P6 | 🟡 同上，lift 未算 |
| 18 | Table 12 `-race` | §6.3 | P5 | ⬜ 0/6 |
| 19 | 自研匿名函数检测器 | §7 | **无** | ❌ 不在本次范围 |

**方案自己加的、论文没做的 5 处**（写报告时单列，不要混进"复现"）：P1 的 Cohen's kappa（**已按 §0.6 取消**）、P6 的 Fisher 显著性检验、P5 的 Go 1.21+ 对照、P2 用 clang AST 数 gRPC-C（论文没说方法）、P0 把快照 pin 到具体 commit（论文只写数据收集日）。实际仍在做的是后 4 处。
