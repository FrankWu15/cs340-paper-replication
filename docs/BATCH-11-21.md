# 11-21 批次

本批七件事：**① 论文 Figure 4（bug 生命周期 CDF）**；**② 补 3 条 etcd 的 41 条内复现**；**③ gRPC-C 线程创建点（Table 2 第七行）**；**④ Table 3 动态 goroutine 测量**；**⑤ Table 6/7/9/10/11 与两组 lift**；**⑥ gRPC-C vs gRPC-Go 原语对照（746 vs 786）**；**⑦ Figure 2 / Figure 3（原语比例随时间）**。

---

# 一、etcd 三条复现（新增）

## 结果

| 条目 | 类型 | 机理 | buggy | fixed | 证据 |
|---|---|---|---|---|---|
| `etcd#4033` | blocking | raftexample 在同一个 `select` 里既收提案又消费 `Ready()`，`Propose()` 自锁 | **HANG**（45s 超时，3 个 `serveChannels` 全卡住） | PASS 1.4s | [`case`](code/cases/etcd-4033/) |
| `etcd#4474` | blocking | 重启 replay WAL 时对尚未创建的 `rc.node` 调 `ApplyConfChange` | **CRASH**（SIGSEGV @ `raft.go:107`） | CLEAN（重启后正常选主并提交） | [`case`](code/cases/etcd-4474/) |
| `etcd#6278` | blocking | `NewElection("test")` 的 range 把既有 key `testa` 算进队列，等一个永不出现的 key | **DEADLOCK**（Campaign 5.00s 超时） | CLEAN（0.00s 当选） | [`case`](code/cases/etcd-6278/) |

三条都在 `repro_targets.csv` 的 41 条内，可直接计入分母。

## 口径变化

| 指标 | 之前 | 现在 |
|---|---:|---:|
| 41 条内已复现 | 14/41 (34%) | **17/41 (41%)** |
| blocking | 10/21 (48%) | **13/21 (62%)** |
| etcd | 3/13 | **6/13** |

`data/repro_summary_1121.csv` 是本批 3 行，字段与 `repro_summary_1118.csv` 一致，合并后即 28 行。

## 三条各自的方法差异（不可混算）

| 条目 | kind | 判据 | 备注 |
|---|---|---|---|
| #4033 | real-repo + 移植补丁自带测试 | 45s 无进展 + 栈落在 `serveChannels` | 测试文件 buggy 版本不存在，从 fix 取 |
| #4474 | real-repo + 原程序跑两遍 | 重启后进程是否存活 + 新提案能否被 GET 到 | PUT 是乐观返回，**不能只看 PUT 状态码** |
| #6278 | real-repo + 20 行驱动器 | `Campaign` 是否在 5s 内返回 | integration 框架在本环境不可用，改用真实 server 二进制 |

## 尝试过但没成的三条（负面结果，一并留档）

`results/data/attempts_1121.csv`，原始日志在 `results/logs/`。

| 条目 | 跑法 | 结果 | 原因 |
|---|---|---|---|
| `etcd#3593` | `-race TestWriteReadTimeoutListener` | 两侧 PASS，0 race | race 在 `time.AfterFunc(50ms)` 回调里调 `t.Fatal`，测试本身 30ms 就结束，timer 从不触发 |
| `etcd#8183` | `-race TestRevision ./compactor` | 两侧 PASS，0 race | `fakeRevGetter.rev` 只在 compactor 单 goroutine 路径被读写，打不出并发 |
| `etcd#3060` | `-race -count=100 TestStopRaftWhenWaitingForApplyDone` | 两侧 PASS×100，0 race | `r.stopped` 在 `go r.run()` 之后才创建的窗口极窄，100 轮未命中 |

这三条的共同点：**补丁修的是测试/初始化代码自身的脆弱竞态**，`-race` 只在特定时序才报。论文把它们标成 Reproduced，但复现依赖当时的机器与调度，本环境跑不出来。这个结论对 Table 12 有直接意义 —— 检出率高度依赖重复次数与负载，不是"跑一次就该报"。

另有一次方法失败：`etcd#6278` 用 fix 自带的 `integration` 测试时，**buggy 与 fixed 两侧都卡在 `member.Launch` 300s**，说明是 2016 版测试集群框架与 Ubuntu 18.04 + go1.10.8 不兼容，不是 bug 判据。改用真实 server 二进制后 8 秒出结果。

