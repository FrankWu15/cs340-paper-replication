# boltdb@7fb06fee · 读事务共享 meta 页指针

| 项 | 值 |
|---|---|
| 分类 | **non-blocking**（数据竞争，表现为 panic / 断言失败） |
| 仓库 | `github.com/boltdb/bolt` |
| buggy 提交 | `7fb06fee^` |
| 修复提交 | `7fb06fee` |
| 触发用例 | `TestParallelTransactions`（该 commit 的 Makefile 自带 `go test -v -race -test.run=Parallel`） |
| 判定 | buggy **失败率 80%~100%** / fixed **失败率 0%~10%**（各 10 次 × 3 轮） |
| 负责 | 李振炜 1240012318 |

## 症状

读事务直接引用 `db.meta`（共享），写事务修改 `meta.txnid` 时发生竞争，并发读会读到
撕裂的页面，表现为 `invalid page type: meta` panic 或断言失败：

```
github.com/boltdb/bolt.(*Cursor).search(...)   cursor.go:118
github.com/boltdb/bolt.(*Transaction).Get(...)
github.com/boltdb/bolt.TestParallelTransactions.func1...
exit status 2
FAIL	github.com/boltdb/bolt	1.279s
```

修复让 `Transaction.init` 复制一份 meta，每个事务持有独立副本。**不是死锁**：进程
总是跑完并退出，只是中间崩了，归 non-blocking。

## 判定口径：看两侧的相对差异，不看单次结果

并发 bug 单跑一次会抽到偶然通过的那一侧，所以固定用 10 次统计的失败构成：

| 轮次 | buggy 通过数 | fixed 通过数 |
|---|---|---|
| 第 1 次 | 0/10 | 9/10 |
| 第 2 次 | 0/10 | 9/10 |
| 第 3 次 | 2/10 | 10/10 |

buggy 失败构成：panic 1~2 次 + 断言失败 6~9 次。80% vs 0% 两段不重叠，判定成立。

另有一处**与 bolt 无关**的干扰：测试本身不稳，多个 reader goroutine 并发调
`t.FailNow()` 会在 `testing.(*common).FailNow()` 上产生竞争，且 `local := current`
只复制了 slice header。所以不取单次 PASS/FAIL 作判据。

## 证据

- `logs/boltdb_7fb06_buggy.log`：buggy 侧 panic 栈
- `logs/boltdb_7fb06_buggy_last.log`、`logs/boltdb_7fb06_fixed_last.log`：两侧最后一次完整输出
- `shots/boltdb7fb06_run4.png`：终端截图

## 重跑

Go 1.10.8 + GOPATH 模式：

```bash
cd $GOPATH/src/github.com/boltdb/bolt
go test -v -run=Parallel -count=1        # 或 -race
```

完整的三轮统计脚本见 `code/harness/08_repro_boltdb.sh`。
