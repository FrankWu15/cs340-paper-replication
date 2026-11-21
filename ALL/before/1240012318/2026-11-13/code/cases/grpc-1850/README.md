# grpc#1850 —— 客户端发送配额泄漏，写大消息卡到 deadline（已复现）

| 项 | 内容 |
|---|---|
| 仓库 | google.golang.org/grpc |
| 类型 | 阻塞（RPC 卡在写操作上） |
| buggy | `484b3ebb^1`（2018-02-13 之前） |
| 修复提交 | `484b3ebb` · transport: fix race causing flow control discrepancy when sending messages over server limit (#1859) |
| 补丁规模 | `transport/http2_client.go` +2、`transport/http2_server.go` +2、`test/end2end_test.go` +44 |
| 分档 | A（补丁自带 `TestClientDoesntDeadlockWhileWritingErrornousLargeMessages`） |
| 结论 | **已复现**：buggy 侧两轮各 50 次，命中 8 次 / 10 次（16%、20%）；fixed 侧 50/50 全 PASS |

## 缺陷本身

`transport/http2_client.go` 的 `Write()` 在一个循环里连续申请三种发送配额：

```go
streamQuota, _, err = s.sendQuotaPool.get(math.MaxInt32, s.waiters)  // 流窗口
if err != nil { return err }

tq, _, err := t.sendQuotaPool.get(size, s.waiters)                   // 连接窗口
if err != nil { return err }

ltq, _, err := t.localSendQuota.get(size, s.waiters)                 // 本地软额度
if err != nil {
    return err                                                       // ← buggy：吞掉 tq
}
```

`localSendQuota` 是 **连接级共享**的 128KB 软额度（`defaultLocalSendQuota = 128 * 1024`），
只在 `dataFrame` 真正写出后由回调 `f()` 归还。当它见底时 `get` 会阻塞，而此时每个等待中的
`Write` 都已经把 `tq` 借到手了。若此刻流被 RST 或被 context 取消，这些 `Write` 从第三处
`return err` 退出，**已借的连接级配额没有归还**。

一次泄漏最多 16KB（`http2MaxFrameLen`）。泄漏累积到超过连接窗口（`defaultWindowSize = 65535`）
之后，这条连接上所有 `Write` 都会永久停在 `t.sendQuotaPool.get`，RPC 不再返回。

修复就是补一行 `t.sendQuotaPool.add(tq)`（服务端侧是同一个 bug 的镜像）。

## 为什么 3 次循环看不出、50 次才看得出来

这条 bug 不是"必然死锁"，而是**按时序概率泄漏**。要泄漏必须同时满足：

1. loopyWriter 的入队速度持续快于出队速度，把 128KB 本地软额度吃干净；
2. 此时有 `Write` 正堆在 `localSendQuota.get` 上并且已经持有 `tq`；
3. 这些流在等待期间被 RST 或 context 取消。

单轮官方测试 0.22s 就跑完 1000 次 RPC，环回上三种配额都在快速往返，撞上第 1 条的窗口很窄。
上一轮只跑 3 次（补跑 10 次、`-race` 5 次）全是 PASS，由此误判成"环回太快、触发不了"。

循环 50 次后稳定命中：

| 轮次 | 侧 | 结果 |
|---|---|---|
| 第 1 轮 50 次 | buggy | PASS 40 / **DEADLINE 10** |
| 第 1 轮 50 次 | fixed | PASS 50 |
| 第 2 轮 50 次（归档） | buggy | PASS 42 / **DEADLINE 8** |
| 第 2 轮 50 次（归档） | fixed | PASS 50 |

## 判定口径的修正（上一轮的误判点）

上一轮的判定只看 `go test` 的整体超时：

```
输出含 "test timed out" → TIMEOUT   （已触发）
以 ok 开头              → PASS
以 FAIL 开头            → FAIL      （被当成噪声）
```

但官方测试内部给每条 RPC 设了 10s deadline。RPC 卡在写操作上时，先到期的是这个 deadline，
日志长这样：

```
--- FAIL: TestClientDoesntDeadlockWhileWritingErrornousLargeMessages (10.05s)
    end2end_test.go:6035: TestService/UnaryCall(_,_) = _.
        rpc error: code = DeadlineExceeded desc = context deadline exceeded,
        want code: ResourceExhausted
```

10 条 goroutine 全部拿到 `DeadlineExceeded` 而不是期望的 `ResourceExhausted` —— 这正是
"写不出去、RPC 卡住"的直接证据，只是它被归到了 OTHER 里。

现在 `p4_case.sh` 增加了 `P4_DEADLINE_HIT=1` 开关，把 `DeadlineExceeded` 判为 `DEADLINE`（命中）。
默认关闭，避免影响其它 case 的既有结论。

## 怎么跑

```bash
# 50 次循环（推荐，命中率 16%~20%）
bash code/cases/grpc-1850/run_loop.sh 50

# 单次 3 轮对照（看两侧基线，通常全 PASS，可能看不到 bug）
bash code/cases/grpc-1850/run.sh 3
```

仓库路径用 `P4_REPO` 覆盖，默认 `$HOME/gopath/src/google.golang.org/grpc`。

脚本本身在虚拟机上验证过一轮 10 次：buggy `pass=9 deadline=1`，fixed `pass=10 deadline=0`。

两个容易踩的点（都已处理）：
- 官方测试的 `-only_env` 是测试包自己的 flag，必须在 `-args` 之后传。脚本通过
  `P4_EXTRA_ARGS="-args -only_env=tcp-clear"` 交给 `p4_case.sh`，否则测试会去跑
  `tcp-tls` 那几个坏环境，两侧都会显示 TIMEOUT，看起来像"复现了"但其实是环境问题。
- 命中时是 `FAIL + DeadlineExceeded`，不是 `test timed out`，所以要看 `P4_DEADLINE_HIT=1`
  打开后的 `DEADLINE` 计数。

## 关于 TLS / 其它环境

这台机器上 `tcp-tls`、`no-balancer` 两个环境会卡在 `Dial`（`WithBlock` 无限重试），
`tcp-clear-round-robin`、`handler` 直接 panic，所以测试统一 `-args -only_env=tcp-clear`。
只影响环境覆盖面，与这条 bug 的触发无关。

## 证据

- `results/logs/grpc-1850/summary.txt` — 两次运行的总述与机理
- `results/logs/grpc-1850/loop50/buggy_summary.txt` — 50 次逐行判定（pass=42 deadline_hit=8）
- `results/logs/grpc-1850/loop50/fixed_summary.txt` — 50 次全 PASS
- `results/logs/grpc-1850/loop50/buggy_hit_iter{4,6,8,16,25,26,28,43}.log` — 8 份命中原始输出
- `results/logs/grpc-1850/iter3/` — 上一轮 3 次对照（全 PASS），留作"少次循环看不出来"的对照