## 环境与依赖坑（下次直接照做）

1. **2015 版 etcd**（#4033/#4474/#3060/#3593）：依赖已提交在仓库内，`GOPATH=<repo>/Godeps/_workspace:<原 GOPATH>` 即可编译，不需要联网。
2. **2016/2017 版 etcd**（#6278/#8183）：按 `glide.lock` 逐条 `clone + checkout`。`golang.org/x/*` 已无法直连，改 `https://github.com/golang/<sub>`；`google.golang.org/grpc` 改 `github.com/grpc/grpc-go`。
3. `bitbucket.org/ww/goautoneg` 已下线（clone 会要认证），从 etcd 后续 vendor 快照取同源 162 行文件（BSD 许可头完整保留）。
4. `integration` 包在本环境起不来；要用真实 server 时，`go build -o etcd .` 后直接 `--listen-client-urls` 起单机即可（1s 内 ready）。
5. **`-race` 不能用来判 blocking**：#4033 的测试自身在 `raftexample_test.go:86/101` 有变量竞争，两侧都会报，只能靠超时+栈判。
6. `git checkout` 会被上一侧留下的 untracked 测试文件挡住，切版本前先 `rm -f`。

---

# 二、gRPC-C 线程创建点（Table 2 第七行）

论文 §3.1：gRPC-C 140K 行、只有 **5 个线程创建点、0.03/KLOC**。

| 口径 | 数量 | 说明 |
|---|---:|---|
| 物理线程创建 API | 4 | pthread_create、CreateThread、2 处 std::thread |
| **Linux 核心路径** | **5** | 上面去掉 Windows，加 timer_manager 与 executor |
| 全部 `gpr_thd_new` 调用点 | 6 处文件 | 再加 poller、profiling、executor 扩容 |

| 项 | 论文 | 本文 |
|---|---:|---:|
| 创建点 | 5 | **5**（口径 B） |
| 代码行 | 140K | 147.1K（`src/` + `include/`） |
| 每 KLOC | 0.03 | **0.034** |

源码：gRPC v1.10.0（2018-03-01，`474c595`），经 gitee 镜像取得（GitHub 直连被代理拦截）。详见 [`case`](code/cases/grpc-c-creation/)。

---

# 三、Table 3 动态 goroutine 测量

gRPC-Go `f6692351`（2018-05-21）官方 benchmark，交叉编译 linux/amd64，VM 上跑。

| 负载 | 并发 | 侧 | goroutine | 论文比值 | 反推 C 线程 |
|---|---|---:|---:|---:|---:|
| sync_ping_pong | 1 | client | 18 | 7.33 | 2.46 |
| sync_ping_pong | 1 | server | 10 | 4.00 | 2.50 |
| qps_unconstrained | 200 | client | 216 | 201.46 | 1.07 |
| **qps_unconstrained** | **1000** | **client** | **1019** | **201.46** | **5.06** |
| qps_unconstrained | 1000 | server | 14 | 6.36 | 2.20 |

**比值列复现**：1000 并发 → 1019 goroutine，÷201.46 = 5.06 ≈ gRPC-C 线程池 5 线程，自洽。

**存活时间列不可复现**：实测平均 9.17%（client）/ 6.12%（server），论文 63.65% / 76.97%。原因是本地回环 3,940 RPS，短命 goroutine 占绝大多数，309 ms 采样只能看见 1%。详见 [`case`](code/cases/table3-dynamic/) 与 [`报告`](report/table3_dynamic.md)。

gRPC-C 未运行：镜像 `third_party` 子模块全空，装不上，C 侧数值引用论文。

---

# 四、Figure 4（bug 生命周期 CDF）

| 指标 | 论文 | 本文 |
|---|---:|---:|
| shared memory 中位数 | ≈74 天 | **59.9 天** |
| message passing 中位数 | ≈96 天 | **106.5 天** |
| 300 天时已修比例（SM / MP） | 0.898 / 0.861 | 0.758 / 0.800 |

判定 **partially supported**：长尾结论成立、两类交叉位置一致，但 CDF 在 100 天之后系统性低 4~15 个百分点。

