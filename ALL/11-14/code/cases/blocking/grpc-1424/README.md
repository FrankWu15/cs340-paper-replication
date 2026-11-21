# grpc#1424 · DialContext 里 lbWatcher 泄漏，doneChan 永不关闭

| 项 | 值 |
|---|---|
| 分类 | **blocking**（阻塞式 Dial 永不返回） |
| 仓库 | `google.golang.org/grpc` |
| buggy 提交 | `39c8c3866d926d95e11c03508bf83d00f2963f91` |
| 修复提交 | `4e56696c6c5a8cd7b711a1eb8936463559361da5`（"Fix a goroutine leak in DialContext (#1424)"） |
| 触发用例 | `TestClientLBWatcherWithClosedBalancer`（根包，补丁自带） |
| 判定 | buggy **FAIL ×3** / fixed **PASS ×3** |
| 负责 | 李振炜 1240012318、许汝轩 1240011357（两人各自独立复现，本目录合并） |

## 症状

`DialContext` 在阻塞模式下起一个 `lbWatcher` 并在 `<-doneChan` 上等它；`doneChan`
的关闭责任落在 `lbWatcher` 内，但关闭动作只出现在一条路径上。balancer 已关闭时
走不到那条路径，`doneChan` 永不关闭，`Dial` 永久阻塞。

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
| 许汝轩（Go 1.22.9，module 模式） | `logs/xu/` | `grpc_buggy.log`、`grpc_fixed.log` |
| 许汝轩的记录 | `code/xu-case.md` | 机理、触发条件、可靠性说明 |
| 修复补丁 | `patches/01-lbwatcher-leak.patch` | 上游提交原文 |
| 依赖固定 | `notes/` | `go.mod`、`go.sum`、两版本源码差异、构建环境 |
| 截图 | `shots/grpc1424_repro.png` | 终端截图 |

## 重跑

```bash
bash run.sh          # 3 次 × 60s；Go 1.10.8 + GOPATH 模式
```

许汝轩那套（Go 1.22.9 + module）的步骤见 `code/xu-case.md` 与 `notes/env.md`，
与上面的脚本是两条独立路径。
