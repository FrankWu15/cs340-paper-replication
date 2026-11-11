# Kubernetes 并发 bug 最小复现（补充实验）

在 `boltdb#392` 之外**多测两个 Kubernetes blocking bug**，用来覆盖论文
Table 6 里的 **Mutex / shared-memory 类**（与你原来那个 message-passing /
`Chan w/` 类互补）。本目录是独立补充实验，**没有改动 `boltdb392-replication/`，
也没有上传到 GitHub**。

## 1. 选了哪两个 bug

来源：`go-concurrency-bugs-master`（论文官方数据集）与 `bug table.xlsx`
（sheet `blocking`）。

| | Bug A | Bug B |
|---|---|---|
| BugID | `kubernetes#62464` | `kubernetes#20697` |
| fix commit | `c1b19fce903675b82e9fdd1befcc5f5d658bfe78` | `d3639aff7397dd0f0d3553b82043401ff834a356` |
| 数据集行 | `blocking` 第 28 行 | `blocking` 第 36 行 |
| 标题 | avoid dobule RLock() in cpumanager | Fix deadlock in watch cache |
| 上游文件 | `pkg/kubelet/cm/cpumanager/state/state_mem.go` | `pkg/storage/watch_cache.go` |
| 数据集分类 | circular / non-traditional / rwlock / shared memory / Syn Remove / lock-patch / 2 行 | circular / traditional / lock related / shared memory / Syn Add / mis-unlock / lock-patch / 1 行 |

**Bug A（双重读锁）**：`GetCPUSetOrDefault()` 外层 `RLock()` 之后又调用内部
同样会 `RLock()` 的 `GetCPUSet()`。Go 的 `sync.RWMutex` 是写优先的：一旦有
writer 排队，同一 goroutine 的第二次 `RLock()` 会排在 writer 后面，而 writer
又在等第一次 `RUnlock()` —— 循环等待。修复就是删掉外层那两行锁。

**Bug B（漏解锁）**：`WaitUntilFreshAndList()` 把 `defer w.RUnlock()` 放在循环
之后，超时 error path 提前 return 时 defer 还没注册，读锁永久泄漏，后续任何
writer 都卡住。修复把 defer 提到 `RLock()` 之后立刻注册。

两者都对应论文 Section 5.1.1 说的「28 个 blocking bug 由误用锁引起，包括
double locking、加锁顺序冲突、忘记解锁」，以及 Table 7 的 `Syn Remove` /
`Syn Add` / `lock-patch` 修复策略。

## 2. 环境与运行

实测环境：WSL2 Ubuntu 26.04 LTS、内核 `6.18.33.2-microsoft-standard-WSL2`、
Go `1.26.8 linux/amd64`、12 逻辑 CPU、`GOTRACEBACK=all`、`GOPROXY=off`（纯
标准库，离线构建）。完整快照见 `results/environment.txt`。

```bash
# 干净 Linux 机器，只需 Go >= 1.20、bash、coreutils、python3
bash scripts/run_experiments.sh            # 默认 4 组 × 20 次
REPEAT=30 TIMEOUT_SEC=5s bash scripts/run_experiments.sh
python3 scripts/analyze.py                 # 单独重算 mean ± SD 与图

# 单次运行
go build -o bin/repro ./cmd/repro
./bin/repro -bug=double-rlock -mode=buggy  -run-id=demo-1   # rc=2，报死锁
./bin/repro -bug=double-rlock -mode=fixed  -run-id=demo-2   # rc=0
./bin/repro -bug=miss-unlock  -mode=buggy  -run-id=demo-3   # rc=2，报死锁
./bin/repro -bug=miss-unlock  -mode=fixed  -run-id=demo-4   # rc=0
```

`buggy` 期望 Go 内置死锁检测器打印
`fatal error: all goroutines are asleep - deadlock!`（退出码 2）；
`fixed` 期望正常结束（退出码 0）。每组约 3–8 秒，全部 80 次约 20 秒。

## 3. 结果（20 次/组，共 80 次）

