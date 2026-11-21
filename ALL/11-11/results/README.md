# results —— 产出与证据

与 `code/cases/` 用同一套名字，`code/cases/grpc-793` 的证据就在 `logs/grpc-793/`、
`shots/grpc-793_repro.png`。

```
results/
├── data/    统计表：静态统计、论文对照、41 条状态（部分待生成）
├── logs/    原始运行日志，一条 bug 一个目录
└── shots/   终端截图
```

## logs 的目录约定

| case | 文件 | 说明 |
|---|---|---|
| `boltdb-341` | `boltdb_341_buggy.log` / `_fixed.log` | 探针判定输出 |
| | `boltdb_341_sigsegv_evidence.log` | buggy 侧完整崩溃栈 |
| `boltdb-7fb06fee` | `boltdb_7fb06_buggy.log` / `_fixed_last.log` | 10 轮统计 |
| | `boltdb_7fb06_buggy_last.log` | panic 现场 |
| `grpc-*` | `env.txt` | 环境快照：commit、Go 版本、内核 |
| | `summary.txt` | 五态判定汇总 `pass/fail/timeout/notrun/error` |
| | `grpc_{buggy,fixed}_iter{1,2,3}.log` | 逐次原始输出 |
| | `grpc_{buggy,fixed}_last.log` | 最后一次完整栈 |

## 判定口径

`p4_case.sh` 把每次运行归入五种状态，报告里只引用 `summary.txt` 那一行：

| 状态 | 条件 |
|---|---|
| PASS | 输出以 `ok` 开头 |
| FAIL | 输出以 `FAIL` 开头 |
| TIMEOUT | 含 `test timed out` 或外层超时 |
| NOTRUN | 含 `no tests to run` —— 参数没匹配上，**不是有效结果** |
| ERROR | 编译失败等其它情况 |

`notrun>0` 或 `error>0` 时该轮结果作废。`go test` 在空匹配时仍打印 `ok`，
不区分 NOTRUN 会把「测试根本没跑」误判成「通过」。

## shots

| 文件 | 内容 |
|---|---|
| `boltdb-341_buggy.png` | buggy 侧 `VERDICT=BUG closeMs=0` |
| `boltdb-341_fixed.png` | fixed 侧 `VERDICT=OK closeMs=159` |
| `boltdb-7fb06fee_run4.png` | 第 4 轮 `DATA RACE` 与断言失败 |
| `grpc-793_repro.png` | 两侧各 3 轮，buggy 全 TIMEOUT |
| `grpc-1293_repro.png` | 两侧各 3 轮，buggy 全 FAIL |
| `grpc-1424_repro.png` | 同上 |
| `grpc-1687_repro.png` | 同上，含 panic 栈 |

## data 待补

`results/data/` 目前为空目录，下面三张表还没生成：

- `02_static.tsv` —— P2 逐仓库统计（数据在 `make static` 的输出里，尚未汇总成一张表）
- `numbers.tsv` —— 论文数字 vs 我们数字 vs 偏差
- `bug_status.tsv` —— 41 条：已复现 / 未尝试 / 不可跑 + 原因
