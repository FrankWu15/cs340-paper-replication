# Case 01：DialContext 中 goroutine 泄漏导致永久阻塞

## 基本信息

| 项 | 值 |
|---|---|
| 应用 | gRPC-Go |
| 数据集路径 | `blocking-bugs/grpc-go/4e56696c6c5a8cd7b711a1eb8936463559361da5.txt` |
| 类型 | blocking（goroutine 泄漏） |
| 修复提交 | `4e56696c6c5a8cd7b711a1eb8936463559361da5`（2017-08-04） |
| 提交说明 | Fix a goroutine leak in DialContext (#1424) |
| 缺陷版 | `39c8c3866d926d95e11c03508bf83d00f2963f91`（修复提交的父提交） |
| 触发用例 | `TestClientLBWatcherWithClosedBalancer`（修复提交新增） |

## 缺陷机理

`DialContext` 在阻塞模式下的实现如下（`clientconn.go:406-410`）：

```go
if cc.dopts.block {
    doneChan := make(chan struct{})
    go cc.lbWatcher(doneChan)
    <-doneChan
}
```

`doneChan` 的关闭责任落在 `lbWatcher` 内。缺陷版中，关闭动作只出现在一条路径上：

```go
for _, a := range add {
    var err error
    if doneChan != nil {
        err = cc.resetAddrConn(a, true, nil)
        if err == nil {
            close(doneChan)
            doneChan = nil
        }
    }
}
```

即：**只有在成功建立第一条连接之后**才关闭 `doneChan`。该关闭动作位于 `for addrs := range cc.dopts.balancer.Notify()` 循环体内部。

当 balancer 在任何地址送达之前关闭 `Notify` 通道时，`for range` 立即结束，`lbWatcher` 直接返回，`doneChan` 无人关闭。

需要区分两个对象，此前的分析曾将二者混淆：

- `lbWatcher` 协程本身**正常退出**，并未泄漏；
- 泄漏的是 `DialContext` 内部那个匿名协程。该协程结构为 `go func() { ...; <-doneChan; ... }()`，外层通过 `select` 等待 `ctx.Done()` 或 `waitC`。超时发生后，`DialContext` 返回，而该匿名协程永久阻塞在 `<-doneChan` 上。

因此每一次「超时且 balancer 提前关闭」的 `DialContext` 调用都会泄漏一个协程，并持有其栈与相关对象。

## 修复方式

在 `lbWatcher` 入口加 `defer`：

```go
defer func() {
    if doneChan != nil {
        close(doneChan)
    }
}()
```

`if doneChan != nil` 的判断是必要的：正常路径中关闭后已将 `doneChan` 置 `nil`，此处用于避免重复关闭导致 panic。

## 触发条件

1. `ClientConn` 启用阻塞模式（`cc.dopts.block == true`）；
2. balancer 提供非 `nil` 的 `Notify()` 通道；
3. 该通道在返回任何地址之前被关闭。

三项条件与网络环境无关，不依赖服务端、端口或时序，因此本 case 的判定是确定性的。

## 实验结果

| 版本 | 结果 | 耗时 |
|---|---|---|
| 缺陷版 `39c8c386` | `FAIL`：`lbWatcher with closed balancer didn't close doneChan after 100ms` | 0.10s |
| 修复版 `4e56696c` | `PASS` | 0.00s |

原始输出见仓库 `../logs/xu/grpc_buggy.log` 与 `../logs/xu/grpc_fixed.log`。

```
=== RUN   TestClientLBWatcherWithClosedBalancer
    clientconn_test.go:390: lbWatcher with closed balancer didn't close doneChan after 100ms
--- FAIL: TestClientLBWatcherWithClosedBalancer (0.10s)
```

```
=== RUN   TestClientLBWatcherWithClosedBalancer
--- PASS: TestClientLBWatcherWithClosedBalancer (0.00s)
ok  	google.golang.org/grpc	0.003s
```

缺陷版耗时为 0.10s，正是测试用例等待 `doneChan` 的超时上限；修复版为 0.00s，说明通道在 `lbWatcher` 返回时立即被关闭。

## 对照的可靠性

对两版本源码做全目录比对，差异仅涉及两个文件：

```
Files .../clientconn.go ... differ
Files .../clientconn_test.go ... differ
```

`clientconn.go` 的差异即上述 9 行 `defer`；`clientconn_test.go` 的差异即新增的 16 行测试函数。两版本其余源码完全一致，排除了「构建方式或依赖差异导致结果不同」的可能。完整差异见 `../notes/source-diff.txt`。

## 判定性质的说明

本 case 的测试直接调用 `cc.lbWatcher(doneChan)`，并未经过完整的 `DialContext`，因此**验证的是通知契约（`doneChan` 是否被关闭），而非直接观测协程数量**。该契约被破坏后的实际后果是 `DialContext` 内部协程永久阻塞，此结论来自代码路径分析，未通过 `runtime.NumGoroutine()` 或 goroutine dump 实测验证。

若需补强，可另写一个端到端用例：以超时 ctx 调用 `DialContext`，令 balancer 提前关闭，统计调用前后的协程数。当前版本未包含该用例。

## 复跑（Go 1.22.9 + module）

```bash
bash code/cases/blocking/grpc-1424/code/xu-run-1229.sh          # 3 轮
bash code/cases/blocking/grpc-1424/code/xu-run-1229.sh 3 60     # iters timeout
```

脚本按提交号下载两侧源码到 `$HOME/grpc1424/{buggy,fixed}`，核对 `clientconn.go` 的 sha256、
补齐与修复版一致的测试文件、复制 `notes/` 里的 `go.mod`/`go.sum` 后开跑；
判定为 buggy `FAIL(assert)` ×3、fixed `PASS` ×3，退出码语义与 grpc#1546 的 `run.sh` 相同
（0 对照成立 / 2 未复现 / 3 fixed 未通过 / 4 环境问题）。

本轮归档日志在 `../logs/xu/1229/`：buggy 3/3 命中、fixed 3/3 通过，
`env.txt` 记录两侧 `clientconn.go`、测试文件与依赖文件的 sha256。

同目录的 `run.sh` 是 Go 1.10.8 + GOPATH 的另一条路径（依赖组内公共驱动 `p4_case.sh`），
两者互不替代：`run.sh` 的产出是组内交叉验证，本脚本是个人 module 环境下的独立复跑。

## 真实 DialContext 路径的协程残留观测（2026-11-19）

### 要回答的问题

官方回归测试 `TestClientLBWatcherWithClosedBalancer` 直接调用 `cc.lbWatcher(doneChan)`，
验证的是「`Notify` 提前关闭时 `doneChan` 是否被关闭」这一通知契约。它没有经过
`DialContext`，也没有统计协程数量。因此「调用方返回后库内部是否还留着等待 `doneChan`
的协程」此前只有源码推断，本实验补上直接观测。

### 设计要点

- 探针 `probe/xu_dialcontext_leak_test.go` 放在 `package grpc_test`，只用公开 API，
  两侧源码树各放一份完全相同的副本，产品代码一行不改。
- 探针实现一个不发布地址的 balancer：`Notify()` 返回非 `nil` 通道且不发地址，
  `Close()` 用 `sync.Once` 幂等关闭它。关闭由连接生命周期触发（`DialContext` 的
  `defer` → `cc.Close()` → `balancer.Close()`），不直接改库内部状态。
- `lbWatcher` 第二次调用 `Notify()`（第 1 次来自 `DialContext` 自身）即表示它已进入
  `for range`。此后轮询 `runtime.Stack`，确认匿名协程已停在 `clientconn.go:409`
  的 `<-doneChan`，才触发取消；避免「取消得太早、协程还没起」造成的假阴性。
- 每次调用返回后设 200 ms 观察窗口，按 0 / 50 / 100 / 200 ms 四点采样，
  允许正常清理完成；窗口长度与全部采样值都记进 `metrics.json`。
- 计数只按 goroutine 块统计（以 `goroutine ` 开头的块），`created by ...` 行不会
  被算成一个协程。目标栈的匹配条件是「`DialContext.func` 前缀 + `clientconn.go:409`」，
  不预设编译器生成的闭包编号（实测为 `DialContext.func3`）。
- 每个配置跑在独立进程里，进程退出即回收缺陷版的残留，不污染下一轮。

### 时序（buggy，context-cancel，N=1，单位 ms）

```
 3.27  balancer.Start
 3.29  Notify #1 (DialContext) / Notify #2 (lbWatcher 进入 range)
 4.31  探针确认 1 个协程停在 clientconn.go:409
 9.15  cancel(ctx)
 9.16  balancer.Close  <- DialContext 的 defer 调用 cc.Close()
 9.20  DialContext 返回 context canceled   [该协程仍在 409]
209.20 观察窗口结束                        [仍在 409]
```

`lbWatcher` 已退出（dump 里 `lbWatcher` 栈数为 0），`balancer` 已关闭，调用已返回，
只有 `DialContext` 内部的匿名协程留在 `<-doneChan` 上：

```
goroutine 21 [chan receive]:
google.golang.org/grpc.DialContext.func3()
	clientconn.go:409 +0x1d3
created by google.golang.org/grpc.DialContext in goroutine 13
	clientconn.go:386 +0x865
```

### 结果

| 触发方式 | N | 侧 | 目标残留栈（3 轮） | goroutine 总数 |
|---|---|---|---|---|
| context-cancel | 1 | buggy | 1 / 1 / 1 | 2 → 3 |
| context-cancel | 1 | fixed | 0 / 0 / 0 | 2 → 2 |
| context-cancel | 10 | buggy | 10 / 10 / 10 | 2 → 12 |
| context-cancel | 10 | fixed | 0 / 0 / 0 | 2 → 2 |
| context-deadline | 1 | buggy | 1 / 1 / 1 | 2 → 3 |
| context-deadline | 1 | fixed | 0 / 0 / 0 | 2 → 2 |
| 非阻塞对照 | 1, 10 | 两版 | 0（12 个进程全部） | 2 → 2 |

- buggy N=10 的逐调用残留是 1、2、…、10，与调用次数一一对应，不只是「总数变大」。
- fixed 每次都是「触发前 1 → 窗口结束 0」：`lbWatcher` 的 `defer` 在 `Notify` 关闭后
  立即关闭 `doneChan`，匿名协程随之退出。
- 非阻塞对照（不加 `WithBlock`、返回后主动 `Close`）两侧都是 0，说明残留不是探针
  自己的协程或 balancer 清理逻辑造成的。

### 边界

- 只覆盖「balancer 在任何地址送达之前关闭 `Notify`」这一条路径。
- 单机、单进程、Go 1.22.9 / WSL2 环境；N 只到 10，属于机制验证，不是统计研究。
- `-count=1` 单次 `go test` 只跑一个测试，本实验的「N」是同一进程内顺序调用
  `DialContext` 的次数，不是测试重复次数。

### 复跑与产物

```bash
bash code/xu-observe-leak.sh          # 约 3 分钟，30 个独立进程
```

判定同时要求四项：buggy 残留 = N、fixed = 0、非阻塞对照 = 0、每个进程的 N 次调用
都已返回。退出码 `0` 成立 / `2` 未观测到 / `3` fixed 或对照有残留 / `4` 环境问题或
有调用未返回。已有归档不必重跑，用 `XU_OBS_JUDGE_ONLY=1 bash code/xu-observe-leak.sh`
可只重算汇总与判定（不覆盖归档里的 `summary.txt`）。

源码准备复用 `xu-run-1229.sh`（专用目录 `$HOME/grpc1424-leak/`），不覆盖
`logs/xu/1229/`。产物：

- `../logs/xu/leak-observation/<side>/<mode>/N<n>/round<r>/`：`metrics.json`、
  `env.json`、`stdout.log`、完整 goroutine dump（每轮前两次与最后一次调用各两份）
- `../logs/xu/leak-observation/env.txt`：工具链、两侧提交号与关键文件 sha256
- `../results/xu/leak-observation/summary.csv`：每个独立进程一行
