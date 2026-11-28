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
| `-race` 补测（2026-11-28） | `logs/vm-1128/`（`SUMMARY.md`、`boltdb341.csv`、`boltdb341C.csv`、18 个运行日志）、`scripts/run_341_race.sh`、`scripts/run_341_race_C.sh` |
| 修复补丁 | `patches/02-close-race.patch` |

## 踩过的坑：补丁自带的测试是无效的

`TestDB.Close()` 里的 `db` 是 `*TestDB`（包装类型），调用的是 `TestDB.Close()` →
`MustCheck()` → 开一个写事务，卡在 `rwlock` 上；`bolt.DB.Close()` 一次都没被执行到。
同名方法静默劫持了调用。所以这条必须用独立探针判，不能用官方测试。

## `-race` 实测（2026-11-28 · VM，给 Table 12 补证据）

三套探针 × 两侧 × 3 轮 = 18 次运行，**0 条 `WARNING: DATA RACE`**（go1.10.8，buggy `55af28c` / fixed `c69cb102`）。

| 探针 | buggy | fixed |
|---|---|---|
| A 原样（不 Commit） | `VERDICT=BUG close_returned_early closeMs=0` ×3 | `VERDICT=OK close_waited closeMs=160` ×3 |
| B 并发 Put + Close | `puts≈97–100 万`，**不崩** ×3 | `puts≈109–136 万` ×3 |
| C Close 后继续 Commit | **SIGSEGV ×3** | `COMMIT_OK` + `CLOSE_DONE` ×3 |

- **探针 B 是必要的反例**："并发"不等于"触雷"——bolt 的 `Put` 只写事务内存里的 node，`Commit` 才落 mmap；
- **探针 C 才是真路径**：崩溃栈 `Tx.Commit → Bucket.spill → Cursor.search → Bucket.pageNode`（`bucket.go:692`）；
- **`-race` 看不见它**：这是对象生命周期 / `munmap` 问题，不在 TSan 的定义域，而且进程先 SIGSEGV，来不及出报告。

**结论：Table 12 记「实测、未检出」（0 / 9 轮）**；本 case 的复现凭据是"Close 提前返回 / Commit SIGSEGV"，与检测器无关。

证据在 `logs/vm-1128/`（`SUMMARY.md`、两份 CSV、18 个日志），探针与驱动脚本在 `scripts/`。

## 重跑

- 李振炜那套：`code/harness/08_repro_boltdb.sh`（Go 1.10.8 + GOPATH，探针写在 `$GOPATH/src/boltprobe`）
- 许汝轩那套：Go 1.6.4，`code/main.go` 直接 `go run`，两个版本的源码快照各放一个独立 GOPATH

细节见 `code/README-upstream.md` 与 `report/appendix/xu-1357-report.md`。
