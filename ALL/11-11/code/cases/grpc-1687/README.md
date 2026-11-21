# grpc#1687 —— 向已关闭的 channel 发送

| 项 | 内容 |
|---|---|
| 仓库 | google.golang.org/grpc |
| 类型 | 非阻塞（panic，必现） |
| buggy | `c6b46087ab^1` |
| 修复提交 | `c6b46087ab` |
| 测试 | `transport/TestHandlerTransport_HandleStreams_WriteStatusWrite` |

## 症状

写状态码路径上向已关闭的 channel 发送，直接 panic 终止进程：

```
panic: send on closed channel
  transport/handler_server.go:170
  ← 调用方 handler_server.go:256
```

## 判定

不需要放大时间窗口，单次运行必现；fixed 侧正常 PASS。

## 实测

| 侧 | iter1 | iter2 | iter3 | SUMMARY |
|---|---|---|---|---|
| buggy | FAIL | FAIL | FAIL | pass=0 fail=3 |
| fixed | PASS | PASS | PASS | pass=3 fail=0 |

## 注意

包目录是 `transport`。早前一次实验填成 `test`，两侧 6 轮全部 NOTRUN，
`go test` 依然打印 `ok` —— 这是最容易误判为成功的一种情况。

## 证据

- `results/logs/grpc-1687/`
- `results/shots/grpc-1687_repro.png`
