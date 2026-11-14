# 2026-11-13 · grpc-go 剩余目标复现

这一批只做**复现产物**：把 `11-13/clear/` 里还没有的 grpc-go 目标补齐。
P0/P1/P2 的分析脚本与报告不再重复产出，所以 `code/analysis/`、`code/tools/`、`data/`、`docs/`、
`report/` 下面都是空目录（只留 `.gitkeep` 占位），保持与全组架构同名，方便后面直接并回去。

**本目录只保留复现成功的三条：`grpc-1459`、`grpc-1667`、`grpc-1850`。**
另外三条（`grpc-1662`、`grpc-639`、`grpc-1803`）本轮没有构造出触发条件，已移出本目录，
不在交付范围内。

## 1. 目标清单

`data/repro_targets.csv`（在 `11-13/clear/`）里 grpc-go 共 10 条，其中 4 条已有复现：
`grpc#793`、`#1293`、`#1424`、`#1687`。本次从剩下的 6 条里拿下 3 条：

| case | 类型 | 修复提交 | 测试来源 | 分档 |
|---|---|---|---|---|
| `grpc-1850` | 阻塞 | `484b3ebb` | 补丁自带 `TestClientDoesntDeadlockWhileWritingErrornousLargeMessages` | A |
| `grpc-1459` | 阻塞 | `c29d6389` | 无，需自写探针 | B |
| `grpc-1667` | 非阻塞（数据竞态） | `a62701e4` | 无，需自写探针 | B |

## 2. 环境

复现不在本机跑，在课程用的 Linux 虚拟机上（`11-13/clear` 里那 4 条 grpc 也是这台机器上做的）：

| 项 | 值 |
|---|---|
| 主机 | `li@192.168.47.128` |
| 系统 | Linux 4.15.0-213-generic（Ubuntu 18.04），4 核 |
| Go | `/usr/local/go1.10.8`，`GO111MODULE=off` |
| 仓库布局 | `$GOPATH/src/google.golang.org/grpc`（2018 年的代码没有 go.mod） |
| 依赖 | `golang.org/x/net`、`x/text`、`github.com/golang/protobuf`、`glog` 已在 GOPATH 里 |

## 3. 方法

两套驱动，都在 `code/harness/`：

| 脚本 | 用于 | 做法 |
|---|---|---|
| `p4_case.sh` | A 档，补丁自带测试 | buggy 侧 checkout `fix^1` 后只把补丁里 `*_test.go` 的部分打上去，非测试代码保持 buggy |
| `p4_probe.sh` | B 档，自写探针 | 两侧都注入同一份 `probe/*_test.go`，只换被测源码；支持 `-race` |

判定口径（与已有 4 条一致）：

- 输出含 `WARNING: DATA RACE`（或 `fatal error: concurrent map ...`）→ **RACE**，竞态类 bug 已触发
- 输出含 `test timed out` → **TIMEOUT**，阻塞类 bug 已触发
- `P4_DEADLINE_HIT=1` 时，输出含 `DeadlineExceeded` → **DEADLINE**，RPC 卡到测试自身 deadline（也属于触发）
- `ok` 且出现过 `=== RUN` → **PASS**；`FAIL` → **FAIL**；`no tests to run` → **NOTRUN**（结果无效）

三条都按「buggy 必现/高频，fixed 干净」对照：buggy 侧必须出现 RACE/TIMEOUT/DEADLINE，
fixed 侧必须全 PASS，否则视为未复现。`grpc-1459`、`grpc-1667` 跑 3 次即稳定；
`grpc-1850` 按概率泄漏，3 次看不出来，要用 `run_loop.sh` 循环 50 次。

## 4. 结果

| case | buggy | fixed | 结论 | 证据 |
|---|---|---|---|---|
| `grpc-1459` | TIMEOUT ×3 | PASS ×3 | **已复现** | `results/logs/grpc-1459/` |
| `grpc-1667` | RACE ×3 | PASS ×3 | **已复现** | `results/logs/grpc-1667/` |
| `grpc-1850` | **DEADLINE 8/50（另轮 10/50）** | PASS 50/50 | **已复现** | `results/logs/grpc-1850/loop50/` |

