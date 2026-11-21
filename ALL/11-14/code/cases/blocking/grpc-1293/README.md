# grpc#1293 · 删除在途流不通知对端，调用方空等

| 项 | 值 |
|---|---|
| 分类 | **blocking**（等待不到终止信号） |
| 仓库 | `google.golang.org/grpc` |
| buggy 提交 | `7df48bee^` |
| 修复提交 | `7df48bee8829276b13ef52bff4e1c47b9d55cd7d` |
| 触发用例 | `TestInflightStreamClosing`（`transport` 包，补丁自带） |
| 判定 | buggy **FAIL ×3** / fixed **PASS ×3** |
| 负责 | 李振炜 1240012318 |

## 症状

流被删除时不通知等待方，`RecvMsg` 拿不到任何 `StreamError`，一直等到测试自己的
5s 超时：

```
--- FAIL: TestInflightStreamClosing (5.00s)
	transport_test.go:418: Test timed out, expected a StreamError.
```

修复提交在删除在途流时补上了对等待方的通知，使其立即收到 `StreamError` 返回。

## 判定口径

这条的表现是「等不到该来的错误」而不是进程整体挂死，所以判据取 FAIL
（测试内部超时断言），不是 `go test` 的 TIMEOUT。

| 侧 | iter1 | iter2 | iter3 |
|---|---|---|---|
| buggy | FAIL | FAIL | FAIL |
| fixed | PASS | PASS | PASS |

## 证据

- `logs/summary.txt`、`logs/env.txt`
- `logs/grpc_{buggy,fixed}_iter{1,2,3}.log`、`*_last.log`
- `shots/grpc1293_repro.png`

## 重跑

```bash
bash run.sh          # 3 次 × 60s 超时
```

注意包目录是 `transport`，不是 `test`。
