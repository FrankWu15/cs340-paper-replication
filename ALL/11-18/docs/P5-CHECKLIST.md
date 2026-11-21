# P5 检测器评测 · 待检测清单

> 对应论文 Table 8（§5.3 内置死锁检测器）与 Table 12（§6.3 `-race` 检出率）。
> 本文件只回答两个问题：**要检测哪些 bug**、**每条检测什么**。
> 骨架 CSV 见 `results/data/p5_checklist.csv`（19 行，字段已按行填好，空列待跑）。
> 文中 `code/cases/...`、`code/harness/...` 路径均相对 `ALL/11-14`（已复现的 19 条都在那里，本批 11-18 只有 etcd 三条）。

---

## 0. 两个检测器，各只检测一件事

| 检测器 | 论文位置 | 检测什么 | 判据 | 论文预期 |
|---|---|---|---|---|
| 内置 deadlock detector | Table 8 | 进程是否进入"所有 goroutine 都睡死、且无 timer / netpoll 能再唤醒" | stderr 含 `fatal error: all goroutines are asleep - deadlock!` | 2/21 |
| `-race`（TSan） | Table 12 | 是否存在 data race（happens-before 违例） | stderr 含 `WARNING: DATA RACE`，栈落在 bug 附近 | 10/20 |

两者都是 Go 工具链自带能力，不是我们自加的：前者是 `runtime.checkdead()`，无需任何编译参数；后者是 `go build -race`。

---

## 1. 判定必须分四类，不能只分"检出 / 未检出"

这是 P5 最容易做错的地方。实测输出有三种"没报 deadlock"的样子，含义完全不同：

| 观测 | 分类 | 计入 | 说明 |
|---|---|---|---|
| `fatal error: all goroutines are asleep - deadlock!`，exit 2 | **DETECTED** | 分子 | 唯一算检出的形态 |
| 挂到外部 timeout、进程未退出、也没有上面那句话 | **SILENT_HANG** | 分母 | 还有 goroutine 在跑（timer / netpoll / 后台 worker），`checkdead()` 不满足条件 |
| 正常报错 / 断言失败 / panic / SIGSEGV 后退出 | **OTHER_FAIL** | 分母 | bug 触发了，但不是死锁形态；对 detector 而言是未检出 |
| 正常退出、bug 根本没触发 | **INVALID** | 不计 | 试验无效，必须重跑 |

`-race` 侧同理：`WARNING: DATA RACE` 才算检出；`FAIL`（断言失败）、`panic: send on closed channel`、时序断言被拖慢导致的失败都是 OTHER_FAIL，**不能进分子**。之前 `TestDB_Open_InitialMmapSize` 在 `-race` 下必失败就是这类污染。

---

## 2. 为什么 real-repo 类几乎抓不到：timer 只是第一层，更硬的是"全体睡死"

### 2.1 timer 抑制是真实机制

`runtime.checkdead()` 的判定条件是"**没有可运行的 goroutine，且 timers 队列为空、netpoller 无就绪事件**"。而 `go test -timeout Ns` 正是靠一个 pending timer 实现的——只要这个 timer 还挂着，`checkdead()` 就认为"进程还可能被唤醒"，**不会报 deadlock**，进程会一直挂到 timer 到期，然后由 testing 框架打印 `panic: test timed out after Ns`。

这条不是推论，写 case 的人当时就绕开了它，并在源码注释里写明：

- `code/cases/blocking/etcd-6873-double-lock/cmd/repro/main.go`：
  > *"we deliberately do NOT use a `time.After()` watchdog here. A pending timer keeps a goroutine runnable, which would suppress Go's 'all goroutines are asleep' deadlock detector."*
- `code/cases/blocking/cockroachdb-1cc69980/cmd/buggy/main.go`：
  > *"By default no watchdog is used, so the exit-2 comes straight from the Go runtime's deadlock detector … Pass `-watchdog` to add an 8s fallback that force-exits 2 if the native detector were somehow suppressed (e.g. by a pending timer)."*

### 2.2 但实测证明：去掉 timer 之后，grpc 仍然一条都抓不到

2026-11-18 在虚拟机上做了对照：`grpc-793` 用 `-test.timeout 0` 裸跑测试二进制（外部 `timeout` 兜底）；`grpc-1459` 额外把探针里的 `context.WithTimeout(10s)` 换成 `context.Background()`，把 Go 层的 timer 全清干净。

| case | 死锁是否成立 | goroutine 数 | 检测器 |
|---|---|---|---|
| grpc-793 | **成立**：`GracefulStop`(server.go:801) 与 `Serve`(server.go:318) 卡在同一把 `Mutex` | 4 | 25s 无报告（SILENT_HANG） |
| grpc-1459 | **成立**：`grpc.invoke` 卡在 `Mutex.Lock` | 12 | 20s 无报告（SILENT_HANG） |

