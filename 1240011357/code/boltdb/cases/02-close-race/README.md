# Case 02 · Close 不等待未完成的写事务

| 项 | 值 |
|---|---|
| 论文数据集 | `non-blocking-bugs/boltdb/c69cb102ce8f7609b57f75d0ccb10862167001e7.txt` |
| 分类 | non-blocking（数据竞争 / 关闭时序） |
| buggy 提交 | `55af28c19cd84431e1f3c5b132a07c1deecff10b`（2015-05） |
| 修复提交 | `c69cb102`（merge PR #377），实际改动在 `e929eba`（"Wait for pending tx on close."） |
| 检测手段 | 直接观察 `Close()` 与写事务提交的时序 + 崩溃 |

## 机理

buggy 版的 `Close()` 只拿 `metalock` 就往下走：

```go
func (db *DB) Close() error {
	db.metalock.Lock()
	defer db.metalock.Unlock()
	return db.close()          // opened=false、freelist=nil、munmap、关文件
}
```

`metalock` 只保护 meta 页，并不排斥正在进行的事务。于是只要还有写事务没提交，
`Close()` 也会照样把 `freelist` 置空、把数据区 unmap、把文件描述符关掉。
写事务随后 `Commit()` 时去访问这些结构，就拿到已失效的状态。

修复让 `Close()` 额外获取写锁与 mmap 读锁：

```go
	db.rwlock.Lock()          // 与写事务互斥，等写事务结束
	defer db.rwlock.Unlock()

	db.metalock.Lock()
	defer db.metalock.Unlock()

	db.mmaplock.RLock()       // 等正在进行的 remap 结束
	defer db.mmaplock.RUnlock()
```

## 复现方法

```bash
bash run.sh 02 buggy    # 预期：Close 立刻返回，随后 Commit 崩溃
bash run.sh 02 fixed    # 预期：Close 阻塞到事务提交完成
```

程序（`main.go`）的时序：

1. 打开写事务，写入 k1，**不提交**
2. 另一个 goroutine 调用 `db.Close()`，记录耗时
3. 50 ms 后检查 Close 是否已经返回
4. 继续用这个写事务写入 k2 并 `Commit()`

## 观测结果

buggy（`results/boltdb/b2_buggy.log`）：

```
[3] 写事务已打开并写入 k1（尚未提交）
[4] Close 在写事务未提交时就返回了，耗时 35.92µs  <-- buggy 行为
[5] 写事务继续写入并提交 ...
panic: runtime error: invalid memory address or nil pointer dereference
github.com/boltdb/bolt.(*Bucket).pageNode(...)
	.../bolt/bucket.go:692
github.com/boltdb/bolt.(*Tx).Commit(...)
	.../bolt/tx.go:151
```

fixed（`results/boltdb/b2_fixed.log`）：

```
[4] Close 正在等待写事务结束  <-- fixed 行为
[5] 写事务继续写入并提交 ...
    Commit 成功
[6] Close 最终耗时 55.242242ms
结论: 未崩溃
```

## 补充说明

修复里的 `mmaplock` 用的是 `RLock`，所以它只挡"正在进行的 remap"，**不会**等读事务。
实测把复现程序改成"读事务保持打开 + Close"时，修复版同样会崩 —— 这是该修复的
覆盖边界，不是复现失败。真正的互斥点是与写事务共享的 `rwlock`。