覆盖 **63 / 171 条，3 / 6 个应用**。docker（44）、kubernetes（34）、cockroachdb（28）是 `filter=tree:0` 按需克隆，本地无文件内容，blame 需联网抓 blob 而当前代理 502。补齐需在能直连 GitHub 的机器上重克隆这三个仓库（去掉 `--filter`），脚本不用改。

---

# 五、Table 6/7/9/10/11 与两组 lift

论文明细章的五个交叉表 + 两组相关系数，此前一直标 🟡（「数据齐、未出表」）。本批把统计脚本补上。

- 脚本：[`code/analysis/05_stats_figures.py`](code/analysis/05_stats_figures.py)
- 报告：[`report/tables_6_11.md`](report/tables_6_11.md)
- 数据：`results/tables/*.csv`（五张表 + 三个 lift 矩阵）

## 结果：五张表逐格一致

数据源是 artifact 的两张 one-hot 标注表（blocking 85 行、non-blocking 86 行），脚本把列名映射成论文用词后直接交叉统计，**一格不差**：

| 表 | 内容 | 规模 | 比对 |
|---|---|---|---|
| Table 6 | blocking 根因 × 应用 | 6 × 6 + 合计 | 0 差异 |
| Table 7 | blocking 修复策略 × 根因 | 6 × 5 + 合计 | 0 差异 |
| Table 9 | non-blocking 根因 × 应用 | 6 × 6 + 合计 | 0 差异 |
| Table 10 | non-blocking 修复策略 × 根因 | 6 × 5 + 合计 | 0 差异 |
| Table 11 | non-blocking 补丁原语 × 根因 | 6 × 7 + 合计 | 0 差异 |

脚本带自检：任何一格与 `PAPER` 字典对不上就以非零码退出，所以这张表可以被反复验证。

## 两处归类例外（写进代码注释）

Table 6 要求每条 bug 恰好归入一个根因，但标注表有两行不满足，处理方式由论文的表格数字反推：

1. `moby#25384` 六个根因列全空，只有 `WaitGroup`/`waitgroup` 为 1 → 论文 Docker 行 `Wait=3`，按 WaitGroup 记 Wait；
2. `kubernetes#11298` 同时打了 `wait related` 与 `mixing lock/wait & channel` → 论文 Kubernetes 行 `Wait=0`、`Chan w/=6`，说明 mixing 优先。

两条都只改归类，不改原始标注。

## lift 的三处对话

| 项 | 论文 | 本文 | 判定 |
|---|---|---|---|
| Mutex × Moves | 1.52（最强） | **1.52** | ✅ |
| Chan × Adds | 1.42（第二） | **1.42** | ✅ |
| anon. × Data Private | 2.23 | **2.23** | ✅ |
| misusing chan × Moves | 2.21 | **2.21** | ✅ |
| misusing chan × Channel | 2.7（最强） | **3.11** | ⚠ 差 15% |

另外发现论文一句表述与它自己的 Table 7 不自洽：正文说「其余均低于 1.16」，但 Chan×Changes 按同一公式是 **1.63**，比它报的次高值 1.42 和最高值 1.52 都高。只有当「样本数 > 10」这条过滤同时作用在 fix 侧时（此时 Chan×Changes 的 fix 样本 9 被排除），排序才回到 1.52 / 1.42。论文没写清过滤作用在哪一维，本报告两种口径都列出，不替它选。

`misusing chan × Channel` 的 3.11 要凑成 2.7，需要 `n(Channel)=22`（而非 Table 11 的 19）或 `N≈75`，推测论文在 `P(B)` 里数的是「补丁中出现 channel 的次数」而不是「用了 channel 的 bug 数」。这条没有硬凑。

---

# 六、gRPC-C 原语对照（746 vs 786）

报告 `report/grpc_c_vs_go.md`，脚本 `code/cases/grpc-c-primitives/`。

论文那句 "gRPC-C only uses lock, and it is used in 746 places (5.3 per KLOC)" 没写口径。
按「`src/core/` + `include/`，`gpr_mu_lock/unlock/trylock` 调用点」这一条数：

