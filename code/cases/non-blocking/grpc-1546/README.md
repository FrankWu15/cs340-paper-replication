# grpc#1546 · 并发 WriteStatus 触发 send on closed channel

| 项 | 值 |
|---|---|
| 分类 | **non-blocking**（数据竞争 → panic） |
| 仓库 | `google.golang.org/grpc` |
| buggy 提交 | `cf79c849790fd644fab2ef0996e07c177f7b689c`（修复提交的第一父提交） |
| 修复提交 | `22c3f92f5faea8db492fb0f5ae4daf0d2752b19e` — *transport: fix racey send to writes channel in WriteStatus (#1546)* |
| 触发用例 | `TestHandlerTransport_HandleStreams_MultiWriteStatus`（`transport` 包，补丁自带） |
| 判定 | buggy **FAIL ×3（panic）** / fixed **PASS ×3** |
| 负责 | 许汝轩 1240011357 |

## 症状

同一条流的多个 goroutine 并发结束，`WriteStatus` 向已经关闭的 `writes` 通道发送函数：

```
panic: send on closed channel

goroutine 148 [running]:
google.golang.org/grpc/transport.(*serverHandlerTransport).do(...)
	transport/handler_server.go:170
```

进程被 panic 终止（`exit status 2`），但**不是卡死**，归 non-blocking。

## 判定口径

| 侧 | iter1 | iter2 | iter3 |
|---|---|---|---|
| buggy | FAIL（panic） | FAIL（panic） | FAIL（panic） |
| fixed | PASS | PASS | PASS |

`WriteStatus` 在锁内只检查 `streamDone` 就释放锁，发送、`close(ht.writes)`、置位分三步在锁外完成，
期间其他 goroutine 仍能通过检查。修复把 `streamDone = true` 移进同一临界区。

**每轮必须 `-count=200`**：竞争窗口很窄，两侧 `-count=1` 各跑 20 次全部通过，
单次重复的命中率不足 1%（观测到崩溃发生在第 3、6、116、128 次重复）。
`p4_case.sh` 固定 `-count=1`，本案例因此用独立驱动。

## 证据

- `logs/summary.txt`、`logs/env.txt`
- `logs/grpc_{buggy,fixed}_iter{1,2,3}.log`、`*_last.log`
- `patches/1546.patch`（完整修复）、`patches/1546-test.patch`（仅测试文件）

## 重跑

```bash
bash run.sh          # 3 轮 × 每轮 -count=200
```
