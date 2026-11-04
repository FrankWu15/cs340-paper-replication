# 并发缺陷复现报告：BoltDB 与 gRPC-Go

**复现对象**：《Understanding Real-World Concurrency Bugs in Go》(ASPLOS'19) 公开数据集
`system-pclub/go-concurrency-bugs` 中的并发缺陷

**报告范围**：BoltDB 的 2 个缺陷、gRPC-Go 的 1 个缺陷，共 3 个案例。
其中 BoltDB 案例 01（读事务引用共享 meta 页指针，修复提交 `7fb06fee`）由小组另一成员
完成并单独提交，本报告不再包含。

---

## 1. 概述

本实验从上述数据集中选取 BoltDB 与 gRPC-Go 两个项目的三个并发缺陷，采用**缺陷版本与修复版本同程序对照**的方法进行复现：同一份触发程序（或同一回归测试）分别在缺陷提交（buggy）与修复提交（fixed）上编译运行，要求前者出现可观测故障、后者正常结束。

该方法的作用在于建立因果关系：单独观测到一次崩溃或死锁，不足以说明该现象由目标缺陷引起；只有在同一程序、同一构建条件下，版本差异构成唯一变量时，故障的出现与消失才能归因于该修复提交。

**复现结论**：三个缺陷均获得对照结果成立。其中与提交说明（或论文描述）存在偏差的两处已在第 6 节如实说明。

---

## 2. 复现结果

| 编号 | 应用 | 缺陷 | 类型 | 缺陷版本表现 | 修复版本表现 | 结论 |
|---|---|---|---|---|---|---|
| 1 | BoltDB | `Close()` 未等待进行中的写事务 | non-blocking | 关闭耗时 35 µs 即返回，随后提交触发空指针崩溃 | 关闭阻塞 55 ms 至事务结束，提交成功 | 与预期一致 |
| 2 | BoltDB | 事务入口错误分支漏解锁 | blocking | `all goroutines are asleep - deadlock!` | 127 ns 返回 `ErrDatabaseNotOpen` | 故障可复现，触发路径与提交说明不同 |
| 3 | gRPC-Go | `DialContext` 中协程泄漏导致永久阻塞 | blocking | 回归测试 FAIL（100 ms 内 `doneChan` 未关闭） | 回归测试 PASS | 与预期一致 |

三个案例的共同特征：均无需专用检测工具即可定位。Go 运行时的死锁检测、测试超时断言与崩溃栈信息已足以暴露问题，此结论与论文第 7 节一致。

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

此差异属于构建手段不同，不影响前后对照的有效性：缺陷版与修复版使用完全相同的 `go.mod` / `go.sum` / Go 版本，唯一变量是那 9 行 `defer`（见 `code/grpc-go/notes/source-diff.txt`）。

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

第 ④ 步是流程的核心。触发条件不由试错得出，而由补丁的改动内容反推：补丁在某一错误分支中补充了释放操作，即说明缺陷存在于该分支的资源管理；补丁以 `defer` 补充通道关闭，即说明缺陷源于该通道在异常路径上无人关闭。

判定标准：缺陷版本须出现可观测故障（崩溃、死锁或断言失败之一），修复版本须正常完成。

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

修复版本输出：`第 2 次 Begin(false) 返回: database not open（耗时 127ns）`。

### 案例 3 · gRPC-Go `DialContext` 中协程泄漏导致永久阻塞

**缺陷机理。** `DialContext` 在阻塞模式下的实现如下（`clientconn.go:406-410`）：

```go
if cc.dopts.block {
    doneChan := make(chan struct{})
    go cc.lbWatcher(doneChan)
    <-doneChan
}
```

`doneChan` 的关闭责任落在 `lbWatcher` 内。缺陷版中，关闭动作只出现在一条路径上：只有在成功建立第一条连接之后才关闭 `doneChan`，且该关闭动作位于 `for addrs := range cc.dopts.balancer.Notify()` 循环体内部。当 balancer 在任何地址送达之前关闭 `Notify` 通道时，`for range` 立即结束，`lbWatcher` 直接返回，`doneChan` 无人关闭。

需要区分两个对象：`lbWatcher` 协程本身正常退出，并未泄漏；泄漏的是 `DialContext` 内部的匿名协程（`go func() { ...; <-doneChan; ... }()`）。超时发生后 `DialContext` 返回，而该匿名协程永久阻塞在 `<-doneChan` 上。因此每一次「超时且 balancer 提前关闭」的 `DialContext` 调用都会泄漏一个协程。

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

---

## 6. 与提交说明的差异

以下两处差异需如实说明。

### 差异一：案例 2 的 remap 死锁路径不可触发

修复提交的说明为 "Fix deadlock on remmap"。据此设计的压力测试（4 个读事务持续持锁，写事务连续写入 256 KB 数据以迫使数据库越过映射阈值，8 秒内完成 800 余次写入）在缺陷版本与修复版本上均未出现阻塞。

源码分析表明：该快照中 `db.mmap()` 仅获取 `mmaplock`，而写事务持有的 `metalock` 在 `beginRWTx` 返回前即已释放，提交与内存分配阶段并不持有该锁。因此两个方向的循环等待无法成立。

该修复提交实际修正多处问题，本快照中可确定性触发的是**错误分支漏解锁**一处。报告按实际复现结果记录，未沿用提交说明中的表述。

### 差异二：案例 3 验证的是通知契约，而非直接观测协程数量

本案例的测试直接调用 `cc.lbWatcher(doneChan)`，并未经过完整的 `DialContext`，因此验证的是通知契约（`doneChan` 是否被关闭），而非直接观测协程数量。该契约被破坏后的实际后果是 `DialContext` 内部协程永久阻塞，此结论来自代码路径分析，未通过 `runtime.NumGoroutine()` 或 goroutine dump 实测验证。

---

## 7. 局限性

- 仅覆盖 3 个缺陷（BoltDB 2 个、gRPC-Go 1 个），数据集共 169 个（blocking 83、non-blocking 86），结论不具统计意义，仅验证方法可行性；
- 论文表格统计 BoltDB 共 5 个缺陷，其中 blocking 类 `boltdb#392` 与 `boltdb#240` 未提供修复提交哈希，无法进行版本对照，故未纳入；
- BoltDB 部分使用 go1.6.4，与缺陷发生时的 Go 版本（1.2 / 1.4）存在差异；gRPC-Go 部分使用 go1.22.9 编译 2017 年代码，均非缺陷发生时的原生版本；
- 案例 1、2 为单次运行，未作重复性统计；
- 案例 3 采用修复提交自带的回归测试，属于以官方测试验证官方修复，独立性弱于案例 1 的自编触发程序。

---

## 8. 复现步骤

### 8.1 BoltDB（需 Linux/WSL2 + Go 1.6.4）

```bash
cd code/boltdb
bash setup.sh              # 下载 4 份源码快照（2 个缺陷 × buggy/fixed）

bash run.sh 02 buggy       # 预期：Close 立即返回并触发提交崩溃
bash run.sh 02 fixed       # 预期：Close 阻塞约 55ms 后提交成功
bash run.sh 03 buggy       # 预期：deadlock
bash run.sh 03 fixed       # 预期：正常返回错误
```

运行需 Go 1.6.4，默认路径 `/usr/local/go-versions/go1.6.4`，可通过 `GOROOT=...` 覆盖。

### 8.2 gRPC-Go（需 Go 1.22.9）

```bash
export GO111MODULE=on
export GOPROXY=https://goproxy.cn,direct
export GOSUMDB=off

# 分别在缺陷版与修复版工作目录放置同一份源码与 go.mod / go.sum
# （版本固定文件见 code/grpc-go/notes/），运行修复提交新增的回归测试：
go test -run TestClientLBWatcherWithClosedBalancer -v
```

缺陷版预期 FAIL，修复版预期 PASS。构建细节与已知网络问题见 `code/grpc-go/notes/env.md`。

各案例的缺陷机理详见 `code/*/cases/*/` 下的说明文档，原始输出见 `results/` 目录。
