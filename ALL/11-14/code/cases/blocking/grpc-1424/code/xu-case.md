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

原始输出见仓库 `results/grpc-go/grpc_buggy.log` 与 `results/grpc-go/grpc_fixed.log`。

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