`grpc-1850` 这条早前被误判成"未触发"，本轮纠正：它不是触发不了，而是**按概率触发**（16%~20%），
且命中时的表现是测试内 RPC 卡到 10s deadline 返回 `DeadlineExceeded`，而不是 `go test` 整体超时。

## 5. 三条复现的关键证据

`grpc-1459`：buggy 侧第 3 次 RPC 起永久挂起，栈上能同时看到两侧——

```
goroutine  ...  [semacquire]
sync.(*Mutex).Lock
google.golang.org/grpc/transport.(*http2Client).NewStream      http2_client.go:389

goroutine 14  [chan receive]
google.golang.org/grpc/transport.(*http2Client).keepalive      http2_client.go:1308
```

keepalive 协程在**持着 t.mu** 时阻塞在 `<-t.awakenKeepalive`，后续 `NewStream` 全部卡在同一把锁上。

`grpc-1667`：`-race` 报的第一个写点就在目标位置——

```
Write at ... by goroutine 12:
  runtime.mapassign_fast64()
  google.golang.org/grpc.(*ccBalancerWrapper).NewSubConn       balancer_conn_wrappers.go:198
```

`ccb.subConns` 的读写都没加锁；fixed 提交（`a62701e4`）补上了 `ccb.mu`，同样的操作序列 3/3 干净通过。

`grpc-1850`：buggy 侧 50 次循环里 8 次把期望的 `ResourceExhausted` 变成了 `DeadlineExceeded`——

```
--- FAIL: TestClientDoesntDeadlockWhileWritingErrornousLargeMessages (10.05s)
    end2end_test.go:6035: TestService/UnaryCall(_,_) = _.
        rpc error: code = DeadlineExceeded desc = context deadline exceeded,
        want code: ResourceExhausted        ← 这里 ×10，10 条 goroutine 全部卡到 deadline
```

`Write()` 里第三处配额申请失败时吞掉了已借的 `tq`：

```go
ltq, _, err := t.localSendQuota.get(size, s.waiters)
if err != nil {
    return err                    // buggy：tq 没还回 t.sendQuotaPool
}
```

泄漏 16KB/次，攒够 64KB（`defaultWindowSize`）后这条连接上的写就永久卡在
`t.sendQuotaPool.get`。fixed 侧 50/50 全 PASS，从未出现。

## 6. 目录

```
.
├── code/
│   ├── harness/        p4_case.sh（官方测试）、p4_probe.sh（自写探针）、p4_deps.sh
│   └── cases/          一条 bug 一个目录：README.md + run.sh + probe/
├── results/
│   ├── logs/<case>/    summary.txt、env.txt、两侧各 3 份原始输出
│   │                   （grpc-1850 例外：iter3/ 为旧的 3 次对照，loop50/ 为 50 次循环与命中日志）
│   └── data/          逐条对照表 grpc_repro_summary.csv
├── data/              空（本次不产出解析数据）
├── docs/              空
└── report/            空
```

并回全组仓库时，`code/cases/grpc-*`、`results/logs/grpc-*` 可以按同名目录直接复制，
`code/harness/p4_probe.sh` 是新增文件，`p4_case.sh`/`p4_deps.sh` 与 `11-13/clear/` 里的版本一致。

## 7. 怎么重跑

```bash
# 在 Linux 上，先把仓库放到 GOPATH
export GOPATH=$HOME/gopath GO111MODULE=off GOROOT=/usr/local/go1.10.8
export PATH=$GOROOT/bin:$PATH
git clone https://github.com/grpc/grpc-go $GOPATH/src/google.golang.org/grpc

bash code/cases/grpc-1459/run.sh            # 3 次 × 30s 超时
bash code/cases/grpc-1667/run.sh
bash code/cases/grpc-1850/run_loop.sh 50    # 这条按概率触发，要走 50 次循环
```

`run.sh` 的 `P4_REPO` 可覆盖仓库路径，第一个参数是重复次数，第二个是单次超时秒数。
