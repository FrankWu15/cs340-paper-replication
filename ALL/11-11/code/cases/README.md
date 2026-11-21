# cases —— 一条 bug 一个目录

每个目录只放**能重新触发这条 bug 的代码**，不含数据与日志。
证据（日志、截图）在 `results/logs/<case>/` 与 `results/shots/`，用同名目录对应。

## 统一模板

```
<case>/
├── README.md    症状 / 根因 / 触发方式 / 判定标准 / 实测结果
├── run.sh       一条命令跑完 buggy 与 fixed 两侧
└── probe/       仅当官方测试无效时需要（目前只有 boltdb-341）
```

`run.sh` 约定：第一个参数是重复次数（默认 3），第二个是单次超时秒数。
仓库路径用 `P4_REPO` 覆盖，默认取 `$HOME/gopath/src/<repo>`——复现必须在 GOPATH 布局下，
因为 2018 年的代码没有 go.mod。

## 状态

| case | 仓库 | 症状 | 类型 | 状态 | 证据 |
|---|---|---|---|---|---|
| `boltdb-341` | boltdb | `Close()` 提前返回，`Commit` SIGSEGV | 非阻塞 | 已复现 | 日志 + 2 张截图 |
| `boltdb-7fb06fee` | boltdb | 并发读写 meta 撕裂 | 非阻塞 | 已复现 | 日志 + 1 张截图 |
| `boltdb-392` | boltdb | mmap 竞态 | 非阻塞 | 有实现，待并入 | 在 `1240012684/` |
| `boltdb-194` | boltdb | `beginTx` 漏解锁 | 阻塞 | 待并入 | 在 `1240011357/` |
| `grpc-793` | grpc-go | 二次 `GracefulStop` 自我死锁 | 阻塞 | 已复现 | 日志 + 截图 |
| `grpc-1293` | grpc-go | 删除在途流不通知调用方 | 阻塞 | 已复现 | 日志 + 截图 |
| `grpc-1424` | grpc-go | `doneChan` 永不关闭 | 阻塞 | 已复现 | 日志 + 截图 |
| `grpc-1687` | grpc-go | `send on closed channel` | 非阻塞 | 已复现 | 日志 + 截图 |
| `moby-17176` | docker | devmapper 漏解锁 | 阻塞 | 待并入 | 在 `1240012557/` |

「待并入」的三个目录目前只有说明，代码与证据仍在原来的学号目录里，等对应同学确认后再搬。
