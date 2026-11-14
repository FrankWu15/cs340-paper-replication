# grpc#1459 —— client keepalive 唤醒令牌不复位，后续 RPC 死锁

| 项 | 内容 |
|---|---|
| 仓库 | google.golang.org/grpc |
| 类型 | 阻塞（deadlock） |
| buggy | `c29d6389^1`（2017-08-25 之前） |
| 修复提交 | `c29d6389` · transport: Fix deadlock in client keepalive. (#1460) |
| 补丁规模 | `transport/http2_client.go` +4 行 |
| 探针 | `probe/keepalive_awaken_probe_test.go`（`package grpc_test`，放仓库根目录） |

## 症状

连接空闲一段时间后，新的 RPC 永久不返回；`context` 的 deadline 也救不回来，进程只能被外部
超时杀掉。已建立的连接看起来是好的（TCP 没断、`ClientConn` 还是 READY）。

## 根因

`awakenKeepalive` 是容量 1 的"门铃"，语义上必须**在 keepalive 协程睡着时保持可写**：

```
newHTTP2Client:  t.awakenKeepalive <- struct{}{}      // 先塞满，平时不可写
keepalive():     <-t.awakenKeepalive                  // dormant 时把门铃清空（在持 t.mu 的情况下）
                 select { case <-t.awakenKeepalive: } // 等新流来按门铃
NewStream():     case t.awakenKeepalive <- struct{}{}: // 0→1 时按门铃，然后发 PING
```

buggy 版本按完门铃没有把令牌补回去，于是门铃状态变成"空"。等这一轮 PING 结束、连接再次空闲，
keepalive 协程进入 dormant 分支执行 `<-t.awakenKeepalive` 时会**永远阻塞，而且这时它手里还攥着 `t.mu`**。
之后任何 `NewStream` 都要先抢 `t.mu`，于是一起卡死。

修复就是那 4 行：按完门铃后再补一个令牌，让门铃重新变成不可写。

## 触发方式

1. `grpc.WithKeepaliveParams(keepalive.ClientParameters{Time: 100ms, Timeout: 100ms})`，把 keepalive 周期压到毫秒级；
2. 发一次 RPC，让 `activeStreams` 从 0 变 1，唤醒 keepalive；
3. 之后连续发 RPC：第 2 次还能过（此时 keepalive 还在等 PING 的 Timer），**第 3 次开始**卡在 `NewStream` 的 `t.mu.Lock`；
4. 探针一共发 4 次，每次间隔 700ms，不设看门狗——直接让 `go test -timeout` 把卡住的进程杀掉，栈就是证据。

## 判定

| 侧 | 期望 | 说明 |
|---|---|---|
| buggy | TIMEOUT | `go test` 30s 不返回，栈里有 `NewStream → sync.Mutex.Lock` 与 `keepalive` 的 `chan receive` |
| fixed | PASS | 4 次 RPC 全部返回 |

## 实测

| 侧 | iter1 | iter2 | iter3 | SUMMARY |
|---|---|---|---|---|
| buggy | TIMEOUT | TIMEOUT | TIMEOUT | pass=0 timeout=3 |
| fixed | PASS | PASS | PASS | pass=3 timeout=0 |

崩溃现场（`logs/grpc_buggy_last.log`）：

```
goroutine ... [semacquire]
sync.(*Mutex).Lock
google.golang.org/grpc/transport.(*http2Client).NewStream      transport/http2_client.go:389

goroutine 14 [chan receive]:
google.golang.org/grpc/transport.(*http2Client).keepalive      transport/http2_client.go:1308
```

两条栈指向同一把互斥锁，正是上面说的"keepalive 持锁阻塞、NewStream 抢锁"。

## 证据

- `logs/`：`summary.txt`、`env.txt`、两侧各 3 份原始输出 + `*_last.log`
- 重跑：`bash run.sh`
