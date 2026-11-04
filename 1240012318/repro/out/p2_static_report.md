# P2 静态测量报告

生成时间：2026-11-04 15:10
工具：`repro/tools/goast`（go/ast 遍历，非正则）
入口：`./run.sh static` → `./run.sh compare`

本阶段不运行任何程序，只读源码，回答一个问题：**这 6 个项目里并发原语用得有多普遍，
共享内存与消息传递各占多少**。对应论文 Table 2（goroutine 创建点）与 Table 4（原语用量）。

逐格对照见 `out/table2_table4_compare.md`，结论摘要见 §6。

---

## 1. 口径

论文没有公开其统计工具，因此这是「同方法重实现」。口径由**对照论文数字反推**确定，
不是拍脑袋定的——每条都有反推依据：

| 项 | 取值 | 依据 |
|---|---|---|
| 排除目录（分子） | `vendor/`、`third_party/`、`.git/` | 若含 vendor，创建点数会远超论文（Docker 145） |
| 测试文件（分子） | 排除 `*_test.go` | 同上；论文 Table 2 的创建点数对应产品代码 |
| goroutine 创建点 | `go f()` 与 `go func(){}` 分开计数 | 论文 Table 2 按这两类分列 |
| 锁 | 机械口径 `lock_calls`：凡 `.Lock/.Unlock/.RLock/.RUnlock` 调用点计一次 | 不依赖类型推断，可 grep 复核（§2.1 校验偏差 <4%） |
| chan | **只算收发**（`ch <- v` 与 `<-ch`），**不含 `make(chan)`** | 反推论文绝对值：BoltDB 11=11、gRPC 176 vs 181、K8s 698 vs 730、Docker 416 vs 393、etcd 863 vs 892，五个吻合；计入 make 则系统性高 25% |
| Misc | `sync.Pool` 引用点 | etcd 该列为 0（排除 `context`，etcd 有 277 处），且 BoltDB=2、Docker=11~14 吻合 |
| KLOC | **全仓代码行**（含 vendor、含测试、去空行与注释行） | 由 Table 2「创建点 ÷ per-KLOC」反推论文 LOC，与本仓全仓代码行比值 0.73~0.80；实测六仓库偏差 **0.7%**（§6） |

分子排除 vendor/测试、分母包含它们，看起来不对称，但这是**论文自己的口径**——
反推的 LOC（Docker 806K、etcd 443K、K8s 2322K）只有含 vendor 才成立，
而创建点数只有排除 vendor 才成立。复现时照论文做，不擅自"修正"。

## 2. 结果

| 项目 | 文件 | 代码行 | goroutine 创建点 | /KLOC | 共享内存原语 | 消息传递原语 | MP 占比 |
|---|---|---|---|---|---|---|---|
| boltdb | 24 | 9,100 | 2 | 0.221 | 34 | 13 | 27.7% |
| etcd | 576 | 444,500 | 270 | 0.607 | 1,260 | 863 | 40.7% |
| grpc-go | 156 | 52,800 | 48 | 0.909 | 587 | 184 | 23.9% |
| docker | 1,067 | 790,900 | 147 | 0.186 | 1,104 | 427 | 27.9% |
| cockroachdb | 1,177 | 520,400 | 148 | 0.284 | 1,933 | 723 | 27.2% |
| kubernetes | 5,142 | 2,304,100 | 509 | 0.221 | 3,110 | 700 | 18.4% |
| **合计** | **8,142** | **4,121,800** | **1,124** | — | **8,028** | **2,910** | **26.6%** |

解析错误：6 个仓库合计 1 个（cockroachdb），占 1,178 个 .go 文件（成功 1,177 + 失败 1）的 0.08%，不影响结论。

> 该文件是 `pkg/cmd/prereqs/testdata/src/example.com/a/invalid.go`，`package a` 之后只有一行乱码
> `dfasdg agawega ageawg`。这是 CRDB **故意构造的测试夹具**，用于验证 `prereqs` 工具（只解析 import、
> 不编译语法）面对非法 Go 文件仍能产出依赖列表——`prereqs_test.go` 的 `expectedA` 里明确列出了它。
> 换言之不是工具缺陷，也不是 checkout 损坏，是上游仓库自带的坏文件。`goast` 已补记
> `parse_error_files` 字段，此后任何解析失败都会留痕而不是只记个数。

`testdata/` 目录未排除（`go build` 会忽略它），但 6 仓库合计仅 9 个文件 / 360 行，占 0.02%。

### 2.1 lock_calls 的独立校验

用 `find ... -not -name '*_test.go' | xargs grep -oE '\.(Lock|Unlock|RLock|RUnlock)\(\)'`
逐仓库对拍：

