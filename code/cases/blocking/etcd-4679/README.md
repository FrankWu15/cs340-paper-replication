# etcd#4679 — Close 持锁等待 watcher 退出（锁被自己人挡住）

## 元信息

| 项 | 值 |
|---|---|
| 论文 uid | `etcd#4679` |
| 行为分类 | blocking |
| 修复 commit | `d21d2e6624bc5400e52baa45804668f5f9b6a161` |
| buggy 版本 | `d21d2e6624^` |
| 真实源文件 | `clientv3/client.go` |
| 论文集合 | 在 41 条内（`Reproduced?=1`），计入 Table 8 分母 |
| 运行环境 | Ubuntu 18.04 / Linux 4.15.0-213-generic / Go 1.10.8 linux/amd64 |

## 1 症状

在**连接已经断开**的状态下调用 `client.Close()`，调用永不返回；`Watcher.Close()` 一直等着 watch goroutine 退出，而那个 goroutine 正在等 `Close()` 手里那把锁。进程内所有 goroutine 最终全部阻塞，运行时打印 `fatal error: all goroutines are asleep - deadlock!`。

## 2 机理

buggy 版本用 `defer c.mu.Unlock()` 把整段 `Close()` 包在临界区里，包括后面三个"关闭下游组件"的调用：

```go
func (c *Client) Close() error {
	c.mu.Lock()
	defer c.mu.Unlock()          // ← 一直到函数结束都持锁
	if c.cancel == nil {
		return nil
	}
	c.cancel()
	c.cancel = nil
	c.Watcher.Close()            // 等 watch goroutine 结束
	c.Lease.Close()
	return c.conn.Close()
}
```

watch goroutine 在退出路径上要读客户端状态（真实代码走 `ActiveConnection` / 重连记账），必须拿 `c.mu`：

```
Close: 持 c.mu  →  等 watcher 的 donec
watcher:        →  等 c.mu（在 donec 关闭之前）
```

这是"持锁做等待、被等待方又要这把锁"的典型形态，与 #6937 的自锁不同：这里是**跨 goroutine 的等待环**，且只在连接异常（`cancel` 已被消费、watcher 需要走清理路径）时才走到。

## 3 修复

上游删掉 `defer`，把 `c.mu.Unlock()` 提到三个 `Close()` 调用之前：

```go
	c.cancel()
	c.cancel = nil
	c.mu.Unlock()

	c.Watcher.Close()
	c.Lease.Close()
	return c.conn.Close()
```

锁只保护 `cancel` 字段的读写，不覆盖任何阻塞调用。

## 4 判定口径

| 判定 | 条件 |
|---|---|
| DEADLOCK | 输出含 `all goroutines are asleep - deadlock!`，退出码 2 |
| CLEAN | 退出码 0，且打印 `close ok` |

确定性触发：只要走同一路径，必然成环，因此按论文口径只跑一次。

## 5 实测

| 侧 | 结果 | 证据 |
|---|---|---|
| buggy | **DEADLOCK** | `logs/buggy.log`：先打印 `close: waiting for watcher to stop`，随后 `fatal error: all goroutines are asleep - deadlock!`；主 goroutine 停在 `watcher.Close` 的 `<-w.donec`，`exit=2` |
| fixed | **CLEAN** | `logs/fixed.log`：`close: waiting for watcher to stop` → `close ok`，`exit=0` |

## 6 怎么重跑

```bash
cd code/cases/blocking/etcd-4679
./run.sh
GO=/usr/local/go1.10.8/bin/go ./run.sh
```

## 7 保真说明

- `results/real-source.txt` 导出 `d21d2e6624^:clientv3/client.go` 的 `Close`/`Dial` 段，`defer c.mu.Unlock()` 的位置可直接对照；
- 最小复现保留 `client.mu` 的"整段持有 → 解锁 → 关闭下游"结构，以及 watcher 退出路径上取同一把锁的行为；
- 差异：`grpc.ClientConn`、`Lease`、`Watcher` 都是本地替身（只有 `Close` 与 `donec` 语义），但**持锁位置与等待关系与上游一致**。
