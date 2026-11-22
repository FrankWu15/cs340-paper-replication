# CS340 研究论文复现 · 小组交付

## CS340 Research Paper Replication

澳门科技大学 CS340 课程论文复现项目（2026–2027 学年）
Macau University of Science and Technology, CS340 Research Paper Replication (AY 2026–2027)

复现论文：*Understanding Real-World Concurrency Bugs in Go*（Tu, Liu, Song, Zhang; ASPLOS'19）
数据集：<https://github.com/system-pclub/go-concurrency-bugs>

> **当前进度（2026-11-22）**　论文标记为「已复现」的 **41 条**目标中完成 **24 条（59%）**；
> blocking **17/21（81%）**、non-blocking **7/20（35%）**。论文 19 项实验里
> **9 张表可以直接交付、其中 6 张逐格与论文一致**；两个检测器实验（Table 8 / Table 12）
> 有实测，但分母比论文小。逐条清单见 [docs/REPRODUCTION-TABLE.md](docs/REPRODUCTION-TABLE.md)。

本仓库只有一套结构：四位成员的产出已合并为统一布局，**一条 bug 一个自包含目录，按 blocking /
non-blocking 分两类**（33 个目录、35 个 bug 点）。往哪个目录放文件见 [docs/PLACEMENT.md](docs/PLACEMENT.md)，
旧材料搬到哪去了见 [docs/MIGRATION.md](docs/MIGRATION.md)。

## 组员 / Team Members

| GitHub | 姓名 Name | 学号 Student ID |
|---|---|---|
| FrankWu15 | 吴德诚 Wu Decheng | 1240012684 |
| DreamingZhu111 | 朱奕铭 Zhu Yiming | 1240012557 |
| icecream1293 | 李振炜 Li Zhenwei | 1240012318 |
| Semliii | 许汝轩 Xu Ruxuan | 1240011357 |

## 复现论文 / Selected Paper

- **论文 / Title**: Understanding Real-World Concurrency Bugs in Go (ASPLOS 2019)
- **作者 / Authors**: Tengfei Tu, Xiaoyu Liu, Linhai Song, Yiying Zhang
- **论文链接 / Paper**: <https://songlh.github.io/paper/go-study.pdf>
- **官方代码 / Artifacts**: <https://github.com/system-pclub/go-concurrency-bugs>

## 时间节点 / Milestones

- 组队截止 Team formation: 2026-10-25
- 换论文截止 Paper change deadline: 2026-11-01
- 最终答辩 Final presentation: 2026-12-01
- 每周 commit 检查 Weekly TA check: 每周日 23:59 / Every Sunday 23:59

---

# 一、现在做到哪了

## 1.1 一句话

论文从 171 个 bug 中挑出 41 个做复现实验（blocking 21 + non-blocking 20），我们复现了其中 **24 个**，
并把「复现形态」分成两栏记录——**真实源码跑通 11 条，最小复现体 8 条，另有 5 条早期案件没有形态记录**。
这个分栏是刻意保留的，理由见第三节。

## 1.2 按应用

| 应用 | 论文目标 | 已复现 | 覆盖率 | 未做 |
|---|---:|---:|---:|---:|
| etcd | 13 | 6 | 46% | 7 |
| grpc-go | 10 | 7 | 70% | 3 |
| boltdb | 4 | 3 | 75% | 1 |
| docker | 8 | 5 | 63% | 3 |
| kubernetes | 4 | 2 | 50% | 2 |
| cockroachdb | 2 | 1 | 50% | 1 |
| **合计** | **41** | **24** | **59%** | **17** |

## 1.3 按类型

| 类型 | 论文目标 | 已复现 | 覆盖率 | 未做 |
|---|---:|---:|---:|---:|
| blocking | 21 | 17 | 81% | 4 |
| non-blocking | 20 | 7 | 35% | 13 |
| **合计** | **41** | **24** | **59%** | **17** |

差距几乎全在 non-blocking。原因有两条，都在文档里有据可查：

1. 竞争类 bug 依赖 `-race` 在特定 Go 版本组合上暴露，而本机 `go build -race` 的产物启动即
   `0xC0000139`（race 运行时 DLL 缺失），只能用「可观测不变量」替代取证；