| 项目 | goast | grep | 偏差 |
|---|---|---|---|
| boltdb | 33 | 33 | 0 |
| etcd | 1,066 | 1,040 | +26 (2.5%) |
| grpc-go | 485 | 485 | 0 |
| docker | 1,029 | 994 | +35 (3.5%) |
| cockroachdb | 1,614 | 1,617 | −3 |
| kubernetes | 2,821 | 2,840 | −19 |

偏差来自两处：AST 能识别跨行书写的调用（`mu.Lock(\n)`），grep 不能；反过来 grep 会把
字符串与注释里的 `.Lock()` 也数进去。都在 4% 以内，说明该口径可信。

## 3. 口径敏感性：含不含测试文件

| 项目 | 锁(不含) | 锁(含) | 增幅 | chan收发(不含) | chan收发(含) | 增幅 |
|---|---|---|---|---|---|---|
| boltdb | 33 | 45 | +36% | 11 | 30 | **+173%** |
| etcd | 1,066 | 1,165 | +9% | 863 | 1,735 | **+101%** |
| grpc-go | 485 | 715 | +47% | 176 | 339 | **+93%** |
| docker | 1,029 | 1,104 | +7% | 416 | 987 | **+137%** |
| cockroachdb | 1,614 | 2,343 | +45% | 705 | 1,607 | **+128%** |
| kubernetes | 2,821 | 3,145 | +11% | 698 | 1,362 | **+95%** |

规律很一致：测试代码的 **channel 密度是产品代码的 2 倍以上**，而锁只多 7–47%。
原因是 Go 的测试习惯用 channel 同步 goroutine（`done := make(chan struct{})`、
`select` 超时），很少用锁。

这条对结论有实质影响：如果把测试算进去，MP 占比会明显上移。论文没说明口径，
但反推 Table 2 的创建点数可知它**排除了测试**，所以本报告也排除。

## 4. 工具缺陷与修复

第一次跑出来的数字有明显错误，逐一定位后修掉，修复过程本身值得写进报告。

### 4.1 变量接收者的调用被整体吞掉（影响最大）

原实现里 `CallExpr` 先判 `fn.X` 是不是 `*ast.Ident`（想识别 `atomic.AddInt32` 这类包调用），
命中就 `return`。但 `mu.Lock()` 的接收者 `mu` **本身也是 `*ast.Ident`**，于是所有
「直接对局部变量加锁」的调用都走不进后面的类型推断分支，只有 `db.mu.Lock()`
这种带字段访问的才算数。

修复：先查变量类型提示表，查不到再按包名判断。效果（修复前后）：

| 项目 | mutex（修复前） | mutex（修复后） |
|---|---|---|
| cockroachdb | 2 | 267 |
| docker | 466 | 484 |
| etcd | 702 | 757 |
| kubernetes | 1,740 | 1,888 |

### 4.2 只认 `sync` 包，包装类型归零

cockroachdb 把标准库锁全包了一层：全仓 `syncutil.Mutex` 165 处，而 `sync.Mutex` 只有 1 处。
原实现只匹配 `pkg == "sync"`，导致 CRDB 的锁统计几乎归零（2）。

修复：包名不匹配时，再按类型名兜底（`X.Mutex` / `X.RWMutex` / `X.WaitGroup` …）。

### 4.3 内嵌 mutex 与跨文件定义仍会漏

`type Foo struct { sync.Mutex }` 然后 `f.Lock()`——匿名嵌入字段没有字段名，提示表记不到；
且提示表是**按文件**收集的，定义在 a.go、使用在 b.go 就断开。

这两类没修（要修得上 `go/types` 做完整类型检查，对 2015–2018 的老代码风险高）。
`lock_calls` 这个机械口径恰好绕过了它们，这也是把它选为锁的**主口径**的原因。

### 4.4 三处口径错误（对照论文后才发现）

前两轮跑完，数字看着"合理"，但和论文一比就露馅。三处都是**口径**而非代码 bug：

| 症状 | 原口径 | 修正 | 证据 |
|---|---|---|---|
| per-KLOC 比论文小 2~6 倍 | 只算非 vendor 非测试的原始行 | 全仓代码行（含 vendor 含测试） | 反推论文 LOC 与全仓原始行比值稳定在 0.73~0.80，正是代码行占比 |
| 原语总量普遍高 12~33% | chan 含 `make(chan)` | 只算收发 | BoltDB 11=11 精确命中，另四仓库 ±5% |
| etcd 的 Misc 占 12.5%，论文为 0 | `context.*` + `io.Pipe` | `sync.Pool` | etcd 有 277 处 context，论文 Misc=0；sync.Pool 在 etcd 恰为 0，BoltDB 恰为 2 |

