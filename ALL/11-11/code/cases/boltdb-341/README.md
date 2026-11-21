# boltdb#341 —— `Close()` 在写事务未结束时提前返回

| 项 | 内容 |
|---|---|
| 仓库 | github.com/boltdb/bolt |
| 类型 | 非阻塞（内存安全，确定性触发） |
| buggy | `55af28c` |
| 修复提交 | `c69cb102` |
| 触发方式 | 独立探针 `probe/main.go`，官方测试无效 |

## 症状

`DB.Close()` 不等待未提交的写事务直接返回，随后 `Commit` 访问已释放的 mmap，
触发 SIGSEGV（`db.go:603`，调用栈经 `tx.go:162`）。

## 为什么不能用官方测试

修复提交里的 `TestDB.Close()` 调用的是测试自己定义的同名方法，内部 `MustCheck()`
会开一个写事务并阻塞在 rwlock 上，**真正的 `bolt.DB.Close()` 从未被执行**，
所以无论 buggy 还是 fixed 都 PASS。这条坑是复现过程中最花时间的一个。

## 探针判定

探针开一个写事务后不提交，150ms 后检查 `Close()` 是否已返回：

| 侧 | 输出 | 含义 |
|---|---|---|
| buggy | `VERDICT=BUG close_returned_early closeMs=0` | 0ms 就返回，完全不等事务 |
| fixed | `VERDICT=OK close_waited closeMs=159` | 被挡到事务提交后才放行 |

`159 = 150（探针固定等待）+ 9（Commit 耗时）`，这个差值本身就是「确实等到了」的证据。

## 实测

| 侧 | commit | closeMs | 判定 |
|---|---|---|---|
| buggy | `55af28c` | 0 | BUG |
| fixed | `c69cb102` | 159 | OK |

探针在 buggy 分支故意不执行 `Commit`——SIGSEGV 是附加现象，不是判据，
要观察崩溃现场把 `probe/main.go` 里那行 `return` 去掉即可。

## 运行

```bash
bash code/cases/boltdb-341/run.sh
```

需要 Go 1.10.8 与 GOPATH 布局，脚本默认 `$HOME/gopath/src/github.com/boltdb/bolt`，
用 `P4_REPO` 覆盖。**每次 checkout 后必须清 `$GOPATH/pkg`**，否则会链接到上一版本的
编译产物，buggy 侧会跑出 fixed 的行为。

## 证据

- `results/logs/boltdb-341/`：`boltdb_341_buggy.log`、`boltdb_341_fixed.log`、
  `boltdb_341_sigsegv_evidence.log`（完整崩溃栈）
- `results/shots/boltdb-341_buggy.png`、`results/shots/boltdb-341_fixed.png`
