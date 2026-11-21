# etcd#6937 — watchBroadcast 持写锁再取读锁，goroutine 自锁

## 元信息

| 项 | 值 |
|---|---|
| 论文 uid | `etcd#6937` |
| 行为分类 | blocking |
| 修复 commit | `91ff6f30b50a14158ec10cdd24836d775a336f52` |
| buggy 版本 | `91ff6f30b5^` |
| 真实源文件 | `proxy/grpcproxy/watch_broadcast.go` |
| 论文集合 | 在 41 条内（`Reproduced?=1`），计入 Table 8 分母 |
| 运行环境 | Ubuntu 18.04 / Linux 4.15.0-213-generic / Go 1.10.8 linux/amd64 |

## 1 症状

grpc-proxy 的 watch 广播在**第一次广播或删除 watcher 时直接卡死**，进程不再响应任何请求，也不报错。触发时不涉及外部服务：只要有一个 watcher，`bcast()` 进去就再也出不来。

## 2 机理

`watchBroadcast` 用一个 `sync.RWMutex` 保护 `receivers`。`bcast()` 与 `delete()` 都是整段持**写锁**，但函数体里又调用了 `size()` / `empty()`，而这两个方法自己会取**读锁**：

```go
func (wb *watchBroadcast) bcast(wr clientv3.WatchResponse) {
	wb.mu.Lock()
	defer wb.mu.Unlock()
	...
	if wb.size() > 0 {                 // size() 里 wb.mu.RLock()
		eventsCoalescing.Add(float64(wb.size() - 1))
	}
}

func (wb *watchBroadcast) size() int {
	wb.mu.RLock()
	defer wb.mu.RUnlock()
	return len(wb.receivers)
}
```

`sync.RWMutex` 不可重入：同一 goroutine 持有写锁时再取读锁会永久阻塞。此时进程里没有别的 goroutine 能推进，运行时判定全部睡眠，打印 `fatal error: all goroutines are asleep - deadlock!` 并以退出码 2 结束。

## 3 修复

上游把两处 `size()`/`empty()` 换成直接读 map 长度，不再加锁（`wb.mu` 已经持有）：

```go
if len(wb.receivers) > 0 {
	eventsCoalescing.Add(float64(len(wb.receivers) - 1))
}
```

`fixed/main.go` 只改这两处，其余与 buggy 完全一致。

## 4 判定口径

| 判定 | 条件 |
|---|---|
| DEADLOCK | 输出含 `all goroutines are asleep - deadlock!`，退出码 2 |
| CLEAN | 退出码 0，且打印 `bcast: done` / `delete: done` |

blocking 类按论文 §5.3 的口径只跑一次：这类阻塞是确定性触发的，重复运行不增加信息。

## 5 实测

| 侧 | 结果 | 证据 |
|---|---|---|
| buggy | **DEADLOCK** | `logs/buggy.log` 尾部 `fatal error: all goroutines are asleep - deadlock!`，栈顶为 `sync.(*RWMutex).RLock` ← `watchBroadcast.size` ← `watchBroadcast.bcast`，`exit=2` |
| fixed | **CLEAN** | `logs/fixed.log` 打印 `bcast: done, responses=1 coalesced=1` / `delete: done, receivers=1`，`exit=0` |

## 6 怎么重跑

```bash
cd code/cases/blocking/etcd-6937
./run.sh                 # 用 PATH 里的 go
GO=/usr/local/go1.10.8/bin/go ./run.sh   # 指定老工具链
```

产物：`logs/buggy.log`、`logs/fixed.log`、`logs/environment.txt`、`logs/verdict.txt`（形如 `buggy=DEADLOCK fixed=CLEAN`）。脚本退出码 0 表示对照成立。

## 7 保真说明

本目录是**最小复现**，不是完整 etcd 构建：

- `results/real-source.txt` 是从本地 etcd 克隆里 `git show 91ff6f30b5^:proxy/grpcproxy/watch_broadcast.go` 导出的真实文件；
- `buggy/main.go` 保留了真实代码的**方法集合、加锁位置与调用结构**（`bcast`/`add`/`delete`/`size`/`empty` 全部同名同序），只把 `clientv3.WatchResponse`、metrics、grpc 依赖替换成本地类型；
- 因此触发的是同一处缺陷，而非"看起来像"的等价物。取舍理由与 11-14 的 `etcd-6873` 一致。
