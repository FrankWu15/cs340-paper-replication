# boltdb#341 · Close 不等待未完成的写事务

| 项 | 值 |
|---|---|
| 分类 | **non-blocking**（关闭时序竞争） |
| 仓库 | `github.com/boltdb/bolt` |
| buggy 提交 | `55af28c19cd84431e1f3c5b132a07c1deecff10b` |
| 修复提交 | `c69cb102`（merge PR #377），实际改动为 `e929eba`（"Wait for pending tx on close."） |
| 检测手段 | 时序观测 + 崩溃（SIGSEGV / panic） |
| 判定 | buggy **崩溃** / fixed **Close 阻塞到事务结束后正常提交** |
| 负责 | 李振炜 1240012318、许汝轩 1240011357（两人各自独立复现，本目录合并） |

## 症状

buggy 的 `Close()` 只拿 `metalock` 就往下走，而 `metalock` 只保护 meta 页、并不排斥
正在进行的事务：

```go
func (db *DB) Close() error {
	db.metalock.Lock()
	defer db.metalock.Unlock()
	return db.close()          // opened=false、freelist=nil、munmap、关文件
}
```

写事务还在跑，`Close()` 照样把 freelist 置空、把数据区 unmap、把 fd 关掉；写事务
随后 `Commit()` 访问这些结构就拿到失效状态。修复让 `Close()` 额外获取写锁与 mmap
读锁，等写事务结束。

**注意不是死锁**：没有人被永久阻塞，进程是在 `Commit` 里崩掉的，所以归 non-blocking。

## 判定口径

两位成员的现象一致，崩溃位置不同（buggy 侧两种都出现过）：

| 来源 | buggy | fixed |
|---|---|---|
| 李振炜（独立探针，Go 1.10.8） | `Close()` 0ms 返回，`Commit` SIGSEGV（`db.go:603` → `tx.go:162`） | `Close()` 阻塞 159~168ms，`Commit` 成功 |
| 许汝轩（`main.go`，Go 1.6.4） | `Close` 35.92µs 返回，随后 `Commit` panic（`bucket.go:692`，崩在 `Bytes()` 里） | `Close` 阻塞 55.24ms，`Commit` 成功 |

## 证据

| 来源 | 路径 |
|---|---|
| 李振炜 | `logs/boltdb_341_buggy.log`（`VERDICT=BUG close_returned_early closeMs=0`）、`logs/boltdb_341_fixed.log`、`logs/boltdb_341_sigsegv_evidence.log`、`shots/boltdb341_{buggy,fixed}.png` |
| 许汝轩 | `logs/b2_buggy.log`、`logs/b2_fixed.log`、`code/main.go`、`code/README-upstream.md` |
| 修复补丁 | `patches/02-close-race.patch` |

## 踩过的坑：补丁自带的测试是无效的

`TestDB.Close()` 里的 `db` 是 `*TestDB`（包装类型），调用的是 `TestDB.Close()` →
`MustCheck()` → 开一个写事务，卡在 `rwlock` 上；`bolt.DB.Close()` 一次都没被执行到。
同名方法静默劫持了调用。所以这条必须用独立探针判，不能用官方测试。

## 重跑

- 李振炜那套：`code/harness/08_repro_boltdb.sh`（Go 1.10.8 + GOPATH，探针写在 `$GOPATH/src/boltprobe`）
- 许汝轩那套：Go 1.6.4，`code/main.go` 直接 `go run`，两个版本的源码快照各放一个独立 GOPATH

细节见 `code/README-upstream.md` 与 `report/appendix/xu-1357-report.md`。