793 只剩 4 个 goroutine 依然不报，因为剩下那些处在 `chan receive` / `IO wait` / `select` 上——runtime 认为"还可能被唤醒"，加上监听 socket 的 netpoll waiter，条件永远凑不齐。

### 2.3 所以真正的解释是结构性的

`minimal` 复现体能 20/20 稳定拿到 `exit=2`，是因为它**故意只留抢锁的两个 goroutine**，其余全砍；真实 server 程序（grpc/etcd/k8s）自带监听 socket、transport 管理协程、keepalive ticker，想让"全体 goroutine 睡死"几乎不可能。

这就是论文 Table 8 只有 2/21 的机制解释——**不是检测器弱，是判定条件要求整个进程只剩死锁的 goroutine**。报告里应这样写，而不是写成"工具检出率低"。

**操作结论**：Table 8 必须按 `kind` 分两行报（`minimal` 5/5、`real-repo` 1/6），不能合成 6/13 去跟论文 2/21 比。

---

## 3. 要检测哪些：13 个 blocking 点

按 `repro_summary.csv` 实有的 13 行（11 个目录，其中 `etcd-6873-double-lock` 与 `kubernetes-62464-20697` 各含两个 bug 点）。

**kind 列是本次新增的关键区分**（按"构建时是否链接真实仓库源码"划分，不是按"跑得多不多"）：
- `real-repo` = 编译产物里确实含该仓库的源码（官方测试、`third_party/` 快照、或自写 main 链接真库）。检出率可与论文对话。
- `minimal` = 用 stdlib 手写复刻 bug 的逻辑，不 import 原仓库。它被检出只证明"我们的复现体确实死锁"，**不能**用来论证"Go 能抓到该真实 bug"。两类必须分开报，否则会被问穿。

核对结果：13 条 blocking 里 `real-repo` 7 条（`boltdb-392` 走 `third_party/bolt` 真实 v1.3.1、`boltdb-begin-lock-leak`、grpc 五条），`minimal` 6 条（cockroachdb、etcd-6873 ×2、k8s ×2、moby）。

| # | case | bug 点 | kind | Go | 触发命令 | 现状（2026-11-18 实测） |
|---|---|---|---|---|---|---|
| 1 | `boltdb-392` | boltdb#392 | real-repo | 1.26.8 | `./bin/repro -mode=buggy` | ✅ DETECTED 10/10 |
| 2 | `boltdb-begin-lock-leak` | `defdb743c` | real-repo | 1.6.4 | `GOPATH=<gp> go run code/main.go` | ⬜ 未按 detector 口径统计 |
| 3 | `cockroachdb-1cc69980` | `1cc69980` | minimal | 1.26.8 | `./bin/buggy` | ✅ DETECTED 20/20（rc=2） |
| 4 | `etcd-6873-double-lock` | etcd#6873（`7618fdd`） | minimal | 1.26.8 | `./bin/repro -bug=etcd6873` | ✅ DETECTED 20/20 |
| 5 | `etcd-6873-double-lock` | double-lock（`ae062a0`） | minimal | 1.26.8 | `./bin/repro -bug=doublelock` | ✅ DETECTED 20/20 |
| 6 | `grpc-793` | grpc#793 | real-repo | 1.10.8 | `./t.bin -test.timeout 0` | ❌ **SILENT_HANG**：死锁成立（`GracefulStop` server.go:801 ↔ `Serve` server.go:318 争同一把锁），25s 无报告 |
| 7 | `grpc-1293` | grpc#1293 | real-repo | 1.10.8 | 同上 | ❌ **OTHER_FAIL**：测试自身 5s 超时断言 FAIL |
| 8 | `grpc-1424` | grpc#1424 | real-repo | 1.10.8 | 同上 | ❌ **OTHER_FAIL**：断言失败 0.10s |
| 9 | `grpc-1459` | grpc#1459 | real-repo | 1.10.8 | `./probe.test -test.timeout 0` | ❌ **SILENT_HANG**：死锁成立（`grpc.invoke` 卡 `Mutex.Lock`），12 个 goroutine 存活，20s 无报告 |
| 10 | `grpc-1850` | grpc#1850 | real-repo | 1.10.8 | 同上 + `-args -only_env=tcp-clear` | ❌ **OTHER_FAIL**：DEADLINE 8/50 |
| 11 | `kubernetes-62464-20697` | k8s#62464（`double-rlock`） | minimal | 1.26.8 | `./bin/repro -bug=double-rlock` | ✅ DETECTED 20/20 |
| 12 | `kubernetes-62464-20697` | k8s#20697（`miss-unlock`） | minimal | 1.26.8 | `./bin/repro -bug=miss-unlock` | ✅ DETECTED 20/20 |
| 13 | `moby-17176` | moby#17176 | minimal | 待核对 | `go run moby17176.go` | ⬜ 未跑；程序自带等锁超时，预期 OTHER_FAIL |

