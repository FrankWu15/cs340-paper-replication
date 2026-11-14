# Case 03 · beginTx 错误分支漏解锁导致的死锁

| 项 | 值 |
|---|---|
| 论文数据集 | `blocking-bugs/boltdb/defdb743cdca840890fea24c3111a7bffe5cc0a3.txt` |
| 分类 | blocking（死锁） |
| buggy 提交 | `01bc9be72f46f0f1978b1f1581440c399b3a7684`（2014-06） |
| 修复提交 | `defdb743cdca840890fea24c3111a7bffe5cc0a3`（"Fix deadlock on remmap."） |
| 检测手段 | Go 内置死锁检测器（`fatal error: all goroutines are asleep - deadlock!`） |

## 机理

buggy 版的 `beginTx()` 先拿 mmap 读锁、再拿 meta 锁；当数据库已关闭时走错误分支：

```go
func (db *DB) beginTx() (*Tx, error) {
	db.mmaplock.RLock()

	db.metalock.Lock()

	if !db.opened {
		db.mmaplock.RUnlock()
		return nil, ErrDatabaseNotOpen      // ← 漏了 db.metalock.Unlock()
	}
	...
}
```

`Close()` 之后 `db.opened == false`，第一次 `Begin(false)` 走进这个分支，
**`metalock` 被永久占住**。此后任何 `Begin` / `Update` / `View` 都会阻塞在
`metalock.Lock()` 上，整个数据库不可用。

修复把 `metalock` 提到最前，并在错误分支补上解锁：

```go
	db.metalock.Lock()
	db.mmaplock.RLock()

	if !db.opened {
		db.mmaplock.RUnlock()
		db.metalock.Unlock()                // ← 补上
		return nil, ErrDatabaseNotOpen
	}
```

## 复现方法

```bash
bash run.sh 03 buggy    # 预期：第二次 Begin 卡死，运行时判定 deadlock
bash run.sh 03 fixed    # 预期：两次 Begin 都正常返回 ErrDatabaseNotOpen
```

注意：**必须跑非 `-race` 版本**。`-race` 运行时会带后台线程，Go 的
"all goroutines are asleep" 判定不会触发，只能靠超时杀进程。

程序时序：Open → 建 bucket → `Close()` → `Begin(false)`（返回 ErrDatabaseNotOpen，
但锁已泄漏）→ 再 `Begin(false)`。

## 观测结果

buggy（`results/boltdb/b3_buggy_closed.log`）：

```
[4] 第 1 次 Begin(false) 返回: database not open  <-- 期望 ErrDatabaseNotOpen
[5] 第 2 次 Begin(false)，buggy 版本会卡死在这里 ...
fatal error: all goroutines are asleep - deadlock!

goroutine 1 [semacquire]:
sync.(*Mutex).Lock(0xc82008e110)
github.com/boltdb/bolt.(*DB).beginTx(0xc82008e000, ...)
	.../bolt/db.go:349 +0x68
github.com/boltdb/bolt.(*DB).Begin(0xc82008e000, ...)
	.../bolt/db.go:339 +0x60
```

fixed（`results/boltdb/b3_fixed_closed.log`）：

```
[6] 第 2 次 Begin(false) 返回: database not open (耗时 127ns)
结论: 未卡死
```

## 补充说明：`remap` 路径没触发

修复说明写的是 "Fix deadlock on remmap"，即 DB 增大触发 mmap 重映射时的死锁。
另外写了 `-mode remap` 压测（4 个读事务持续持有 `mmaplock.RLock`，写事务不断写入
256 KB 数据逼 DB 越过 mmap 阈值）：

```bash
bash run.sh 03 buggy -mode remap -secs 20
```

结果 8 秒 / 800+ 次写入都没有卡死（`results/boltdb/b3_buggy_remap.log`）。读代码确认：
这个快照里 `db.mmap()` 只取 `mmaplock`，写事务的 `metalock` 在 `beginRWTx` 返回前
就已释放，提交 / allocate 阶段并不持有它，因此"写事务持 metalock 等 mmaplock、
读事务持 mmaplock 等 metalock"的 ABBA 环不可能形成。

也就是说：同一个修复提交覆盖了多处问题，本快照上能确定性触发的是**错误分支漏解锁**
这一处。
