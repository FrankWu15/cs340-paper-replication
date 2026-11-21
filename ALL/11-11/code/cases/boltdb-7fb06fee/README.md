# boltdb@7fb06fee —— 并发读写导致 meta 撕裂

| 项 | 内容 |
|---|---|
| 仓库 | github.com/boltdb/bolt |
| 类型 | 非阻塞（数据竞争，概率触发） |
| buggy | `7fb06fee^` |
| 修复提交 | `7fb06fee` |
| 触发方式 | `go test -race -count=1 -run Parallel` |

## 症状

多事务并发时，读路径拿到的是共享的 `meta` 结构，写路径同时在修改它，
出现 `DATA RACE` 报告、`panic: invalid page type: meta`，或功能断言失败。

## 根因

`Transaction.init` 直接引用全局 `db.meta`；修复改成每个事务持有一份 `meta` 副本。

## 判定

`-run Parallel` 是整包正则匹配，不是单条测试。判定看 10 轮里的失败比例：

| 侧 | 失败率 |
|---|---|
| buggy | 80%~100% |
| fixed | 0%~10% |

概率型 bug 不能只看单次结果。早前只跑 3 次时 buggy 曾出现 2/10 通过，
据此把结论写成「恒为 0 通过」是错的，现在是区间口径。

## 运行

```bash
bash code/cases/boltdb-7fb06fee/run.sh 10   # 10 轮
```

脚本实际调用 `code/harness/08_repro_boltdb.sh`，会同时跑 341 与 7fb06fee 两侧。

## 证据

- `results/logs/boltdb-7fb06fee/`：`boltdb_7fb06_buggy.log`、`_buggy_last.log`（panic 现场）、
  `_fixed_last.log`
- `results/shots/boltdb-7fb06fee_run4.png`
