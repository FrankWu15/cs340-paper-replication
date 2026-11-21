# grpc#793 · 二次 GracefulStop 自我死锁

| 项 | 值 |
|---|---|
| 分类 | **blocking**（死锁） |
| 仓库 | `google.golang.org/grpc` |
| buggy 提交 | `5a547ed7^` |
| 修复提交 | `5a547ed72c09faf4050739d54caea1d51f4d276d` |
| 触发用例 | `TestServerGracefulStopIdempotent`（`test` 包，补丁自带） |
| 判定 | buggy **TIMEOUT ×3** / fixed **PASS ×3** |
| 负责 | 李振炜 1240012318 |

## 症状

连续两次调用 `Server.GracefulStop()` 时进程不再推进，`go test` 30s 超时。
buggy 侧栈上能看到 `Serve` 卡在 `server.go:318` 的 `sync.(*Mutex).Lock`：

```
goroutine 23 [semacquire]:
sync.(*Mutex).Lock(0xc4200c54f8)
google.golang.org/grpc.(*Server).Serve(...)  server.go:318
```

第二次 `GracefulStop` 在持有 `s.mu` 的情况下等待 `Serve` 退出，而 `Serve` 退出前
要先拿同一把 `s.mu` —— 自锁。修复提交把停止状态的判断与加锁顺序理顺，使
idempotent 调用直接返回。

## 判定口径

blocking 类：buggy 侧必须卡死（`test timed out` → TIMEOUT），fixed 侧必须干净通过。

| 侧 | iter1 | iter2 | iter3 |
|---|---|---|---|
| buggy | TIMEOUT | TIMEOUT | TIMEOUT |
| fixed | PASS | PASS | PASS |

## 证据

- `logs/summary.txt`：两侧逐次判定与 SUMMARY
- `logs/env.txt`：修复提交、包名、GOROOT、`go version`、内核
- `logs/grpc_{buggy,fixed}_iter{1,2,3}.log`、`*_last.log`：原始输出
- `shots/grpc793_repro.png`：终端截图

## 重跑

```bash
bash run.sh          # 3 次 × 30s 超时
P4_REPO=/path/to/grpc-go bash run.sh 5 60
```

依赖 `code/harness/p4_case.sh`：buggy 侧 checkout `fix^1` 后只打补丁里 `*_test.go`
的部分，非测试代码保持 buggy。
