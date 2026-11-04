# P4 复现报告：boltdb 两条目标 bug

复现日期：2026-11-04
执行环境：Ubuntu 18.04.6 LTS（VMware，4 核 / 7GB），Go 1.10.8，GOPATH 模式
脚本：`repro/scripts/08_repro_boltdb.sh`

## 0. 结论

| bug | fix commit | 判定 | buggy 侧症状 | fixed 侧 |
|---|---|---|---|---|
| `boltdb#341` | `c69cb102` | **复现成功** | `Close()` 0ms 提前返回；随后 `tx.Commit()` SIGSEGV | `Close()` 阻塞 159ms 直到事务结束 |
| `boltdb@7fb06fee` | `7fb06fee` | **复现成功** | 10 次中 0 次通过（1 次 `invalid page type: meta` panic，9 次断言失败） | 10 次中 9 次通过，0 次 panic |

两条都满足「buggy 触发、fixed 不触发」的对照要求，2/2。

## 1. 方法与判定依据

论文 §4 的方法原文（`paper_text.txt:843-855`）：

> To reproduce a bug, we rolled the application back to the buggy version,
> built the buggy version, and ran the built program using the bug-triggering
> input described in the bug report. We leveraged the symptom mentioned in
> the bug report to decide whether we have successfully reproduced a bug.
> … Sometimes, we needed to run a buggy program a lot of times.

对应落地：

1. **回滚**：`git checkout <fix>^`（merge commit 取 `^1`）
2. **触发输入**：优先用补丁自带测试；测试无效时自写最小程序（仍以 bug report 描述的场景为准）
3. **症状判定**：用 bug report 描述的症状，不用「测试是否通过」这一间接指标
4. **多次运行**：并发 bug 必须统计，不取单次结果

环境选择 Go 1.10.8 而非新版本，原因是论文研究期（2015-02 ~ 2018-05）对应 Go 1.4~1.10，
且新版本工具链对老代码有两处不兼容（见 §4）。

## 2. boltdb#341（close-race）

### 2.1 bug 本体

```go
// buggy (55af28c) db.go
func (db *DB) Close() error {
	db.metalock.Lock()
	defer db.metalock.Unlock()
	return db.close()      // → munmap()，直接解除内存映射
}
```

`Close()` 不与未结束的事务同步。`munmap()` 之后，仍在进行的事务访问 `DB.page()`
拿到 nil 指针：

```
panic: runtime error: invalid memory address or nil pointer dereference
[signal SIGSEGV: segmentation violation code=0x1 addr=0x0]
  github.com/boltdb/bolt.(*DB).page(...)   db.go:603
  github.com/boltdb/bolt.(*Tx).Commit(...) tx.go:162
```

修复 `c69cb102` 给 `Close()` 补了三把锁：

```go
db.rwlock.Lock()        // 等待写事务结束
defer db.rwlock.Unlock()
db.metalock.Lock()
defer db.metalock.Unlock()
db.mmaplock.RLock()     // 防止与 mmap 重映射冲突
defer db.mmaplock.RUnlock()
```

### 2.2 关键问题：补丁自带的测试无效

补丁附带 `TestDB_Close_PendingTx_RW/RO`，但它在 buggy 和 fixed 上**都通过**，
没有区分度。原因有两层：

1. `db` 是 `*TestDB` 而非 `*bolt.DB`，`db.Close()` 调的是包装方法：

```go
func (db *TestDB) Close() {
	if *statsFlag { db.PrintStats() }
	db.MustCheck()              // ← 内部执行 db.Update(...)，开一个写事务
	defer os.Remove(db.Path())
	db.DB.Close()               // ← 真正的 Close 在这里，前面已经阻塞住了
}
```

`MustCheck()` 的写事务要拿 `rwlock`，而测试主 goroutine 已持有一个写事务，
于是 `TestDB.Close()` 卡在 `Update()` 上——**`bolt.DB.Close()` 一次都没被执行到**。
实测该测试里 `Close` 耗时与测试的 `Sleep` 时长同步变化（sleep 100ms → 109ms，
sleep 400ms → 410ms），证明它只是在等锁。

2. 即使绕过包装，测试的 RO 分支断言也不成立：修复版 `Close()` 用的是
`mmaplock.RLock()`，而 RO 事务同样持 `mmaplock.RLock()`，读锁互不排斥，
RO 事务本来就不会阻止 `Close()`。原作者把 `db.Begin(true)` 写死（`writable`
参数未使用），可能正是绕过了这个分支。

### 2.3 改用独立探针

绕开 `TestDB`，直接对 `*bolt.DB` 触发：

```go
db, _ := bolt.Open(path, 0666, nil)
tx, _ := db.Begin(true)              // 开一个写事务，不提交
go func() { db.Close(); close(done) }()
time.Sleep(150 * time.Millisecond)
select {
case <-done:  fmt.Println("VERDICT=BUG close_returned_early")  // 事务未结束时已关闭
default:      /* 正常：Close 被挡住 */
}
```

结果：

```
buggy  55af28c  → VERDICT=BUG close_returned_early closeMs=0
fixed  c69cb102 → VERDICT=OK  close_waited        closeMs=159
```

**判定**：`Close()` 在事务未结束时返回（0ms）即触发 bug。

## 3. boltdb@7fb06fee（parallel-tx）

> 注意：该条在 artifact 中 `bug_id` 为空，`uid` 为 `boltdb@7fb06fee`（2014 年提交，
> 尚未关联 GitHub issue 号），不是数据缺失。

### 3.1 bug 本体

```go
// buggy: 读事务直接引用 db 的共享 meta
func (t *Transaction) init(db *DB) {
	t.db = db
	t.meta = db.meta()          // ← 共享指针
	...
}
```

