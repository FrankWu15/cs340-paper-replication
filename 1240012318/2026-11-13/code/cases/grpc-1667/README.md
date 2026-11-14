# grpc#1667 —— `ccBalancerWrapper.subConns` 是一张没有同步的 map

| 项 | 内容 |
|---|---|
| 仓库 | google.golang.org/grpc |
| 类型 | 非阻塞（数据竞态，`-race` 可判） |
| buggy | `a62701e4^1`（2017-11-28 之前） |
| 修复提交 | `a62701e4` · Eliminate data race in ccBalancerWrapper (#1688) |
| 补丁规模 | `balancer_conn_wrappers.go` +7 行（新增 `ccb.mu sync.RWMutex`） |
| 探针 | `probe/balancer_subconns_map_probe_test.go`（`package grpc_test`） |

## 症状

`-race` 下报 `mapassign` / `mapaccess` 的数据竞态；不开 `-race` 时表现为偶发的
`fatal error: concurrent map writes` 或 `concurrent map iteration and map write`，直接杀进程。

## 根因

`ccBalancerWrapper.subConns` 这张表有三处访问，**一处都没加锁**（buggy）：

| 位置 | 操作 |
|---|---|
| `watcher()` 的 `case <-ccb.done:` 分支 | `for acbw := range ccb.subConns` —— 读 |
| `NewSubConn()` | `ccb.subConns[acbw] = struct{}{}` —— 写 |
| `RemoveSubConn()` | `delete(ccb.subConns, acbw)` —— 写 |

`NewSubConn`/`RemoveSubConn` 是 balancer 在自己 goroutine 里调的，`watcher` 是 gRPC 内部的
另一条 goroutine（`ClientConn` 关闭时走遍历分支）。两边没有任何同步，写-写、读-写全是竞态。

修复给 `ccBalancerWrapper` 加了 `mu sync.RWMutex`，三处分别用 `Lock`/`RLock` 包住。

## 触发方式

自写 balancer：

1. `HandleResolvedAddrs` 收到地址后先建 8 个 SubConn，把 map 撑起来；
2. 起 **4 条 goroutine** 同时对同一个 ClientConn 反复 `NewSubConn` + `RemoveSubConn` —— 并发写同一张 map；
3. 主 goroutine 等 500ms 后 `cc.Close()`，让 `watcher` 的关闭分支去 `range` 这张表；
4. 全程 `go test -race`。

关键是第 2 步用多条 goroutine：单条 goroutine 的读写是串行的，只有并发写才能稳定命中。

## 判定

| 侧 | 期望 |
|---|---|
| buggy | RACE（`WARNING: DATA RACE`，写点在 `balancer_conn_wrappers.go` 的 `ccb.subConns[...] = ...`） |
| fixed | PASS |

## 实测

| 侧 | iter1 | iter2 | iter3 | SUMMARY |
|---|---|---|---|---|
| buggy | RACE | RACE | RACE | pass=0 race=3 |
| fixed | PASS | PASS | PASS | pass=3 race=0 |

竞态栈（`results/logs/grpc-1667/grpc_buggy_iter1.log`）：

```
WARNING: DATA RACE
Write at 0x00c42008dc50 by goroutine 12:
  runtime.mapassign_fast64()
  google.golang.org/grpc.(*ccBalancerWrapper).NewSubConn      balancer_conn_wrappers.go:198
  google.golang.org/grpc_test.(*churnBalancer).churn()
```

## 备注

探针第一版把 `churnBuilder.lb` 写成普通字段、由 `Build()` 在 resolver goroutine 里赋值，
结果 `-race` 报的是**探针自己**的竞态（`Build()` 写 / 测试读）。改成加锁读之后才拿到目标栈。
写探针时值得先确认第一条 race 报的是不是被测代码。

## 证据

- `results/logs/grpc-1667/`：`summary.txt`、`env.txt`、两侧各 3 份原始输出 + `*_last.log`
- 重跑：`bash code/cases/grpc-1667/run.sh`
