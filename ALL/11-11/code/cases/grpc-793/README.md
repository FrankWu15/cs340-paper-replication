# grpc#793 —— 二次 GracefulStop 自我死锁

| 项 | 内容 |
|---|---|
| 仓库 | google.golang.org/grpc |
| 类型 | 阻塞（deadlock） |
| buggy | `5a547ed72c^1` |
| 修复提交 | `5a547ed72c`（merge commit，取第一父） |
| 测试 | `test/TestServerGracefulStopIdempotent` |

## 症状

第一次 `GracefulStop()` 返回后再次调用，进程永久挂起，只能被外部超时杀掉。

## 根因

`GracefulStop` 抢 `s.mu` 之后进入等待，而正在退出路径上的 `serve` 协程也持有/等待同一把
锁，两边互相等待。崩溃现场两个 goroutine 停在同一个 mutex 地址上：

```
goroutine A: sync.(*Mutex).Lock  ← Server.GracefulStop → server.go:801
goroutine B: sync.(*Mutex).Lock  ← server.go:318
```

## 判定

`go test` 30 秒内不返回 → TIMEOUT，即视为触发。fixed 侧应当正常 PASS。

## 实测

| 侧 | iter1 | iter2 | iter3 | SUMMARY |
|---|---|---|---|---|
| buggy | TIMEOUT | TIMEOUT | TIMEOUT | pass=0 timeout=3 |
| fixed | PASS | PASS | PASS | pass=3 timeout=0 |

`notrun=0 error=0`，且两侧均打印「测试补丁已应用」，排除空匹配造成的假通过。

## 证据

- `results/logs/grpc-793/`：`summary.txt`、`env.txt`、两侧各 4 份原始输出
- `results/shots/grpc-793_repro.png`