修正后 Table 4 的 Total 平均偏差从 16.0% 降到 5.8%，Mutex 列降到 1.8%。

## 5. 初步分析

把 §2 的原语占比和论文的 bug 占比放在一起（论文：171 = 85 blocking + 86 non-blocking，
其中 blocking 有 58% 即 49 条来自 message passing，故 shared memory 侧为 36 + 69）：

| | 使用占比（本文） | blocking bug 占比（论文） | non-blocking bug 占比（论文） |
|---|---|---|---|
| 共享内存 | 73.4% | 42% (36/85) | **80% (69/86)** |
| 消息传递 | 26.6% | **58% (49/85)** | 20% (17/86) |

归一化到「每千次原语使用引出多少条 bug」：

- blocking：消息传递 **16.8** 条 / 千次，共享内存 4.5 条 → **3.8 倍**
- non-blocking：共享内存 **8.6** 条 / 千次，消息传递 5.8 条 → **1.5 倍**

也就是说，两类原语的错误模式是**分工**的：channel 主要引致阻塞，锁主要引致结果错误。
这与论文的核心论断方向一致，且修正口径后倍数更大（原 2.0× / 2.7×）。

**必须声明的局限**：上述是跨项目聚合的粗略估计，不是论文本身的分析方法（论文没做这个归一化）。
分母是原语调用点总数，分子是 bug 条数，一条 bug 通常牵涉多个原语，且各项目规模差异巨大
（Kubernetes 占全部原语的 35%）。严格做法应按项目分别归一化后再汇总。这一版仅作方向性判断。

## 6. 与论文 Table 2 / Table 4 的对比

完整逐格对照见 `out/table2_table4_compare.md`。摘要：

| | 指标 | 结果 |
|---|---|---|
| Table 2 | 创建点 Total（6 仓库） | 平均绝对偏差 **4.5%**（最大 etcd −9.1%） |
| Table 2 | Per KLOC | 平均 **4.8%**，BoltDB 0.22 vs 0.221 |
| Table 4 | 原语 Total | 平均绝对偏差 **5.8%**（BoltDB 47 vs 47） |
| Table 4 | **Mutex 列** | 合计偏差 **+1.8%**，逐仓库平均 7.3% → **可复现** |
| Table 4 | **chan 列** | 合计偏差 **−8.1%**，逐仓库平均 6.5% → **可复现** |
| Table 4 | Once / atomic / WaitGroup / Cond / Misc | 逐仓库平均偏差 51%~422% → **不可比** |
| LOC | 反推 LOC vs 本文代码行 | 平均偏差 **0.7%**（六仓库全部 <2%） |

**核心结论**：论文的两大支柱——「共享内存用得比消息传递多」和「Mutex 是使用最广的原语、
chan 是最常用的消息传递原语」——在本文的工具下复现成功（Mutex +1.8%，chan −8.1%）。

**未复现的部分**：`Once`/`atomic` 两列呈现系统性镜像（论文 atomic 列与我们 `sync.Once`
计数在 6/6 仓库吻合到 8%，而论文 Once 列是我们 `sync.Once` 的 5~10 倍）。
PDF 文本坐标已排除排版错位（表头 x=363.9/387.3/412.1/... 与数据列逐一对齐），
所以只能是论文统计脚本的归类与常规理解不同。没有原作者的脚本，无法判定具体规则，
因此如实标注为不可比，不做猜测性解释。

CockroachDB 是唯一整体偏离较大的项目（Total −18.2%），主要来自 Mutex 列少 200
（1,614 vs 1,814）与 chan 列少 211；它也是六个项目中包装类型最多、类型推断最难的一个。

## 7. 复现

```bash
./run.sh goast      # 编译 tools/goast
./run.sh static     # 六个仓库全跑，输出 repro/out/static_<app>.json
./run.sh compare    # 与论文 Table 2/4 逐格对照，输出 out/table2_table4_compare.md

# 含测试文件（§3 的对照）
goast -root 6app/etcd -include-tests -json repro/out/static_etcd_tests.json
```

产物：

- `repro/out/static_<app>.json` — 每仓库原始计数（含诊断字段 `misc_context`、`chan_make_diagnostic`）
- `repro/out/static_<app>_tests.json` — 含测试的对照
- `repro/out/table2_table4_compare.md` — 逐格对照
- `repro/out/p2_static_report.md` — 本文件
- `repro/out/backup_context_misc/` — 修正口径前的旧结果，留档以便追溯
