# case-01：boltdb 的 mmap 与并发只读事务复现

## 案例目标

`code/case-01/` 负责复现 boltdb 在数据库文件持续增长过程中，并发只读事务与写事务同时运行时暴露的 mmap 相关问题：数据库文件随写入不断扩增，写事务会触发 mmap 增长；同时 16 个只读协程不停开启只读事务，持有已有的页快照。程序用「是否在超时前跑完」作为判定信号。

## 目录结构

```
code/case-01/
├── experiments/
│   ├── mmap_repro.go            # 复现程序
│   ├── buggy-mmap-result.txt    # 有缺陷版本的一次运行输出（原始日志）
│   └── fixed-mmap-result.txt    # 修复版本的一次运行输出（原始日志）
└── README.md
```

## 复现程序

`experiments/mmap_repro.go` 单文件，用 boltdb 打开 `./mmap-repro.db`，启动并发负载：

| 参数 | 值 |
| --- | --- |
| 只读协程数 `readerCount` | 16 |
| 写入次数 `writeCount` | 1200 |
| 单次写入 value 大小 `valueSize` | 64 KB |
| 超时上限 `timeout` | 120 s |

- 只读侧：循环执行 `db.Begin(false)` → `Bucket.Get("key-00000000")` → `time.Sleep 2ms` → `tx.Rollback()`，直到写侧置位 `writeDone`。
- 写入侧：`db.Update` 里 `CreateBucketIfNotExists("data")` 后 `Put`，key 为 `key-%08d`，每 100 次打印一次数据库文件大小。
- 判定：`wg.Wait()` 在超时前完成则打印 `RESULT: COMPLETED` 并关闭数据库；超时则打印 `RESULT: TIMEOUT` 并 dump 全部 goroutine 栈后 `exit(2)`。

程序自己会删除并重建 `mmap-repro.db`，跑完不要提交这个 .db 文件。

## 运行方式

```bash
cd code/case-01/experiments
go mod init mmap-repro
go get github.com/boltdb/bolt
go run mmap_repro.go > my-run-result.txt 2>&1
```

程序依赖 `github.com/boltdb/bolt`，仓库里没有附带 `go.mod`，首次运行需按上面两行初始化模块。

## 运行结果（原始日志）

| 版本 | 结果 | 只读事务完成数 | 结束前数据库大小 |
| --- | --- | --- | --- |
| buggy（`buggy-mmap-result.txt`） | COMPLETED | 56009 | 96.26 MB |
| fixed（`fixed-mmap-result.txt`） | COMPLETED | 53493 | 95.63 MB |

两次运行都在 120 s 内正常结束，未触发 `RESULT: TIMEOUT` 分支，因此本次环境下的输出没有留下卡死现场的 goroutine 栈。两次的只读事务完成数相差约 2500 次（56009 vs 53493），但库文件增长的节奏基本一致。

## 说明

上述结论只覆盖这两份日志记录的单次运行结果；缺陷是否能在本机稳定复现、以及 reader 完成数的差异是否由修复引起，需要多次重复运行后再判断，不宜由单次日志直接下结论。
