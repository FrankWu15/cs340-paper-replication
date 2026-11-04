# P4 · boltdb 两条目标 bug 复现

环境：Ubuntu 18.04.6 / **Go 1.10.8** / GOPATH 模式（无 `go.mod`）。论文研究期（2015-02~2018-05）对应 Go 1.4~1.10，且新工具链对老代码不兼容（见 §5）。

## 1. 结论

| bug               | buggy       | fixed      |
|-------------------|-------------|------------|
| `boltdb#341`      | `55af28c`   | `c69cb102` |
| `boltdb@7fb06fee` | `7fb06fee^` | `7fb06fee` |

- **`boltdb#341`**：buggy 侧 `Close()` 在 **0ms** 就返回，随后 `Commit` 经 `DB.page()` 拿到 nil → SIGSEGV（`db.go:603` → `tx.go:162`）；fixed 侧 `Close()` 阻塞 **159~168ms** 等事务结束，`Commit` 成功。
- **`boltdb@7fb06fee`**：三次 10 轮统计，buggy 侧失败率 **80%~100%**（`invalid page type: meta` panic 或断言失败），fixed 侧失败率 **0%~10%**。

两条均满足「buggy 触发 / fixed 不触发」，**2/2 复现成功**。

## 2. 方法

论文 §4 原文（`paper_text.txt:843-855`）：

> To reproduce a bug, we rolled the application back to the buggy version, built the buggy version, and ran the built program using the bug-triggering input described in the bug report. We leveraged the symptom mentioned in the bug report to decide whether we have successfully reproduced a bug. … Sometimes, we needed to run a buggy program a lot of times.

落地四步：**回滚**（`git checkout <fix>^`，merge 取 `^1`）→ **触发**（优先用补丁自带测试，无效则自写最小程序）→ **判定**（用 bug report 描述的症状，不用"测试是否通过"）→ **多次运行**（并发 bug 必须统计）。

## 3. boltdb#341（close-race）

`DB.Close()` 不与未完成的事务同步：`close()` 里 `munmap` 之后，事务 `Commit` 访问 `DB.page()` 得到 nil → SIGSEGV。修复 `c69cb102` 给 `Close()` 加了 `db.rwlock.Lock()` + `db.mmaplock.RLock()`。

**补丁自带的测试无效**——这是本条最关键的问题：

```go
db := NewTestDB()   // db 是 *TestDB，不是 *bolt.DB
db.Close()          // 调用的是 TestDB.Close() → MustCheck() → Update() 开写事务
                    // 卡在 rwlock 上，bolt.DB.Close() 一次都没执行到
```

包装类型的同名方法静默劫持了调用。改用独立探针后判定清晰：

| 版本             | `Close()` 行为            | 随后 `Commit()`                      |
|------------------|---------------------------|--------------------------------------|
| buggy `55af28c`  | 0ms 即返回，未等待        | SIGSEGV（`db.go:603` → `tx.go:162`） |
| fixed `c69cb102` | 阻塞 159~168ms 至事务结束 | 成功                                 |

## 4. boltdb@7fb06fee（parallel-tx）

读事务直接引用 `db.meta`（共享），写事务修改 `meta.txnid` 时发生竞争，并发读写会读到撕裂的页面。修复 `7fb06fee` 让 `Transaction.init` 复制 meta，每个事务持有独立副本。该 commit 的 Makefile 自己就写了 `go test -v -race -test.run=Parallel`，作者的复现方式就是跑 race detector。

| 版本                     | 第 1 次          | 第 2 次          | 第 3 次          |
|--------------------------|------------------|------------------|------------------|
| buggy `7fb06fee^` 通过数 | 0/10             | 0/10             | 2/10             |
| fixed `7fb06fee` 通过数  | 9/10             | 9/10             | 10/10            |
| buggy 失败构成           | 1 panic + 9 断言 | 2 panic + 8 断言 | 2 panic + 6 断言 |

**判据是两侧的相对差异，不是单侧绝对值。** 第 3 次 buggy 升到 2/10 通过、fixed 升到 10/10，但 80% vs 0% 仍不重叠。单跑一次有可能抽到 buggy 通过的那 20%——这正是论文强调 "run a buggy program a lot of times" 的原因。

该测试自身也不稳定：多个 reader goroutine 并发调 `t.FailNow()` 会产生 `testing.(*common).FailNow()` 的竞争（**与 bolt 无关**），且 `local := current` 只复制 slice header。所以固定用 10 次统计的失败构成判定，不取单次 PASS/FAIL。

## 5. 环境适配（老代码必须处理）

1. **`ExampleDB_Begin_ReadOnly has malformed example suffix`** —— Go 1.13+ 的 vet 收紧了 Example 命名检查。用 Go 1.10.8，或在 1.27 下加 `-vet=off`。
2. **`flag provided but not defined: -test.paniconexit0`** —— `quick_test.go` 在 `init()` 里调 `flag.Parse()`，早于 Go 1.13+ 的 `testing.Init()`。用 Go 1.10.8，或注释该行。
3. **Windows 上 `-race` 报 `0xc0000139`** —— 缺 CGO 原生工具链，必须在 Linux 上跑。

另外每次 checkout 后必须 `rm -rf $GOPATH/pkg`，否则外部测试包会链接到上一个版本的编译产物。

## 6. 对剩余 39 条的启示

1. **A 档 ≠ 能直接跑**：可行性表的分档要补一层"测试是否触及被修复的代码路径"的判断，先看包装类型的同名方法。
2. **race 报告要看栈帧归属**：报在 `_test.go` 里的竞争多半是测试自身缺陷，不能算 bug 复现。
3. **并发 bug 必须多次统计**：单次 PASS 没说服力，单次 FAIL 也可能来自测试缺陷。
4. **多补丁 bug 要整组回滚**（`etcd#4876` 有 4 个 commit）。

## 7. 证据与复跑

`results/shots/` 中 boltdb 相关截图取自真实终端会话：

| 文件                   | 内容                                                           |
|------------------------|----------------------------------------------------------------|
| `boltdb341_buggy.png`  | `55af28c` 侧探针：`VERDICT=BUG close_returned_early closeMs=0` |
| `boltdb341_fixed.png`  | `c69cb102` 侧探针：`VERDICT=OK close_waited closeMs=159`       |
| `boltdb7fb06_run4.png` | 第 4 轮并发测试：`invalid page type: meta` panic 现场          |

两张 #341 截图的提示符、`git checkout` 切换输出、`go run` 输出与 `tee` 落盘路径均完整可见，
可直接核对「切到 `55af28c` 得 BUG、切到 `c69cb102` 得 OK」这一对照关系。

原始日志在 `results/logs/`：`boltdb_341_buggy/fixed.log`（判定输出）、
`boltdb_341_sigsegv_evidence.log`（完整崩溃栈）、
`boltdb_7fb06_buggy_last.log`（panic 现场）。

```bash
bash code/repro/scripts/08_repro_boltdb.sh          # 默认 10 次统计
REPRO_ITERS=20 bash code/repro/scripts/08_repro_boltdb.sh
```

前置：`$GOPATH/src/github.com/boltdb/bolt`（带 `.git`）+ `github.com/stretchr/testify@v1.2.2`。脚本不硬编码绝对路径，`GOPATH` / `GO110` / `OUT` / `REPRO_ITERS` 均可环境变量覆盖。