2. non-blocking 的触发窗口比 blocking 窄，3 次采样经常抽不到，需要几十到上百轮。

## 1.4 仓库里的 bug 点比 24 多

仓库累计 **35 个 bug 点**，其中 24 条落在论文这 41 条内，另外 **11 条在集合外**
（`defdb743c`、`1cc69980`、etcd#6873、etcd double-lock、k8s#62464、#20697、etcd#4997、
grpc#1546、k8s#9926、docker `0d9e543`、Moby#16309）。集合外的**不计入分子**——这是口径问题，
不是谦虚：论文的 41 条是一个特定子集，把集合外的工作算进覆盖率就是虚报。

---

# 二、与原论文的逐项对照

论文一共 19 项实验活动。下面按「对得上 / 有差距 / 与论文不一致 / 没做」四类分开讲，
每一类的判定标准写在标题里。

## 2.1 对得上的（11 项实验 / 9 张表，可直接交付）

| # | 论文实验 | 论文产出 | 我们的结果 | 偏差 / 判定 |
|---:|---|---|---|---|
| 1 | 六个应用的元信息 | Table 1 | 逐仓库回溯到 commit 数与论文相等的切点 | **6/6 完全相等，0 误差** |
| 2 | goroutine 创建点 | Table 2 | `goast` 走 AST（非正则）统计六个仓库 | Total 列**平均绝对偏差 4.5%** |
| 3 | 二维分类 | Table 5 | 用 artifact 标签重算 | 与原表一致 |
| 4 | 并发原语用量 | Table 4 | 同上工具统计 Mutex / chan | **Mutex 合计 +1.8%、chan −8.1%** |
| 5 | blocking 致因分布 | Table 6 | artifact 两张 one-hot 表交叉统计 | **6×6 逐格一致，0 处差异** |
| 6 | blocking 修复策略 + lift | Table 7 | 同上 | 逐格一致；lift Mutex×Moves **1.52**、Chan×Adds **1.42** 与论文同值 |
| 7 | non-blocking 致因分布 | Table 9 | 同上 | **6×6 逐格一致** |
| 8 | non-blocking 修复策略 + lift | Table 10 / 11 | 同上 | 逐格一致；anon.×Data Private **2.23**、chan×Moves **2.21** 同值 |
| 9 | 原语比例时间演化 | Fig 2 / Fig 3 | 6 应用 × 14 季度 | 逐点偏差 **0.5–3.3 pp** |
| 10 | gRPC-C 与 gRPC-Go 对照 | §3.1、Table 4 | v1.11/v1.12 源码实测 | C 侧 **746 精确命中**（论文 746），Go 侧 771（−1.9%） |

这 10 行覆盖论文 19 项里的 11 项（Table 10 与 11、Fig 2 与 3 各算两项），
共同点是**只依赖源码与 artifact 标注，不依赖运行时**，所以能做得比较干净。
其中 Table 6/7/9/10/11 五张表是逐格 0 差异——脚本内置了论文参考字典，任何一格对不上就以非零码退出，
不是人工比对出来的「差不多」。

## 2.2 有差距的（4 项：方向对，分母小）

| 论文实验 | 论文 | 本文 | 差距性质 |
|---|---|---|---|
| Table 8 · 内置死锁检测器 | 21 个 blocking 中检出 **2** | 已测 11 条、检出 **6**；但能同口径比较的 real-repo 只有 6 条、检出 **1** | **分母不可比**：6 条检出里 5 条来自最小复现体 |
| Table 12 · `-race` 检出率 | 20 个 non-blocking 中检出 **10** | 已测 6 条，检出 **3** | 分母 6 vs 20；且 3 条新案没跑 `-race` |
| Fig 4 · bug 生命周期 | 171 条，全 6 应用 | 63 条，3/6 应用 | 规模缩小，形状对得上 |
| Table 3 · 动态创建点 | 并发 1000 → 201,460 线程（比值 201.46） | 1000 并发 → 1019 goroutine，÷201.46 = **5.06**（C 线程池 5 线程） | **比值列复现**；存活时间列口径不可对齐 |

