# grpc#1424 · DialContext 里 lbWatcher 泄漏，doneChan 永不关闭

| 项 | 值 |
|---|---|
| 分类 | **blocking**（无 deadline 的阻塞 Dial 永不返回；带 deadline 时超时返回但内部协程残留） |
| 仓库 | `google.golang.org/grpc` |
| buggy 提交 | `39c8c3866d926d95e11c03508bf83d00f2963f91` |
| 修复提交 | `4e56696c6c5a8cd7b711a1eb8936463559361da5`（"Fix a goroutine leak in DialContext (#1424)"） |
| 触发用例 | `TestClientLBWatcherWithClosedBalancer`（根包，补丁自带） |
| 判定 | buggy **FAIL ×3** / fixed **PASS ×3** |
| 负责 | 李振炜 1240012318、许汝轩 1240011357（两人各自独立复现，本目录合并） |

## 症状

`DialContext` 在阻塞模式下起一个 `lbWatcher` 并在 `<-doneChan` 上等它；`doneChan`
的关闭责任落在 `lbWatcher` 内，但关闭动作只出现在一条路径上。balancer 已关闭时
走不到那条路径，`doneChan` 永不关闭。

需要区分三层：`lbWatcher` 本身会正常退出，不算泄漏；真正残留的是 `DialContext`
内部启动的匿名协程，它卡在 `<-doneChan` 上；外层 `DialContext` 另有
`select { case <-ctx.Done(): ... }`，调用方设置 deadline 时会超时返回，未设 deadline
的阻塞调用才会一直等下去。官方测试直接调用 `lbWatcher`，验证的是 `doneChan`
的关闭契约；真实 `DialContext` 路径上的协程残留由 `probe/` 下的探针单独观测（见下）。

```
--- FAIL: TestClientLBWatcherWithClosedBalancer (0.10s)
	clientconn_test.go:390: lbWatcher with closed balancer didn't close doneChan after 100ms
```

修复提交在 watcher 的关闭分支里补上了 `close(doneChan)`。

## 判定口径

| 侧 | iter1 | iter2 | iter3 |
|---|---|---|---|
| buggy | FAIL | FAIL | FAIL |
| fixed | PASS | PASS | PASS |

## 证据

两位成员各跑了一遍，两组独立证据都在：

| 来源 | 路径 | 说明 |
|---|---|---|
| 李振炜（`p4_case.sh`，Go 1.10.8） | `logs/` | `summary.txt`、`env.txt`、两侧各 3 份原始输出 |
| 许汝轩（Go 1.22.9，module 模式） | `logs/xu/1229/` | 官方回归测试 3 轮：buggy `FAIL(assert)`、fixed `PASS` |
| 许汝轩（真实 DialContext 观测） | `logs/xu/leak-observation/` | 30 个独立进程的 goroutine dump、逐调用计数、时序 |
| 许汝轩（观测汇总） | `results/xu/leak-observation/summary.csv` | 每个进程一行：残留栈数、返回值、退出码 |
| 观测探针 | `probe/xu_dialcontext_leak_test.go` | 两侧同一份，只用公开 API，产品代码不改 |
| 许汝轩的记录 | `code/xu-case.md` | 机理、触发条件、可靠性说明、观测实验 |
| 修复补丁 | `patches/01-lbwatcher-leak.patch` | 上游提交原文 |
| 依赖固定 | `notes/` | `go.mod`、`go.sum`、两版本源码差异、构建环境 |
| 截图 | `shots/grpc1424_repro.png` | 终端截图 |

## 观测实验（真实 DialContext 路径）

官方测试只验证「`Notify` 提前关闭时 `doneChan` 是否被关闭」。`probe/` 里的探针走真实
`DialContext`：不发布地址的 balancer 进入 `for range` 后取消 context，调用返回后按 200 ms
窗口抓 goroutine dump，直接统计停在 `clientconn.go:409` `<-doneChan` 的匿名协程。

| 配置 | buggy 残留 | fixed 残留 |
|---|---|---|
| `context-cancel`，N=1，3 轮 | 1 / 1 / 1 | 0 / 0 / 0 |
| `context-cancel`，N=10，3 轮 | 10 / 10 / 10（逐调用 1→10） | 0 / 0 / 0 |
| `context-deadline`，N=1，3 轮 | 1 / 1 / 1 | 0 / 0 / 0 |
| 非阻塞对照，N=1、10，各 3 轮 | 0 | 0 |

调用返回、`balancer.Close`、`lbWatcher` 退出都发生在观察窗口之前，只有匿名协程留在
`<-doneChan` 上；`lbWatcher` 栈数在窗口内为 0，可从 dump 直接核对。

判定同时要求五项：归档记录与矩阵定义逐条对齐（默认 30 条，不缺、不多、不重复）、
缺陷版残留 = N、修复版为 0、非阻塞对照为 0、每个进程的 N 次调用全部返回。
任一项不满足即非 0 退出（`2` 未观测到 / `3` 修复版或对照有残留 /
`4` 环境问题、调用未返回或归档不完整），空目录或缺轮次不会被判成成立。

## 重跑

```bash
bash run.sh                        # 3 次 × 60s；Go 1.10.8 + GOPATH 模式
bash code/xu-run-1229.sh 3 60      # Go 1.22.9 + module 模式（官方回归测试）
bash code/xu-observe-leak.sh       # Go 1.22.9 + module 模式（协程残留观测，约 3 分钟）
```

许汝轩那套（Go 1.22.9 + module）的步骤见 `code/xu-case.md` 与 `notes/env.md`，
与上面的 `run.sh` 是两条独立路径。
