# 4 Bug 复现（P4）

> 状态：未开始，6 条素材齐

## 4.1 汇总

从论文标记「已复现」的 41 条目标中完成 6 条，覆盖三种症状：

| 症状 | 代表 case | buggy 侧 | fixed 侧 |
|---|---|---|---|
| 死锁 | `grpc-793` | TIMEOUT ×3 | PASS ×3 |
| 调用方永久等待 | `grpc-1293`、`grpc-1424` | FAIL ×3 | PASS ×3 |
| panic / 数据竞争 | `grpc-1687`、`boltdb-7fb06fee`、`boltdb-341` | FAIL ×3 或失败率 80%+ | PASS ×3 或失败率 0~10% |

## 4.2 三个典型案例

正文各半页，其余条目进附录：

1. `grpc-793` —— 二次 `GracefulStop` 自我死锁，两个 goroutine 卡在同一把 mutex
2. `boltdb-7fb06fee` —— 事务共享 `meta` 导致撕裂，概率触发，用失败率说话
3. `grpc-1687` —— `send on closed channel`，必现，不需要放大窗口

## 4.3 附录

41 条全量明细表（`results/data/bug_status.tsv`，**待生成**），一列状态、一列原因。

## 4.4 必须写进去的两个坑

- boltdb#341 的官方测试无效（`TestDB.Close()` 劫持了真正的 `Close()`），必须用探针
- `go test -run` 空匹配仍输出 `ok`，判定必须区分 `NOTRUN`

这两条不是花絮，它们直接影响「复现成功」这个结论的可信度。