**按 kind 分开的实测结果**（这才是能写进报告的数）：

| kind | 条数 | DETECTED | SILENT_HANG | OTHER_FAIL | 未跑 |
|---|---|---|---|---|---|
| `real-repo` | 7 | **1**（boltdb-392） | 2（grpc-793、1459） | 3（grpc-1293、1424、1850） | 1（boltdb-begin） |
| `minimal` | 6 | **5**（cockroachdb、etcd×2、k8s×2） | 0 | 0 | 1（moby） |

`real-repo` 已完成的 6 条里只中 1 条；`minimal` 5 条全中。这个差距不是巧合，见 §2。

---

## 4. 要检测哪些：6 个 non-blocking，各跑 100 次

论文口径是"每个 bug 跑 100 次，统计 100 次内是否报告"。现有记录多为 3 次或 20 次，需要补齐或明确声明按 N 次统计并记录首次命中位置。

| # | case | 竞争形态 | kind | Go | 触发命令 | 实测（2026-11-18） |
|---|---|---|---|---|---|---|
| 14 | `boltdb-341` | Close 不等写事务 → use-after-unmap | real-repo | 1.6.4 | `go run -race code/main.go` | ⬜ 未跑（需独立 GOPATH 快照） |
| 15 | `boltdb-7fb06fee` | 读事务共享 `db.meta` 指针 | real-repo | 1.10.8 | `go test -race -run=TestParallelTransactions$ -count=20` | ❌ **0/20 检出**：目标竞争（`db.meta`）一次都没报；偶发 `testing.(*common).FailNow` 假阳性 |
| 16 | `etcd-4997` | index 一致性 | minimal | 1.27.3 | `GORACE=halt_on_error=1 ./bin_buggy` | ✅ **100/100**，first_hit=1；竞争点 `ConsistentIndex` ↔ `setConsistentIndex`；fixed 0/20 |
| 17 | `grpc-1667` | map 并发读写（`mapassign_fast64`） | real-repo | 1.10.8 | `p4_probe.sh ... 10 30 race` | ✅ **10/10**，first_hit=1；fixed 10/10 PASS |
| 18 | `grpc-1687` | `send on closed channel` | real-repo | 1.10.8 | `go test -race -run=...WriteStatusWrite$` | ❌ **0/3**：3 次全 panic，DATA RACE 报告 0 次（order violation 不在定义域） |
| 19 | `kubernetes-9926` | capabilities 字段 | minimal | 1.27.3 | `GORACE=halt_on_error=1 ./bin_buggy` | ✅ **100/100**，first_hit=1；竞争点 `Get` ↔ `SetForTests` |

**实测 3/6**（real-repo 1/3 已完成部分，minimal 2/2）。两个未检出各有一个明确机理，不是"工具坏了"：`7fb06fee` 的目标竞争在 20 轮里从未被 TSan 观察到（同时出现测试框架假阳性，说明插桩是生效的）；`grpc-1687` 是 channel 关闭后再发送，属 order violation，TSan 只看 happens-before 数据访问。

这个方向和论文的 `lib 0/2`、`chan 0/1` 完全一致。

---

## 5. 现有基建可以直接复用，不用另写脚本

| 需求 | 现成的东西 | 用法 |
|---|---|---|
| `-race` + 多次迭代 + RACE 判定 | `code/harness/p4_probe.sh` 的第 8 个参数 | 传 `race`，迭代数传 100：`p4_probe.sh <repo> <fix> . "TestXxx$" <probe_dir> 100 30 race` |
| deadlock + race + 静默挂起三分类记录 | `code/cases/blocking/boltdb-392/scripts/race_check.sh` | 已产出 `results/race_check.txt`（`exit_code / deadlock_reported / data_race_warnings / silent_hang_until_timeout`），把这一行作为 P5 单条记录的标准格式 |
| 最小复现程序的 batch 跑 + detector 判定 | `etcd-6873`、`cockroachdb`、`kubernetes-62464` 的 `scripts/run_experiments.sh` | 都已内建 `grep "all goroutines are asleep"` 与 `rc==2` 判定，并输出 CSV |
| race 双工具链对照 | `etcd-4997`、`kubernetes-9926` 的 `scripts/run_experiments.sh` | 已实现 go1.26.8（主）+ go1.8.7（时代对照），改 `N` 即可 |

