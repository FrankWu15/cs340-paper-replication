# grpc#1546 · 并发 WriteStatus 触发 send on closed channel

| 项 | 值 |
|---|---|
| 分类 | **non-blocking**（数据竞争 → panic） |
| 仓库 | `google.golang.org/grpc` |
| 论文编号 | grpc#1111（ASPLOS'19 数据表 BugID），上游为 PR #1546 |
| buggy 提交 | `cf79c849790fd644fab2ef0996e07c177f7b689c`（修复提交的第一父提交） |
| 修复提交 | `22c3f92f5faea8db492fb0f5ae4daf0d2752b19e` — *transport: fix racey send to writes channel in WriteStatus (#1546)* |
| 触发用例 | `TestHandlerTransport_HandleStreams_MultiWriteStatus`（`transport` 包，补丁自带） |
| 判定 | buggy **FAIL(panic) ×3** / fixed **PASS ×3** |
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

`WriteStatus` 在锁内只检查 `streamDone` 就释放锁，发送与 `close(ht.writes)` 都在锁外；
旧版把 `streamDone = true` 放在 `close` 之后、另一次加锁里完成，检查与置位不在同一临界区，
期间其他 goroutine 仍能通过检查。修复把置位提前到检查所在的临界区内。

`-count=1` 时两侧各 20 次全部通过（见 `logs/neg_count1.txt`），因此每轮用 `-count=200`
在同一进程内重复该测试。`200` 是本案例选定的重复预算，不代表每轮必中：本目录归档的三轮均命中，
崩溃出现在第 14、33、4 次重复；另有一次独立复测三轮中两轮命中（第 8、101 次），
一轮跑满 200 次未触发。这种波动是竞争窗口的固有特性，判定按轮统计，不按单次执行。
`p4_case.sh` 固定 `-count=1`，本案例因此单独驱动。

## 证据

- `logs/summary.txt`（每轮判定、退出码与 `=== RUN` 次数）、`logs/env.txt`
- `logs/grpc_{buggy,fixed}_iter{1,2,3}.log`、`*_last.log`
- `logs/neg_count1.txt`（`-count=1` 两侧各 20 次全部通过）
- `patches/1546.patch`（完整修复）、`patches/1546-test.patch`（仅测试文件）
- `env.txt` 记录两侧 `handler_server.go`、测试文件与 `go.mod`/`go.sum` 的 sha256

## 重跑

```bash
bash run.sh                # 3 轮 × 每轮 -count=200
bash run.sh 200 3 120      # count iters timeout
```

首次运行会按提交号把两份源码树下载到 `$HOME/grpc1546/{buggy,fixed}`，补测试补丁，
核对产品文件、测试文件与依赖文件的哈希后才开跑；目录内容与提交对不上会直接报错，
要重下加 `GRPC1546_REBUILD=1`。源码目录可用 `GRPC1546_BUGGY` / `GRPC1546_FIXED` 指定，
日志目录用 `GRPC1546_LOGDIR`。

退出码：`0` 对照成立，`2` buggy 未复现，`3` fixed 未全通过，`4` 源码/构建/环境问题。
