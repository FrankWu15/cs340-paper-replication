# grpc#1293 —— 删除在途流不通知调用方

| 项 | 内容 |
|---|---|
| 仓库 | google.golang.org/grpc |
| 类型 | 阻塞（调用方永久等待） |
| buggy | `7df48bee88^1` |
| 修复提交 | `7df48bee88` |
| 测试 | `transport/TestInflightStreamClosing` |

## 症状

服务端删除一条仍在传输中的流时，客户端的 `RecvMsg` 一直等不到 `StreamError`，调用方挂死。

## 判定

测试内置 100ms 等待窗口，超时即 `Test timed out, expected a StreamError`：

```
transport_test.go:418: Test timed out, expected a StreamError
```

## 实测

| 侧 | iter1 | iter2 | iter3 | SUMMARY |
|---|---|---|---|---|
| buggy | FAIL | FAIL | FAIL | pass=0 fail=3 |
| fixed | PASS | PASS | PASS | pass=3 fail=0 |

## 证据

- `results/logs/grpc-1293/`
- `results/shots/grpc-1293_repro.png`