### 5.1 grpc blocking 条目去掉 timer 抑制的跑法

不要改 `p4_case.sh`（会影响 P4 已入库结论），用一个临时包装：

```bash
# 复制一份去掉 -timeout 的 harness
sed 's/-timeout "${TMO}s"/-timeout 0/' code/harness/p4_case.sh > /tmp/p4_case_notimer.sh
# 外层用 timeout 兜底，避免真的挂死
timeout 90 bash /tmp/p4_case_notimer.sh "$REPO" <fix_sha> "TestKeepaliveAwakenDeadlockProbe$" . 1 60
```

判据：输出出现 `all goroutines are asleep - deadlock!` 即 DETECTED；若仍是外部 timeout 退出，则记 SILENT_HANG（真正的检测器漏报）。

**已按此跑过（2026-11-18）**：793、1459 都是 SILENT_HANG，没有转正。这套脚本留在这里是给复现用，不是待验证的假设——结论见 §2.2。

⚠️ 两个配套注意：

1. **harness 不认这个信号**。`p4_case.sh` 的判定链只认 `test timed out` / `ok` / `FAIL`，死锁 panic 会落到 `else` 被记成 `ERROR`。别被 `SUMMARY error=3` 误导——要另跑一次 grep 拿真实结论：

   ```bash
   for f in /tmp/grpc_buggy_iter*.log; do
     grep -q "all goroutines are asleep - deadlock!" "$f" && echo "$f DETECTED" || echo "$f not-detected"
   done
   ```
2. **`-timeout 0` 之后挂死就靠外层兜底**（脚本内层是 `timeout $((TMO*3+90))`，外部再套 `timeout 90` 时以外部为准）。跑之前确认 90s 够该用例正常完成，否则会把"慢"误判成"挂"。

### 5.2 grpc-1667 的 100 次跑法

```bash
bash code/harness/p4_probe.sh "$P4_REPO" a62701e4aa1d276bec70311251d62a478404d63f . \
  "TestBalancerSubConnsMapRaceProbe$" code/cases/non-blocking/grpc-1667/probe 100 30 race
```

注意 `-race` 有 5~20× 开销，100 次单条可能十几分钟；本机 `go run -race` 报 `0xc0000139`（缺运行时 DLL），**必须在 Linux 虚拟机跑**。

---

## 6. 进度（2026-11-18 更新）

已完成：

- ✅ blocking 侧新增实测 4 条：793 / 1293 / 1424 / 1459，全部走裸进程 + `-test.timeout 0`
- ✅ non-blocking 侧新增实测 5 条：grpc-1667（10/10）、etcd-4997（100/100）、kubernetes-9926（100/100）、boltdb-7fb06fee（0/20）、grpc-1687（0/3）
- ✅ 虚拟机 `-race` 链路已验证：`go1.10.8 -race` 与 `go1.27.3 -race` 均可用（本机 Windows 不可用）

剩余（按性价比）：

1. **补 `repro_summary.csv` 的 8 个机器可读字段**（`go_version / build_cmd / trigger_cmd / runs / successes / symptom_type / evidence_log / reproduced`）——P5 数据已齐，但不补这几列，脚本仍读不出来，约半小时。
2. `boltdb-341`（non-blocking，需独立 GOPATH 快照）与 `boltdb-begin-lock-leak`、`moby-17176`（blocking）三条补齐，P5 就满 19/19。
3. 出表：Table 8 按 kind 分两行、Table 12 一行 6 条并与论文 10/20 做方向对照。

---

## 7. 写报告时必须声明的四件事

1. **分母不同**：我们是 13 / 6，论文是 21 / 20；验收线改写为"在 13 条中检出 x 条，方向一致"，不做比例复现的声明。
2. **kind 不可混算**：minimal 重实现被 detector 识别，证明的是复现体有效，不是真实 bug 可被检出。实测差距（minimal 5/5 vs real-repo 1/6）正是这条的量化证据。
3. **两个数不能并排**：`boltdb-392` 的 10/10 是"单条 bug 自身的检出率"，论文 2/21 是"全集合覆盖率"。
4. **`-race` 有假阳性要剔除**：`boltdb-7fb06fee` 在 Go 1.10.8 下会偶发报 `testing.(*common).FailNow` 之间的竞争——那是测试代码在多个子 goroutine 里调 `t.Fatalf` 导致的，栈里没有 bolt 代码。判定必须看栈是否落在目标函数，只数 `WARNING: DATA RACE` 会把这类污染算进分子。