| 版本 | 锁使用点 | 每 KLOC（原始行） |
|---|---:|---:|
| v1.10.0 | 726 | 6.15 |
| v1.11.0 / v1.12.0 | **746** | 5.55 / 5.51 |
| v1.20.0 | 663 | 3.86 |

**746 精确命中，且 v1.11 与 v1.12 逐点相同**（329 + 411 + 6）。Go 侧 771（论文 786，−1.9%），
原语 8 类。三处与论文不符：密度的两个分母口径不同（Go 含测试的代码行、C 原始行）、
"only uses lock" 忽略了 80 处条件变量、论文没写版本（v1.20 只有 663）。

---

# 七、Figure 2 / Figure 3（原语比例随时间）

报告 `report/fig23_evolution.md`，图 `report/figures/fig2_shared_memory.svg`、`fig3_message_passing.svg`。

6 个应用 × 14 个季度（2015-02 … 2018-05，正好是论文横轴刻度），每个点取该日期前最后
一次提交，用同一份 goast 数原语比例。论文曲线用 `extract_fig23.py` 从 PDF 矢量反解，
标定残差 0.00 px。

| 应用 | 共享内存均值 | 首末漂移 | 与论文逐点平均偏差 |
|---|---:|---:|---:|
| Docker | 71.3% | −3.4 pp | 0.5 pp |
| Kubernetes | 75.1% | +4.7 pp | 1.4 pp |
| etcd | 62.2% | **−12.9 pp** | 1.5 pp |
| CockroachDB | 74.8%（13 点） | −5.7 pp | 3.3 pp |
| gRPC-Go | 75.7% | +1.3 pp | 1.5 pp |
| BoltDB | 73.6% | −4.8 pp | 论文曲线被覆盖 |

**水平对得上（0.5–3.3 pp），"stable over time" 只对四个应用成立**：etcd 三年掉了 12.9 个
百分点（channel 用得越来越多），CockroachDB 形状不符（r≈0），与 Table 4 里它 Total −18% 同源。

---

## 文件与落点

`code/`、`data/`、`results/`、`report/` 直接覆盖到仓库根目录即可。

```
11-21/
├── code/cases/{etcd-4033,etcd-4474,etcd-6278}/   # 三个 case，各自 README + run.sh + logs
├── code/cases/grpc-c-creation/                    # Table 2 第七行，统计脚本 + 原始输出
├── code/cases/table3-dynamic/                     # Table 3，采样脚本 + 200 份 goroutine 栈
├── code/cases/grpc-c-primitives/                  # 746 vs 786，C 侧计数 + 两侧对照
├── code/analysis/06_evolution.py                  # Fig 2/3 采样（含 Godeps 排除与 cat-file 兜底）
├── code/analysis/{extract_fig23,07_fig23}.py      # 论文曲线反解 + 出图
├── code/_attempts/                                # 失败尝试的脚本，留档不删
├── code/analysis/04_lifecycle.py                  # Fig 4，补齐 03→06 的编号空缺
├── code/analysis/05_stats_figures.py              # Table 6/7/9/10/11 + lift，带逐格自检
├── code/{build_bench,run_table3_life,parse_life}.*# benchmark 编译与生命周期解析
├── data/repro_summary_1121.csv                    # 本批 3 行
├── data/{bug_lifetime,lifecycle_cdf}.csv          # Fig 4 数据
├── data/{table3_dynamic,grpc_c_creation_sites}.csv# Table 3 / gRPC-C 数据
├── data/evolution_primitive_usage.csv             # Fig 2/3，6 应用 × 14 季度
├── data/{fig2,fig3}_paper_raw.csv                 # 论文曲线反解原始点
├── data/fig23_compare.csv                         # 逐点对照 + 偏差
├── results/data/attempts_1121.csv                 # 3 条负面结果
├── results/tables/                                # 五张表 + 三个 lift 矩阵的 CSV
├── results/logs/                                  # 负面结果与 integration 原始日志
├── report/table3_dynamic.md                       # Table 3 复现报告
├── report/tables_6_11.md                          # Table 6/7/9/10/11 复现报告
├── report/grpc_c_vs_go.md                         # 原语对照报告
├── report/fig23_evolution.md                      # Fig 2/3 复现报告
└── report/{appendix/p6_lifecycle.md, figures/…}   # Fig 4 附录与图
```
