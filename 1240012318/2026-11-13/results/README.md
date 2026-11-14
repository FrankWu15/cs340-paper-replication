# results —— 本次复现的产出（3 条）

```
logs/<case>/
├── summary.txt            判定汇总（两侧每次一行 + SUMMARY）
├── env.txt                go version / uname / 参数 / 时间
├── grpc_buggy_iter{1,2,3}.log
├── grpc_fixed_iter{1,2,3}.log
└── grpc_{buggy,fixed}_last.log
data/grpc_repro_summary.csv   3 条成功复现目标的逐条对照表
```

## 例外：`logs/grpc-1850/`

这条按概率触发（16%~20%），3 次循环看不出来，所以结构不同：

```
logs/grpc-1850/
├── summary.txt            机理 + 判定口径修正 + 两次运行的结论
├── env.txt
├── iter3/                 上一轮的 3 次对照（两侧全 PASS），留作"少次循环看不出来"的对照
│   ├── summary_iter3.txt
│   └── grpc_{buggy,fixed}_iter{1,2,3}.log
└── loop50/                50 次循环
    ├── buggy_summary.txt  pass=42 deadline_hit=8 hit_rate=16%
    ├── fixed_summary.txt  pass=50 deadline_hit=0
    └── buggy_hit_iter{4,6,8,16,25,26,28,43}.log   8 份命中原始输出
```

命中日志的内容是 `--- FAIL ... DeadlineExceeded ... want code: ResourceExhausted`：
RPC 卡在写操作上直到测试自身的 10s deadline，而不是 `go test` 整体超时。

## 空目录

`shots/` 为空：本轮证据就是 `go test` 的原始输出，没有补终端截图。
