# grpc#1687 · 重复 WriteStatus 触发 send on closed channel

| 项 | 值 |
|---|---|
| 分类 | **non-blocking**（数据竞争 → panic） |
| 仓库 | `google.golang.org/grpc` |
| buggy 提交 | `c6b46087^` |
| 修复提交 | `c6b46087ab923e9f453ec433f99174cdd45b9b89` |
| 触发用例 | `TestHandlerTransport_HandleStreams_WriteStatusWrite`（`transport` 包，补丁自带） |
| 判定 | buggy **FAIL ×3（panic）** / fixed **PASS ×3** |
| 负责 | 李振炜 1240012318 |

## 症状

handler transport 在流已写结束后再次写 status，向已关闭的 channel 发送：

```
panic: send on closed channel

goroutine 9 [running]:
google.golang.org/grpc/transport.(*serverHandlerTransport).do(...)
	transport/handler_server.go:170
```

进程被 panic 终止（`exit status 2`），但**不是卡死**——程序自己跑到了终点才崩，
所以归 non-blocking。修复提交在写 status 前判断流状态，避免重复写。

## 判定口径

| 侧 | iter1 | iter2 | iter3 |
|---|---|---|---|
| buggy | FAIL（panic） | FAIL | FAIL |
| fixed | PASS | PASS | PASS |

注意包目录是 `transport`，不是 `test`。填错包目录时 `go test -run` 仍会输出 `ok`，
但那是「没匹配到任何测试」的假通过，`p4_case.sh` 会把它单列为 `NOTRUN`。

## 证据

- `logs/summary.txt`、`logs/env.txt`
- `logs/grpc_{buggy,fixed}_iter{1,2,3}.log`、`*_last.log`
- `shots/grpc1687_repro.png`

## 重跑

```bash
bash run.sh          # 3 次 × 60s 超时
```