写事务递增 `meta.txnid` 时，读事务正在读同一块内存，导致元数据撕裂
（页面类型字段被读到中间状态）。

修复改为复制：

```go
t.meta = &meta{}
db.meta().copy(t.meta)          // 每个事务持有独立副本
```

### 3.2 触发与统计

该 commit 的 Makefile 自己就加了这一步，说明作者的复现方式就是跑 race detector：

```make
@go test -v -race -test.run=Parallel
```

按此执行 `go test -race -run Parallel`，10 次统计：

| 版本 | PASS | panic(`invalid page type`) | 其他 FAIL | 失败率 |
|---|---|---|---|---|
| buggy `7fb06fee^` | 0/10 | 1 | 9 | **100%** |
| fixed `7fb06fee` | 9/10 | 0 | 1 | 10% |

buggy 侧的典型崩溃：

```
panic: assertion failed: invalid page type: meta
  github.com/boltdb/bolt.(*Cursor).search(...)  cursor.go:89
  github.com/boltdb/bolt.(*Transaction).Get(...) transaction.go:85
```

### 3.3 该测试自身不稳定，不能用单次结果判定

fixed 版本 10 次中仍有 1 次失败。原因是测试代码本身有两个缺陷：

1. 多个 reader goroutine 并发调用 `t.FailNow()`，race detector 会报告
   `testing.(*common).FailNow()` 的竞争——**这个报告与 bolt 无关**，
   buggy 和 fixed 上内容完全相同，不能作为判据。
2. `local := current` 只是复制 slice header，底层数组与写者共享，
   会让断言因测试自身的数据竞争而失败。

因此判定改为「统计 10 次的失败构成」，而不是「单次 PASS/FAIL」。这也是论文
"run a buggy program a lot of times" 的含义。

## 4. 环境适配（对老代码必须处理）

| 现象 | 原因 | 处理 |
|---|---|---|
| `ExampleDB_Begin_ReadOnly has malformed example suffix` | Go 1.13+ 的 vet 收紧 Example 命名检查 | 用 Go 1.10.8；或在 1.27 下加 `-vet=off` |
| `flag provided but not defined: -test.paniconexit0` | `quick_test.go` 在 `init()` 里调 `flag.Parse()`，早于 Go 1.13+ 的 `testing.Init()` | 用 Go 1.10.8；或注释该行 |
| Windows 上 `-race` 报 `exit status 0xc0000139` | 缺 CGO/原生工具链 | 在 Linux 上跑 |

最终统一在 Linux + Go 1.10.8 + GOPATH 下执行，三项问题都不出现。

## 5. 对剩余 39 条的启示

1. **「A 档 = 有现成测试」不等于「可以直接跑出结果」。** boltdb#341 就是 A 档，
   但测试完全无效，实际是按 B 档方式自写探针才复现。可行性表的分档需要补一层
   「测试是否触及被修复的代码路径」的判断。
2. **先确认测试调用的是被测函数。** 包装类型的同名方法（`TestDB.Close`）会静默劫持调用。
3. **race detector 的报告要看栈帧归属。** 报在 `_test.go` 里的竞争多半是测试自身缺陷，
   不能算 bug 复现。
4. **并发 bug 必须多次统计。** 单次 PASS 没有说服力，单次 FAIL 也可能来自测试缺陷。
5. **多补丁 bug 要整组回滚**（见 `bug_table_audit.md` 关于 `etcd#4876`）。

## 6. 复现步骤

```bash
# 依赖：Ubuntu 18.04 + Go 1.10.8 + boltdb 仓库置于 $GOPATH/src/github.com/boltdb/bolt
#   以及 github.com/stretchr/testify@v1.2.2
GOPATH=$HOME/gopath bash repro/scripts/08_repro_boltdb.sh

# 可调迭代次数（默认 10）
REPRO_ITERS=20 GOPATH=$HOME/gopath bash repro/scripts/08_repro_boltdb.sh
```

脚本不硬编码绝对路径：`GOPATH` / `GO110` / `OUT` 均可用环境变量覆盖。

## 7. 复跑稳定性

完整脚本于 2026-11-04 独立执行 2 次，结论一致（2/2 复现）。

| 指标 | 第 1 次 | 第 2 次 | 是否稳定 |
|---|---|---|---|
| #341 buggy `closeMs` | 0 | 0 | ✅ |
| #341 fixed `closeMs` | 159 | 160 | ✅ |
| 7fb06fee buggy 通过数 | 0/10 | 0/10 | ✅ |
| 7fb06fee fixed 通过数 | 9/10 | 9/10 | ✅ |
| 7fb06fee buggy 失败构成 | 1 panic + 9 断言 | 2 panic + 8 断言 | ⚠️ 波动 |

**判据用的是「通过与不通过」，不是「哪种失败」**——失败构成会随时序变化，
但 buggy 恒为 0 通过、fixed 恒为 9/10 通过，这个分离度足够。

#341 的 `closeMs` 差 1ms 属于调度抖动，量级无意义（0 vs ~160 是「不等」与
「等到事务结束」的定性差异）。

附加证据（`04-p4-boltdb/probe_341_evidence.go` 生成）：

```
BUGGY  55af28c:  [2] db.Close() 返回 err=<nil> 耗时=0ms
                [3] 150ms 时 Close 已返回 → 未等待未完成事务（bug 症状）
                [4] 现在提交事务 ... panic: invalid memory address
                    [signal SIGSEGV: addr=0x0]
                    bolt.(*DB).page(...)         db.go:603
                    bolt.(*Tx).Commit(...)       tx.go:162

FIXED  c69cb102: [3] 150ms 时 Close 仍在阻塞 → 已与事务同步（fix 行为）
                [5] Commit 成功
                [2] db.Close() 返回 耗时=160ms
```