**Table 8 为什么不能报 6/11。** 论文的 2/21 是「真实程序跑起来，Go 运行时自己抓到了死锁」。
我们已测的 11 条里，5 条是 minimal——它们报死锁只证明复现体自己会锁死，不能证明 Go 抓到了真实 bug。
能跟论文放在一起比的只有 real-repo 那一行：**1/6**。剩下 6 条 blocking 干脆没测检测器
（11-21 新增的 4 条里，`VERDICT: DEADLOCK` 是驱动侧 3~5 秒外部超时判的，日志里没有
`all goroutines are asleep`），所以既不进分子也不进分母。

**grpc 五条为什么全不报。** 死锁是成立的（SIGQUIT 栈可证），不报的原因已实测确认：
`checkdead()` 要求全体 goroutine 睡死且 timers 为空、netpoll 无事件，而真实 server 永远有
IO / select 协程活着。这是**检测器的设计边界**，不是我们没复现出来。

## 2.3 与论文不一致的地方（3 处，如实记录）

这三处不是我们做错了，是**按论文自己的数据复算时对不上**。写进报告比藏起来更安全，因为评委照着
论文表格一算就能发现。

**一、Table 7 的正文表述与其表格不自洽。** 论文正文称「其余组合均低于 1.16」，但按同一公式，
Chan×Changes = **1.63**，高于它报的 1.42 与 1.52。只有把「样本数 > 10」同时作用到 fix 侧
（Chan×Changes 的 fix 样本只有 9）时，排序才回到 1.52 / 1.42。论文没说明过滤作用在哪一维，
我们把两种口径都给出。

**二、`chan × Channel` 的 2.7 无法用 Table 11 复算。** 我们得到 3.11（差 15%）。要凑出 2.7 需要
`n(Channel) = 22` 或 `N ≈ 75`，推测论文 `P(B)` 数的是「补丁中出现 channel 的次数」而不是
「用了 channel 的 bug 数」。这条不硬凑。

**三、Table 4 的 `atomic` / `Once` 两列整体镜像。** 论文的 `atomic` 列与我们统计的 `sync.Once`
在 6/6 仓库吻合（Docker 15↔14、K8s 48↔45、etcd 13↔11、CRDB 16↔13、gRPC 9↔9、BoltDB 1↔1），
而它的 `Once` 列是我们的 5~10 倍。排版错位已排除（表头与数据列的 x 坐标逐一对齐），
只能是原作者统计脚本的归类与常规理解不同。没有原作者脚本，我们标注为**不可比**，不猜规则。

## 2.4 没做的（2 项）与只做了一半的（1 项）

（论文第 6 项「复现 bug」不在这张清单里，它是本文第一节的主题：24/41。）


- **§7 自研匿名函数检测器** ❌：论文用一个自研检测器找「匿名函数相关」的并发 bug。这需要自己实现
  一个静态分析器，工作量独立于复现，且论文对该工具的规则描述不足以照着实现，**本轮不在范围**。
- **人工判读 3,211 条候选** ⬜：论文靠人读 commit 和补丁筛出 171 个真 bug。我们直接用 artifact 的
  标注（有声明），不重做人工判读——重做会引入主观偏差，也不可复现。
- **11 关键词过滤的漏斗** 🟡：只做到「数字接近」。全文口径重算 4,544 条候选，按补丁反推 3,105
  （论文 3,211，差 3.3%）；但论文从 3,211 到 171 的人工筛除过程没有复现，漏斗中段是空的。

---

# 三、复现形态：两栏，不能混

这是本仓库最重要的一条口径。同样是「复现成功」，证据强度差很多：

| 形态 | 含义 | 条数 | 哪些 |
|---|---|---:|---|
| **real-repo** | 上游函数本体原样执行，只写驱动 | **11** | `boltdb-392`、grpc 793/1293/1424/1459/1850、`etcd-4033`/`4474`/`6278`、`moby-8909`、`moby-256` |
| **minimal** | 按补丁还原调用序列，标准库重写成几十行 | **8** | `etcd-4679`/`5509`/`6937`、`moby-27782`、`moby-28682`、`kubernetes-30872`、`kubernetes-36377`、`cockroachdb-17112` |
| 未标注 | 早期案件，现有文档没写形态 | 5 | `boltdb-341`、`boltdb-7fb06fee`、`grpc-1667`、`grpc-1687`、`moby-17176` |

