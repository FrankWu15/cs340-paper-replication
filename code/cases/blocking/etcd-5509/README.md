# etcd#5509 — acquire 与 reconnect 的双锁顺序反转（ABBA）

## 元信息

| 项 | 值 |
|---|---|
| 论文 uid | `etcd#5509` |
| 行为分类 | blocking |
| 修复 commit | `1d8813052292e6053957fae01d080fde9717f3fc` |
| buggy 版本 | `1d88130522^` |
| 真实源文件 | `clientv3/remote_client.go`、`clientv3/client.go` |
| 论文集合 | 在 41 条内（`Reproduced?=1`），计入 Table 8 分母 |
| 运行环境 | Ubuntu 18.04 / Linux 4.15.0-213-generic / Go 1.10.8 linux/amd64 |

## 1 症状

`Get` 与连接重建同时发生时，客户端**永久挂住**：`Get` 不返回，重连也不完成，进程内两个 goroutine 互等，直到运行时打印 `fatal error: all goroutines are asleep - deadlock!`（退出码 2）。上游的复现用例就是 `TestKVGetErrConnClosed` 里"并发 `cli.Close()` 时 `kv.Get` 卡住"。

## 2 机理

两把锁、两条路径、相反顺序：

```
acquire():                 reconnect() -> retryConnection():
  client.mu.RLock()          r.mu.Lock()
  r.mu.Lock()                client.mu.Lock()      // 写锁
```

`client.mu` 是 `sync.RWMutex`，`retryConnection()` 取的是**写锁**，无法与 `acquire()` 已经持有的读锁共存。于是：

1. G1 在 `acquire()` 里持有 `client.mu.RLock`，要去拿 `r.mu`；
2. G2 在 `reconnect()` 里持有 `r.mu`，要去拿 `client.mu` 的写锁；
3. 两边互等，形成闭环。

`Acquire` 的读锁本应在 `release()` 里释放，但代码路径在拿 `r.mu` 之前就卡住，永远走不到释放。

## 3 修复

上游把 `acquire()` 里的两把锁**调换顺序**，与 `reconnect()` 统一成 `r.mu → client.mu`：

```go
func (r *remoteClient) acquire(ctx context.Context) error {
	for {
		r.mu.Lock()
		r.client.mu.RLock()
		closed := r.client.cancel == nil
		c := r.client.conn
		match := r.conn == c
		r.mu.Unlock()
		...
	}
}
```

顺序统一后不再成环：`acquire()` 在等 `r.mu` 时手里没有任何锁，`reconnect()` 总能走完。

## 4 判定口径

| 判定 | 条件 |
|---|---|
| DEADLOCK | 输出含 `all goroutines are asleep - deadlock!`，退出码 2 |
| CLEAN | 退出码 0，且 fixed 侧打印 `rounds=500 acquire_ok=500` |

ABBA 本身是概率性的，所以 **buggy 侧用两个握手点把交错固定下来**（`acqHeld`/`recHeld`），保证每次运行都成环，而不是靠撞运气；**fixed 侧去掉握手，改为 500 轮并发**，用"全部完成"证明不成环。

## 5 实测

| 侧 | 结果 | 证据 |
|---|---|---|
| buggy | **DEADLOCK** | `logs/buggy.log`：`fatal error: all goroutines are asleep - deadlock!`，一个 goroutine 停在 `sync.Mutex.Lock`（等 `r.mu`），另一个停在 `client.mu` 写锁路径，`exit=2` |
| fixed | **CLEAN** | `logs/fixed.log`：`rounds=500 acquire_ok=500 conn_changed=0` / `no deadlock detected`，`exit=0` |

## 6 怎么重跑

```bash
cd code/cases/blocking/etcd-5509
./run.sh
GO=/usr/local/go1.10.8/bin/go ./run.sh
```

产物同上：`logs/buggy.log`、`logs/fixed.log`、`logs/environment.txt`、`logs/verdict.txt`。

## 7 保真说明

- `results/real-source.txt` 导出了 `1d88130522^` 的 `clientv3/remote_client.go` 全文与 `clientv3/client.go` 中 `ActiveConnection`/`retryConnection` 片段，`acquire()` 的原始锁序可直接对照；
- 最小复现保留了 `client.mu`（RWMutex，写锁路径）与 `remoteClient.mu`（Mutex）这对真实锁，以及 `acquire`、`reconnect`、`retryConnection`、`ActiveConnection` 的真实调用链；
- 差异：把 grpc 连接换成 `int` 计数器，把 `reconnectWait` 的网络等待换成握手通道。锁的语义没有改，这正是缺陷所在。
