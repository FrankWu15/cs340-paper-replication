# 并发缺陷复现报告：BoltDB 与 gRPC-Go

**复现对象**：《Understanding Real-World Concurrency Bugs in Go》(ASPLOS'19) 公开数据集
`system-pclub/go-concurrency-bugs` 中的并发缺陷

**报告范围**：BoltDB 的 2 个缺陷、gRPC-Go 的 2 个缺陷，共 4 个案例。
其中 BoltDB 案例 01（读事务引用共享 meta 页指针，修复提交 `7fb06fee`）由小组另一成员
完成并单独提交，本报告不再包含。

---

## 1. 概述

本实验从上述数据集中选取 BoltDB 与 gRPC-Go 两个项目的四个并发缺陷，采用**缺陷版本与修复版本同程序对照**的方法进行复现：同一份触发程序（或同一回归测试）分别在缺陷提交（buggy）与修复提交（fixed）上编译运行，要求前者出现可观测故障、后者正常结束。

该方法的作用在于建立因果关系：单独观测到一次崩溃或死锁，不足以说明该现象由目标缺陷引起；只有在同一程序、同一构建条件下，版本差异构成唯一变量时，故障的出现与消失才能归因于该修复提交。

**复现结论**：四个缺陷均获得对照结果成立。其中与提交说明（或论文描述）存在偏差的三处已在第 6 节如实说明。

---

## 2. 复现结果

| 编号 | 应用 | 缺陷 | 类型 | 缺陷版本表现 | 修复版本表现 | 结论 |
|---|---|---|---|---|---|---|
| 1 | BoltDB | `Close()` 未等待进行中的写事务 | non-blocking | 关闭耗时 35.92 µs 即返回，随后提交触发空指针崩溃 | 关闭阻塞 55.24 ms 至事务结束，提交成功 | 与预期一致 |
| 2 | BoltDB | 事务入口错误分支漏解锁 | blocking | `all goroutines are asleep - deadlock!` | 85 ns 返回 `ErrDatabaseNotOpen` | 故障可复现，触发路径与提交说明不同 |
| 3 | gRPC-Go | `DialContext` 内部协程泄漏，`doneChan` 永不关闭 | blocking（协程泄漏） | 回归测试 FAIL（100 ms 内 `doneChan` 未关闭） | 回归测试 PASS | 契约层面与预期一致，边界见第 6 节 |
| 4 | gRPC-Go | 并发 `WriteStatus` 越过状态检查，向已关闭通道发送 | non-blocking | 同一测试重复 200 次，3/3 出现 `panic: send on closed channel` | 同条件下 3/3 通过 | 与预期一致，判定依赖重复执行 |

四个案例的共同特征：均无需专用检测工具即可定位。Go 运行时的死锁检测、panic 栈与测试断言已足以暴露问题，此结论与论文第 7 节一致。

---

## 3. 实验环境

### 3.1 BoltDB 部分

| 项目 | 配置 |
|---|---|
| 操作系统 | WSL2 / Ubuntu 22.04.5 LTS |
| Go 版本 | go1.6.4 linux/amd64 |
| 构建方式 | GOPATH 模式 |
| 硬件 | 12 核 / 11.7 GB |

选择 go1.6.4 的依据：两个缺陷分别位于 2014-06、2015-05 两个代码快照，项目早于 Go modules 引入。go1.6（2016-02 发布）是能同时编译上述快照、且在 Linux 平台 `-race` 检测器稳定可用的最低版本。

### 3.2 gRPC-Go 部分

| 项目 | 配置 |
|---|---|
| 操作系统 | WSL2 / Ubuntu 22.04.5 LTS |
| Go 版本 | go1.22.9 linux/amd64 |
| 构建方式 | module 模式（临时生成 go.mod） |
| 依赖固定 | protobuf `1909bc2f`、x/net `1c05540f`、genproto `09f6ed29`、x/text `3bd178b8`（2017-08 时间点） |

gRPC-Go 快照同样早于 go.mod 机制，但未沿用 GOPATH 模式，原因有三：该快照依赖 4 个外部仓库，GOPATH 模式下需手工摆放并保证版本互相兼容，出错面更大；最新的 `golang.org/x/net` 已将最低 Go 版本要求提升至 1.26，必须精确指定历史版本，module 模式对此更直接；修复提交自带的回归测试无外部测试框架依赖，module 模式不会引入额外变量。

此差异属于构建手段不同，不影响前后对照的有效性：缺陷版与修复版使用完全相同的 `go.mod` / `go.sum` / Go 版本，唯一变量是修复提交涉及的那几行代码（案例 3 见 `blocking/grpc-1424/notes/source-diff.txt`，案例 4 见 `non-blocking/grpc-1546/patches/1546.patch`）。

---

## 4. 复现方法

每个缺陷按统一流程处理：

```
① 从数据集提取修复提交哈希
        ↓
② 经 GitHub API 查询 parents[0].sha，得到缺陷提交
        ↓
③ 两份快照分别建立独立工作区（BoltDB 为 GOPATH 布局，gRPC-Go 为独立 module 目录）
        ↓
④ 依据补丁内容推定触发条件，编写触发程序或取修复提交自带的回归测试
        ↓
⑤ 同一程序分别在两版本上运行，记录输出
```

第 ④ 步是流程的核心。触发条件不由试错得出，而由补丁的改动内容反推：补丁在某一错误分支中补充了释放操作，即说明缺陷存在于该分支的资源管理；补丁以 `defer` 补充通道关闭，即说明缺陷源于该通道在异常路径上无人关闭；补丁把状态置位移进临界区，即说明检查与置位之间存在窗口。

判定标准：缺陷版本须出现可观测故障（崩溃、死锁或断言失败之一），修复版本须正常完成。对竞争窗口极窄的缺陷，两侧采用相同的重复次数，以命中次数而非单次结果作判据。

---

## 5. 缺陷分析与复现过程

### 案例 1 · BoltDB `Close()` 未等待进行中的写事务

**缺陷机理。** 缺陷版 `Close()` 仅获取 `metalock`（保护 meta 页）便执行清理：将 `opened` 置为 `false`、清空 `freelist`、解除内存映射并关闭文件。此时仍在执行的写事务于提交阶段访问已被清理的内部状态。修复方式为 `Close()` 额外获取 `rwlock` 与 `mmaplock.RLock`，与写事务互斥。

**触发条件。** 写事务提交前，另一 goroutine 调用 `Close()`。

**实验结果。** 本案例以时序数据作为主要判据，其区分度高于崩溃栈：

```
缺陷版本：Close 于写事务提交前返回，耗时 35.92µs
          panic: invalid memory address or nil pointer dereference
          bolt.(*Tx).Commit(...)  tx.go:151

修复版本：Close 阻塞等待写事务结束
          提交成功，Close 总耗时 55.242242ms
```

关闭耗时由 35 µs 增至 55 ms，增加部分即等待写事务完成的时间，直接表明互斥已生效。

**实现说明。** 初次实验假定 `Close()` 等待全部事务，导致修复版本同样崩溃。查阅源码后确认其仅等待写事务，读事务不参与互斥，据此调整触发程序后方获得对照结果。

### 案例 2 · BoltDB 事务入口错误分支漏解锁

**缺陷机理。** `Close()` 执行后 `db.opened` 为 `false`。事务入口 `beginTx()` 检测到该状态后进入错误分支，返回前仅执行 `mmaplock.RUnlock()`，遗漏 `metalock.Unlock()`。该锁因此被永久占用，后续任何事务操作均在 `metalock.Lock()` 处阻塞。修复方式为将 `metalock` 的获取提前，并在错误分支补充释放操作。

该缺陷属于**错误处理路径上的资源泄漏**：正常执行路径不受影响，仅在异常状态下暴露。

**触发条件。** 关闭数据库后再次发起事务。

**实验结果。**

```
fatal error: all goroutines are asleep - deadlock!
github.com/boltdb/bolt.(*DB).beginTx(...)  db.go:349   ← metalock.Lock()
```

修复版本输出：`第 2 次 Begin(false) 返回: database not open`。

归档日志记录的耗时分别为 85 ns（`b3_fixed_closed.log`）与本机复跑的 115 ns。该数值为单次调用读数，
受调度影响，仅用于说明错误分支立即返回，不作为稳定性能指标。

### 案例 3 · gRPC-Go `DialContext` 内部协程泄漏，`doneChan` 永不关闭

**缺陷机理。** `DialContext` 在阻塞模式下的实现如下（`clientconn.go`）：

```go
if cc.dopts.block {
    doneChan := make(chan struct{})
    go cc.lbWatcher(doneChan)
    <-doneChan
}
```

`doneChan` 的关闭责任落在 `lbWatcher` 内。缺陷版中，关闭动作只出现在一条路径上：只有在成功建立第一条连接之后才关闭 `doneChan`，且该关闭动作位于 `for addrs := range cc.dopts.balancer.Notify()` 循环体内部。当 balancer 在任何地址送达之前关闭 `Notify` 通道时，`for range` 立即结束，`lbWatcher` 直接返回，`doneChan` 无人关闭。

需要区分三个对象：`lbWatcher` 协程本身正常退出，并未泄漏；泄漏的是 `DialContext` 内部启动的匿名协程，它在 `<-doneChan` 上永久阻塞；外层 `DialContext` 因为还有 `select { case <-ctx.Done(): ... }`，在调用方设置了 deadline 时会超时返回。因此实际后果是**每次超时调用泄漏一个协程**，而不是调用方一定被永久挂死；只有未设 deadline 的阻塞调用才会一直等下去。

**修复方式。** 在 `lbWatcher` 入口补充 `defer` 关闭 `doneChan`（`if doneChan != nil` 判断用于避免与正常路径重复关闭）。

**触发条件。** ① `ClientConn` 启用阻塞模式；② balancer 提供非 `nil` 的 `Notify()` 通道；③ 该通道在返回任何地址之前被关闭。三项条件与网络环境无关，不依赖服务端、端口或时序，因此本案例的判定是确定性的。

**实验结果。**

```
缺陷版 39c8c386：
--- FAIL: TestClientLBWatcherWithClosedBalancer (0.10s)
    clientconn_test.go:390: lbWatcher with closed balancer didn't close doneChan after 100ms

修复版 4e56696c：
--- PASS: TestClientLBWatcherWithClosedBalancer (0.00s)
ok  	google.golang.org/grpc	0.003s
```

缺陷版耗时 0.10s 正是测试等待 `doneChan` 的超时上限；修复版 0.00s 说明通道在 `lbWatcher` 返回时立即被关闭。

**对照的可靠性。** 对两版本源码做全目录比对，差异仅涉及 `clientconn.go`（上述 9 行 `defer`）与 `clientconn_test.go`（新增的 16 行测试函数）两个文件，其余源码完全一致，排除了构建方式或依赖差异导致结果不同的可能。

**直接观测（2026-11-19 补充实验）。** 官方测试直接调用 `cc.lbWatcher(doneChan)`，验证的是通知契约，并未测量调用方返回后是否真有协程残留。为此另写一份探针（`code/cases/blocking/grpc-1424/probe/xu_dialcontext_leak_test.go`，两侧同一份、产品代码不改），走真实 `DialContext` 路径直接计数。

探针不调用任何内部函数，只用公开 API：实现一个不发布任何地址的 `Balancer`（`Notify()` 返回非 `nil` 通道，`Close()` 幂等关闭），用 `WithBlock()` + `WithBalancer()` 发起阻塞调用；`lbWatcher` 第二次调用 `Notify()`（即进入 `for range`）被视为已进入目标路径，随后轮询确认匿名协程已停在 `<-doneChan`，再取消 context 或等待 deadline 到期。取消后 `DialContext` 的 `defer` 调用 `cc.Close()`，进而 `balancer.Close()`，与真实关闭路径一致。每次调用返回后设 200 ms 观察窗口，按 0 / 50 / 100 / 200 ms 四点采样完整 goroutine dump。

时间顺序（缺陷版，`context-cancel`，N=1，单位 ms，相对进程内测试起点）：

| 时刻 | 事件 |
|---|---|
| 3.27 | `balancer.Start` |
| 3.29 | `Notify #1`（`DialContext` 自身）与 `Notify #2`（`lbWatcher` 进入 `for range`） |
| 4.31 | 探针确认 1 个协程停在 `clientconn.go:409` |
| 9.15 | 取消 context |
| 9.16 | `balancer.Close`（`DialContext` 的 `defer` → `cc.Close()`） |
| 9.20 | `DialContext` 返回 `context canceled`，该协程仍在 409 |
| 209.20 | 观察窗口结束，仍在 409 |

也就是说：调用已返回、balancer 已关闭、`lbWatcher` 已退出（dump 中 `lbWatcher` 栈数为 0），只有 `DialContext` 内部那个匿名协程留在 `<-doneChan` 上。

| 触发方式 | N | 侧 | 每进程目标残留栈（3 轮） | goroutine 总数 |
|---|---|---|---|---|
| `context-cancel` | 1 | 缺陷版 | 1 / 1 / 1 | 2 → 3 |
| `context-cancel` | 1 | 修复版 | 0 / 0 / 0 | 2 → 2 |
| `context-cancel` | 10 | 缺陷版 | 10 / 10 / 10 | 2 → 12 |
| `context-cancel` | 10 | 修复版 | 0 / 0 / 0 | 2 → 2 |
| `context-deadline` | 1 | 缺陷版 | 1 / 1 / 1 | 2 → 3 |
| `context-deadline` | 1 | 修复版 | 0 / 0 / 0 | 2 → 2 |
| 非阻塞对照（两侧） | 1、10 | 两版 | 0（全部 12 个进程） | 2 → 2 |

缺陷版 N=10 的逐调用残留数为 1、2、…、10，与调用次数一一对应；修复版每次都是「触发前 1 → 窗口结束 0」，说明 `defer` 在 `Notify` 关闭后立即关闭了 `doneChan`。非阻塞对照（不加 `WithBlock`、返回后主动 `Close`）两侧均为 0，排除了探针自身的协程或 balancer 清理逻辑造成的假象。

运行时定位到的栈形如（缺陷版，N=10 的第 10 次调用后）：

```
goroutine 21 [chan receive]:
google.golang.org/grpc.DialContext.func3()
	clientconn.go:409 +0x1d3
created by google.golang.org/grpc.DialContext in goroutine 13
	clientconn.go:386 +0x865
```

函数名取编译器生成的 `DialContext.func3`，匹配条件只依赖源码行号 409 与 `DialContext.func` 前缀，不预设闭包编号。共 30 个独立进程（2 版本 ×（cancel 2 档 + noblock 2 档 + deadline 1 档）× 3 轮），原始 dump、逐调用计数与汇总分别见 `logs/xu/leak-observation/` 与 `results/xu/leak-observation/summary.csv`。

由此可以确认：官方测试证明的是「`doneChan` 在 `Notify` 提前关闭时是否被关闭」这一契约，本实验证明的是该契约被破坏后**调用方返回后确实每次留下一个阻塞协程**，两者层级不同、互不替代。

### 案例 4 · gRPC-Go 并发 `WriteStatus` 向已关闭的 `writes` 通道发送

**缺陷机理。** handler transport 的 `WriteStatus` 用一把互斥锁保护 `streamDone` 的检查，但检查完立即释放锁，发送、关闭通道与置位分三步完成：

```go
ht.mu.Lock()
if ht.streamDone { ht.mu.Unlock(); return nil }
ht.mu.Unlock()                 // 锁在这里释放
err := ht.do(func() { ... })   // 向 ht.writes 发送闭包
close(ht.writes)               // 关闭通道
ht.mu.Lock()
ht.streamDone = true           // 最后才置位
ht.mu.Unlock()
```

`streamDone` 要等通道关闭之后才为真，这段窗口内其它 goroutine 仍会通过检查，随后向已关闭的 `writes` 发送，触发 `panic: send on closed channel`；若两个调用几乎同时走到关闭，也可能报 `close of closed channel`。

**修复方式。** 把 `streamDone = true` 移入同一临界区，删掉末尾的置位。后续调用拿锁时即看到 `true`，不会再进入发送与关闭。

**触发条件。** 多个 goroutine 并发结束同一条流，同时调用 `WriteStatus`。官方回归测试 `TestHandlerTransport_HandleStreams_MultiWriteStatus` 用 5 个 goroutine 构造这一条件。

**实验结果。** 竞争窗口很窄，单次执行几乎不触发：两侧各 20 次 `-count=1` 全部通过（记录见
`code/cases/non-blocking/grpc-1546/logs/neg_count1.txt`）。将同一测试在单进程内重复 200 次后，对照成立：

| 侧 | iter1–3 | 汇总 |
|---|---|---|
| 缺陷版 `cf79c849` | FAIL ×3 | 3/3 `panic: send on closed channel` |
| 修复版 `22c3f92f` | PASS ×3 | 3/3 PASS |

三轮崩溃分别出现在第 14、33、4 次重复。`200` 是选定的重复预算，不是触发保证：另做一次独立复测
（同一官方源码、`GOPROXY=off`、每轮上限 200 次）三轮中两轮命中（第 8、101 次），一轮跑满 200 次未触发。
因此该案例的结论是「同一测试、同一重复次数下两侧按轮对照可观测到差异」，既不是「一次运行必崩」，
也不能把某一轮必中当作判据。

---

## 6. 与提交说明的差异

以下三处差异需如实说明。

### 差异一：案例 2 的 remap 死锁路径不可触发

修复提交的说明为 "Fix deadlock on remmap"。据此设计的压力测试（4 个读事务持续持锁，写事务连续写入 256 KB 数据以迫使数据库越过映射阈值，8 秒内完成 800 余次写入）在缺陷版本与修复版本上均未出现阻塞。

源码分析表明：该快照中 `db.mmap()` 仅获取 `mmaplock`，而写事务持有的 `metalock` 在 `beginRWTx` 返回前即已释放，提交与内存分配阶段并不持有该锁。因此两个方向的循环等待无法成立。

该修复提交实际修正多处问题，本快照中可确定性触发的是**错误分支漏解锁**一处。报告按实际复现结果记录，未沿用提交说明中的表述。

### 差异二：案例 3 的官方测试验证通知契约，协程残留由补充探针直接观测

本案例的官方测试直接调用 `cc.lbWatcher(doneChan)`，并未经过完整的 `DialContext`，因此它验证的是通知契约（`doneChan` 是否被关闭），而不是协程数量。外层 `DialContext` 在调用方设置 deadline 时会返回 `context deadline exceeded`，所以「协程泄漏」与「调用方永久阻塞」不能混为一谈。

初版报告只凭代码路径分析推断「内部匿名协程永久阻塞在 `<-doneChan`」。2026-11-19 补充的探针走真实 `DialContext`，用 goroutine dump 直接定位到停在该行的协程：缺陷版每次调用残留 1 个、N=10 时累积到 10 个，修复版在同样输入与窗口内为 0。因此现在这一结论有实测支撑；但官方测试本身仍是契约测试，两者的结论层级不同。

### 差异三：案例 4 的官方测试单次执行不足以判定

案例 4 的回归测试由修复提交自带，但其竞争窗口极窄：在本机，`-count=1` 时缺陷版 20 次全部通过，
需要把同一测试在同一进程内重复上百次才容易观测到 panic（实测落在第 4 至 128 次重复不等）。
因此本案例的判定口径是「同一测试、同一重复次数下两侧比较」，
而不是「跑一次看是否崩溃」。这一点也是该缺陷值得记录的原因：测试本身存在，但按常规方式执行会漏判。

---

## 7. 局限性

- 仅覆盖 4 个缺陷（BoltDB 2 个、gRPC-Go 2 个），结论不具统计意义，仅验证方法可行性；
- 论文统计 171 个缺陷（blocking 85、non-blocking 86），公开数据集中有修复提交可查的条目为 169 条；
  本报告不对这些条目作「均可运行」的承诺，实际可复现性受代码年代、工具链与外部依赖影响；
- 论文表格统计 BoltDB 共 5 个缺陷，其中 `boltdb#392` 与 `boltdb#240` 未提供可用的修复提交对照，
  本报告未纳入；
- BoltDB 部分使用 go1.6.4，与缺陷发生时的 Go 版本（1.2 / 1.4）存在差异；gRPC-Go 部分使用 go1.22.9
  编译 2017 年代码，均非缺陷发生时的原生版本；
- 案例 1、2 为单次运行，未作重复性统计；案例 3 采用修复提交自带的回归测试，属于以官方测试验证
  官方修复，独立性弱于案例 1 的自编触发程序；案例 4 同样使用官方测试，但通过固定重复次数提高了
  判定的稳定性，并保留了单次执行不触发的负结果；
- 案例 3 的协程残留已由补充探针在 30 个独立进程上直接观测，但探针只覆盖「balancer 在任何地址送达前
  关闭 `Notify`」这一条路径，且运行在本机单一环境（Go 1.22.9 / WSL2），不能据此推断线上系统的全部
  触发路径与泄漏规模。

---

## 8. 复现步骤

### 8.1 BoltDB（需 Linux/WSL2 + Go 1.6.4）

```bash
cd code/harness
bash xu_boltdb_setup.sh          # 下载 4 份源码快照（2 个缺陷 × buggy/fixed）

bash xu_boltdb_run.sh 02 buggy   # 预期：Close 立即返回并触发提交崩溃
bash xu_boltdb_run.sh 02 fixed   # 预期：Close 阻塞约 55ms 后提交成功
bash xu_boltdb_run.sh 03 buggy   # 预期：deadlock
bash xu_boltdb_run.sh 03 fixed   # 预期：正常返回错误
```

运行需 Go 1.6.4，默认路径 `/usr/local/go-versions/go1.6.4`，可通过 `GOROOT=...` 覆盖；
工作目录默认 `code/harness/_work`，可通过 `WORK=...` 覆盖。触发程序取自
`code/cases/non-blocking/boltdb-341/code/main.go` 与
`code/cases/blocking/boltdb-begin-lock-leak/code/main.go`。

### 8.2 gRPC-Go（个人 module 入口 / 组内公共驱动）

案例 3 与案例 4 都能在 Go 1.22.9 + module 下复跑，源码按提交号自动下载：

```bash
# 案例 3：DialContext 协程泄漏（官方回归测试）
bash code/cases/blocking/grpc-1424/code/xu-run-1229.sh 3 60

# 案例 3：真实 DialContext 路径的协程残留观测（本报告 5 节补充实验）
bash code/cases/blocking/grpc-1424/code/xu-observe-leak.sh

# 案例 4：并发 WriteStatus
bash code/cases/non-blocking/grpc-1546/run.sh 200 3
```

两个脚本都会下载两侧官方源码、核对关键文件 sha256、补齐测试文件后才开跑，退出码统一为
`0` 对照成立 / `2` buggy 未复现 / `3` fixed 未通过 / `4` 源码或环境问题。
案例 3 的归档输出在 `code/cases/blocking/grpc-1424/logs/xu/1229/`：buggy 3/3 `FAIL(assert)`、fixed 3/3 `PASS`。

`xu-observe-leak.sh` 先在专用源码目录 `$HOME/grpc1424-leak/` 里做同样的准备，再复制探针跑完整矩阵
（30 个独立进程，约 3 分钟），输出到 `logs/xu/leak-observation/` 与
`results/xu/leak-observation/summary.csv`。它会拒绝覆盖已有归档，确需重跑加 `XU_OBS_FORCE=1`。

案例 3 另有一条组内交叉验证路径：`code/cases/blocking/grpc-1424/run.sh` 调用公共驱动 `p4_case.sh`，
走 Go 1.10.8 + `GOPATH`。该驱动写死 `GOROOT=/usr/local/go1.10.8`，归档日志的 `env.txt` 记录
`uname=Linux 4.15.0-213-generic`，说明那份结果产自 1.10.8 环境；本机 WSL 的同一版本装在
`/usr/local/go-versions/go1.10.8`，所以本机复跑走上面那条 module 入口，公共驱动保持原样不动。