| Bug | Mode | n | 检出死锁 | 耗时 mean ± SD (ms) |
|---|---|---:|---:|---:|
| double-rlock | buggy | 20 | 20/20 (100%) | 236.30 ± 37.68 |
| double-rlock | fixed | 20 | 0/20 | 128.05 ± 8.00 |
| miss-unlock | buggy | 20 | 20/20 (100%) | 188.50 ± 53.08 |
| miss-unlock | fixed | 20 | 0/20 | 125.85 ± 6.17 |

SD 为样本标准差 (n−1)。耗时用 `date +%s%N` 在进程外测量，含 Go runtime
启动与 detector 的反应时间；内部 trace 显示业务部分只需 0.5–7 ms。
原始数据 `results/summary.csv`、统计 `results/statistics.csv`、
表 `results/table_results.md`、图 `results/figK1_detection_rate.svg`、
80 份未改动日志 `results/raw/`。

**结论**：两个 buggy 版本在 20/20 次运行中都被内置检测器判为死锁，
打上各自的 1–2 行补丁后 0/20 死锁 —— 在同一台机器、同一 workload 下，
唯一变量是补丁本身，构成受控对照（`controlled re-run`）。

## 4. 与论文的对照（可直接进全组报告）

| 论文位置 | 本实验可填的内容 |
|---|---|
| Table 6（blocking bug 根因） | 两个 `Mutex`/`RWMutex` 类案例，与 boltdb#392 的 `Chan w/` 类互补 |
| Section 5.1.1 | double locking 与 forgetting to unlock 的具体实例 |
| Table 7（修复策略） | `Syn Remove`（删两行 RLock/RUnlock）、`Syn Add`（提前 defer）、`lock-patch` |
| Section 5.3 / Table 8 | 补充「内置 detector 对这两类传统锁死锁同样有效」的实测；注意这不是论文 21 个复现 bug 中的两个，`Reproduced?` 列需查表确认后再写 |

## 5. 偏差表（写报告时照抄）

| # | 项目 | 论文原设置 | 本实验设置 | 原因 |
|---|---|---|---|---|
| D1 | 被测代码 | 真实 Kubernetes 历史版本 | 纯 Go 标准库最小复现，逻辑逐行照上游 fix patch 提取 | 2018 年 k8s 依赖与 GOPATH 构建在 Go 1.26 上不可行；最小复现是同组朱奕铭对 Docker bug 采用的、课程允许的做法 |
| D2 | 触发方式 | bug report 原始输入 | 加 channel 同步点 + 5 ms sleep，保证 writer 在两次 RLock 之间排队 | 论文 Section 4 明确允许 "manually add sleep" 以获得确定性触发；不改锁逻辑本身 |
| D3 | Go / OS / 内核 | 论文未报告 | Go 1.26.8 / Ubuntu 26.04 / WSL2 6.18.33.2 | 需要可 pin 的环境；`original setting = not reported` |
| D4 | 规模 | 6 个应用、171 个 bug | 1 个应用的 2 个 bug | reduced scale，作业允许但须声明 |
| D5 | 判定手段 | 论文用内置 deadlock detector 评估 21 个复现 blocking bug | 同样用内置 detector，退出码 + `fatal error` 关键字判定 | 与论文 Table 8 的检测手段一致，便于对照 |

## 6. 目录

```
go.mod, Makefile
cmd/repro/main.go                    CLI 入口
internal/bugs/double_rlock.go        Bug A，含 buggy / fixed 两版
internal/bugs/miss_unlock.go         Bug B，含 buggy / fixed 两版
scripts/run_experiments.sh           批量运行 + 环境快照 + CSV
scripts/analyze.py                  mean ± SD、表、SVG 图（纯标准库）
results/                            80 份原始日志、CSV、表、图、环境快照
```

**未上传**：本目录目前只在本地。若要并进团队仓库，请明确说明，届时建议
作为新的 `1240012684/kubernetes-extra/` 子目录提交，避免与已有的
`boltdb#392` 证据链混淆。