**minimal 能证明什么。** 证明「这段调用序列会自锁 / 会读到脏状态」，以及「打上补丁后不再发生」。
这对 Table 6/7 那类**机理分类**是足够的证据。

**minimal 不能证明什么。** 不能证明「上游程序真实运行时一定以同样方式失败」——真实环境里可能有
别的 goroutine 恰好化解、可能先在别处崩、可能被上层超时掩盖。所以它不能替 Table 8 记检出。

**`moby-27782` 是个特例。** 我们试过把它做成 real-repo，但复现出的挂起落在 `fsnotify` 的
`sync.Cond.Wait`，不在补丁改的那一行，跟修不修无关——**结论不成立**，所以退回 minimal，
不计入 real-repo。依据与命令在 [code/cases/real-repo-notes.md](code/cases/real-repo-notes.md)。

---

# 四、分类原则

| | blocking（论文 §5） | non-blocking（论文 §6） |
|---|---|---|
| 表现 | 进程卡住、不推进 | 进程总能跑完 |
| 典型信号 | `fatal error: all goroutines are asleep - deadlock!`、`go test` 超时 | 不加 `-race` 就静默；加了才有 `WARNING: DATA RACE`，或中途 panic |
| 判据 | buggy 必须卡死、fixed 必须干净通过 | buggy 必须报竞争/崩溃、fixed 必须干净 |
| 常见坑 | 超时不等于 bug——先排除环境导致的 Dial 卡死 | 单跑一次可能抽到「恰好没崩」，必须统计多次 |

按这个判据，仓库里 blocking 24 个 bug 点（22 个目录，其中 `etcd-6873-double-lock/`、
`kubernetes-62464-20697/` 各含两条）、non-blocking 11 个目录。逐条的负责人与症状见
[code/cases/README.md](code/cases/README.md)。

---

# 五、目录 / Layout

```
.
├── code/
│   ├── analysis/        P0–P2 分析脚本（挖提交、AST 静态统计、与论文比对、可行性筛选）
│   ├── harness/         复现驱动（p4_case.sh / p4_probe.sh / p4_deps.sh / 08_repro_boltdb.sh 等）
│   ├── tools/           goast：Go AST 统计工具
│   └── cases/
│       ├── blocking/        22 个目录 / 24 条（论文 §5）
│       ├── non-blocking/    11 个目录 / 11 条（论文 §6）
│       └── real-repo-notes.md   real-repo 两条的虚拟机环境与三个工具链坑
├── data/                跨 case 的数据：41 条目标、44 条可行性、bug 表、repo.lock.tsv、tables/
├── docs/                流程与口径
│   ├── PLACEMENT.md          放置规则
│   ├── MIGRATION.md          搬迁对照
│   ├── COMPLETION-STATUS.md  19 项实验逐项对照（本文件 §2 的来源）
│   ├── REPRODUCTION-TABLE.md 41 → 24 的逐条明细与缺口清单
│   ├── PRESENTATION-REQUIREMENTS.md  答辩要求拆解
│   └── BATCH-11-18.md / BATCH-11-21.md  两批补充复现的记录
├── report/
│   ├── appendix/        P0/P1/P2/P4/P6 六篇 + Table 3、Table 6–11、gRPC-C 对照
│   └── figures/         Fig 2 / Fig 3 / Fig 4（SVG + 论文原图对照）
└── results/
    ├── data/            repro_summary.csv（33 条复现记录的机器可读总表）
    ├── attempts-11-21/  三条 etcd 的负面结果（尝试过、没复现）
    ├── logs/            （空占位）单条 bug 的日志随 case 走
    └── shots/           （空占位）截图随 case 走
```

**一条 bug 一个自包含目录**是关键约定：说明、可运行代码、原始日志、截图都在
`code/cases/<类>/<bug>/` 里，能单独复跑，也不会出现「代码在 A、证据在 B」的断链。
代价是 `results/logs/` 与 `results/shots/` 不再集中存放，保留为占位。

---

# 六、怎么跑

环境分两套，取决于被测代码的年代：

