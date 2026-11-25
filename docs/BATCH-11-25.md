# 11-25 批次

本批一件事：把 11-21 补充的 3 条 minimal non-blocking 案例（`moby-28682`、`kubernetes-36377`、
`cockroachdb-17112`）搬到 Linux 虚拟机上重跑，**补上此前缺的 `-race` 证据**。

起因：本机 Windows 上 `go build -race` 能过，但产物一启动就 `0xC0000139`（race 运行时 DLL 缺失），
所以 11-21 只能靠可观测不变量判定，Table 12 记不上账。

---

## 1. 结果

| 案例 | 不变量（10 轮/侧） | `-race`（100 轮/侧） | 首次命中 | fixed 侧 `-race` |
| --- | --- | --- | ---: | ---: |
| `moby-28682` | BUG 10/10 → OK 10/10 | **0/100** | — | 0/100 |
| `kubernetes-36377` | BUG 10/10 → OK 10/10 | **100/100** | 1 | 0/100 |
| `cockroachdb-17112` | BUG 10/10 → OK 10/10 | **100/100** | 1 | 0/100 |

不变量侧的量值（buggy 10 轮）：

- `moby-28682`：200 次试验漏发 close stdin **88~115 次**（中位 98），fixed 恒为 0。
- `kubernetes-36377`：store 内对象被 reconcile 改写，annotations **1 → 2**，10 轮一致。
- `cockroachdb-17112`：2 秒窗口内快照与决策时刻不一致 **100~169 次**（中位 128），fixed 恒为 0。

---

## 2. 竞争落点

两条命中的竞争都正好落在 bug 机制上，不是旁支的偶然竞争：

| 案例 | 写 | 读 | 位置 |
| --- | --- | --- | --- |
| kubernetes#36377 | `main.reconcile()`（mapassign） | `main.main.func1()` 的 `len(obj.Annotations)` | `buggy/main.go:57` / `:71` |
| cockroachdb#17112 | `(*backupState).exportFile()` 的 append | `(*backupState).checkpoint()` 锁外读 `s.files` | `buggy/main.go:41` / `:62` |

`moby-28682` 没有任何未同步访问：`stdinClose` 全程 mutex 保护，缺陷是 `select` 在两个 case
同时就绪时等概率随机、走了空分支。**0/100 是正确结果**，不是检测失败。

原始报告：`code/cases/non-blocking/<case>/logs/vm-1125/race/sample_buggy.log`。

---

## 3. 与旧记录的关系

`docs/COMPLETION-STATUS.md` 里"这 3 条没跑 `-race`、不能替 Table 12 记检出"那段已改写为实测结果，
并保留三条口径：

1. 形态是 **minimal**，不是上游源码，所以这 2 条检出**单独列**，不并进原有的"上游/独立复现体"那张表；
2. 合成一句可说：`-race` 实测 **5/8**（原表 6 条里 3 条 + 本次 2 条）；
3. `moby-28682` 的 0/100 归到论文「并非所有非阻塞型缺陷都是数据竞争」那条原因，不算漏检事故。

论文只给分类计数（传统 7/13、匿名 3/4、库 0/2、channel 0/1），**无法逐条对齐**，
所以只能说"这两条若被跑过，预期会被检出"，不能断言论文漏计了 2 条。

---

## 4. 方法与环境

| 项 | 值 |
| --- | --- |
| 机器 | VMware `ubuntu1804-p4`，`li@192.168.47.128`（NAT） |
| 系统 | Ubuntu 18.04.6 LTS，kernel 4.15.0-213，4 核，7.8 GB |
| 工具链 | `go1.27.3 linux/amd64`，gcc 7.5.0（`-race` 走 cgo） |
| A 段 | 不带 `-race`，10 轮/侧，看程序自己的不变量（退出码 3 = BUG） |
| B 段 | `go build -race`，100 轮/侧，`GORACE=halt_on_error=1`，命中即停 |
| 判定 | 日志出现 `WARNING: DATA RACE` 或 `fatal error: concurrent map` 即算检出，与退出码无关 |
| 耗时 | 全流程 9 分 31 秒 |

`halt_on_error=1` 是偏离：它只影响"一轮报几条竞争"，不影响"这一轮报不报"，
所以对 100 轮检出率无影响；若要统计每轮竞争条数，去掉该变量重跑。

---

## 5. 目录与重跑

```
code/cases/non-blocking/
├── run_race.sh                      本批脚本（A 段 + B 段，三条一起）
├── moby-28682/
│   ├── logs/vm-1125/invariant/      10 轮 × 2 侧
│   ├── logs/vm-1125/race/           100 轮 × 2 侧 + hits_*.txt + sample_buggy.log
│   └── results/vm-1125.txt          汇总
├── kubernetes-36377/                （同上）
└── cockroachdb-17112/               （同上）
```

在虚拟机里：

```bash
cd code/cases/non-blocking
bash run_race.sh                                     # 三条，10 + 100
CASES=cockroachdb-17112 RUNS=3 RACE_RUNS=20 bash run_race.sh   # 单条快跑
```

---

## 6. 局限

1. **只有 4 核**，交错空间比论文机器小，理论上会低估检出率。这两条却是 100% 首轮命中，
   说明竞争窗口足够宽、不靠极端调度——反过来也印证论文那 4 条"约需 100 次才报"的缺陷窗口确实窄。
2. **minimal 形态**：能证明"这个缺陷形态属于 TSan 的检测范围"，不等于"上游程序跑起来也会被检出"。
   要坐实后者，得在真实仓库上复现，`moby-28682` 需要跑着的 containerd、`kubernetes-36377` 需要
   client-go 的 store 装配、`cockroachdb-17112` 需要 cgo + RocksDB，暂不具备条件。
