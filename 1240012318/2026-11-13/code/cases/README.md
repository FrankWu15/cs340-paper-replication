# cases —— 本次复现成功的 3 条 grpc-go

一条 bug 一个目录：`README.md`（症状/根因/触发/判定/实测）+ `run.sh`（一条命令跑完两侧）
+ `probe/`（B 档才需要，自写判定程序）。

| case | 修复提交 | 症状 | 分档 | 结果 |
|---|---|---|---|---|
| `grpc-1459` | `c29d6389` | keepalive 唤醒令牌不复位 → 后续 RPC 死锁 | B | 已复现（TIMEOUT 3/3） |
| `grpc-1667` | `a62701e4` | `ccBalancerWrapper.subConns` 无同步 map | B | 已复现（RACE 3/3） |
| `grpc-1850` | `484b3ebb` | 客户端发送配额泄漏 → 写大消息卡到 deadline | A | 已复现（50 次循环命中 16%~20%，fixed 0/50） |

`run.sh` 约定与全组一致：第一个参数是重复次数（默认 3），第二个是单次超时秒数；
仓库路径用 `P4_REPO` 覆盖，默认 `$HOME/gopath/src/google.golang.org/grpc`。

`grpc-1850` 额外有 `run_loop.sh`：这条是按概率触发的，3 次循环基本看不出来，
需要 `bash code/cases/grpc-1850/run_loop.sh 50` 才能稳定命中。

证据在 `results/logs/<case>/`，与这里的目录同名。