| 被测对象 | 工具链 | 模式 |
|---|---|---|
| grpc-go（2018 前后） | Go 1.10.8，`GOROOT=/usr/local/go1.10.8` | `GO111MODULE=off`，GOPATH |
| boltdb（2015 前后，许汝轩那套） | Go 1.6.4 | GOPATH |
| moby 1.3 / k8s 1.6 真实源码 | Go 1.5.4 / 1.7.6，需 `CC=gcc-nopie` 包装 | GOPATH（`vendor/src` 布局） |
| 其余 minimal 复现体 | Go 1.8~1.26 均可（纯标准库） | module |

```bash
# grpc 官方测试类（793 / 1293 / 1424 / 1687）
cd code/cases/blocking/grpc-793 && bash run.sh

# 探针类（1459 / 1667 / 1850）
cd code/cases/blocking/grpc-1459 && bash run.sh 3 30
cd code/cases/blocking/grpc-1850 && bash run_loop.sh 50   # 这条按概率触发，3 次看不出来

# 吴德诚的工程
cd code/cases/blocking/boltdb-392 && bash scripts/run_experiments.sh

# boltdb 两条（李振炜那套）
bash code/harness/08_repro_boltdb.sh

# 11-21 补充的 7 条：每个目录自带 run.sh，目录名自动推断
cd code/cases/blocking/moby-8909        && RUNS=3 bash run.sh
cd code/cases/blocking/moby-256         && RUNS=3 bash run.sh
cd code/cases/blocking/moby-27782       && RUNS=3 bash run.sh
cd code/cases/blocking/kubernetes-30872 && RUNS=3 bash run.sh
cd code/cases/non-blocking/moby-28682   && RUNS=3 bash run.sh
cd code/cases/non-blocking/kubernetes-36377 && RUNS=3 bash run.sh
cd code/cases/non-blocking/cockroachdb-17112 && RUNS=3 bash run.sh

# real-repo 两条要连虚拟机（上游源码 + 老版本 Go）
bash code/cases/blocking/moby-8909/run_real.sh
bash code/cases/blocking/moby-256/run_real.sh
```

这 7 条的判定写在首行：`VERDICT: DEADLOCK`（卡住超过阈值，退出码 2）、`VERDICT: BUG`
（逻辑断言失败，退出码 3）、`VERDICT: OK`（退出码 0）。判定结果同时写进各案自己的
`results/verdict.txt`，`buggy 有失败 + fixed 0 失败` 才算 `REPRODUCED`。

`run.sh` 的仓库路径用 `P4_REPO` 覆盖，默认 `$HOME/gopath/src/google.golang.org/grpc`。
判定口径（`PASS`/`FAIL`/`TIMEOUT`/`NOTRUN`/`ERROR`/`DEADLINE`）以 `code/harness/README.md` 为准。

---

# 七、已知限制

- **41 条里还剩 17 条**：etcd 7、docker 3、grpc 3、kubernetes 2、cockroachdb 1、boltdb 1。
  其中 3 条（etcd#3593 / #8183 / #3060）是**试过没复现**，负面结果留在
  `results/attempts-11-21/`，按口径不计入分子。
- **Table 8 的 real-repo 分母只有 6**，Table 12 只有 6；两张表都不能拿 minimal 的结果去凑。
- **Table 3 存活时间列口径不可对齐**，只报了比值列（5.06 vs 5）。
- **Fig 2/3 里 CockroachDB 形状不符**（MAE 3.3 pp、r≈0），与 Table 4 里它 Total −18% 是同一件事，
  已如实标注，没有为了好看去调参。
- **两条 bug 有两人各自的证据**：`boltdb#341`、`grpc#1424`，两套日志并存、互为交叉验证。
- **部分 case 是机制级最小复现**，不是把 Docker / Kubernetes / etcd 整个跑起来；各 README 都写了
  缩比范围，不夸大。
- **阶段性总述未入库**：早期按学号分目录的几份 README 已并入各 case README 与本文件，
  不再单列，避免同一份数据出现两处口径。

## 协作约定 / Commit convention

课程按周检查每个人的实质性提交，**commit message 必须带学号 + 姓名**，否则该周的贡献无法认定。

One-time setup per clone (use the email bound to your own GitHub account, so the commit links
to your profile):

```bash
git config user.name  "<你的姓名拼音>"
git config user.email "<你 GitHub 账号绑定的邮箱>"
```

Branching: work on `main` is fine for this size of project. Rebase before pushing if the
remote has moved; do not force-push a commit that someone else has built on.
