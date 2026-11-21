# grpc#1424 —— balancer 关闭后 doneChan 永不关闭

| 项 | 内容 |
|---|---|
| 仓库 | google.golang.org/grpc |
| 类型 | 阻塞（监听协程泄漏，调用方空等） |
| buggy | `4e56696c6c^1` |
| 修复提交 | `4e56696c6c` |
| 测试 | `./TestClientLBWatcherWithClosedBalancer`（仓库根包） |

## 症状

balancer 已关闭，`lbWatcher` 的退出信号 `doneChan` 却始终不关闭，等待它的调用方永远不会被唤醒。

## 判定

测试在 100ms 窗口内检查 `doneChan`：

```
clientconn_test.go:390: lbWatcher with closed balancer didn't close doneChan after 100ms
```

## 实测

| 侧 | iter1 | iter2 | iter3 | SUMMARY |
|---|---|---|---|---|
| buggy | FAIL | FAIL | FAIL | pass=0 fail=3 |
| fixed | PASS | PASS | PASS | pass=3 fail=0 |

## 注意

包目录是仓库根 `.`，不是 `balancer/`。早前一次实验把它填成 `balancer`，
`-run` 空匹配后 `go test` 仍输出 `ok`，会造成假通过。

## 证据

- `results/logs/grpc-1424/`
- `results/shots/grpc-1424_repro.png`
