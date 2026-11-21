# 11-18 批次：etcd 三条 blocking 复现

ASPLOS'19《Understanding Real-World Concurrency Bugs in Go》复现交付的一个增量批次。只做 etcd，只做 blocking，共 3 条，全部在虚拟机上用 Go 1.10.8 跑通。

## 结果

| 条目 | 机理 | buggy | fixed | 证据 |
|---|---|---|---|---|
| `etcd#6937` | `bcast()` 持写锁又调 `size()` 取读锁，goroutine 自锁 | DEADLOCK | CLEAN | [`case`](code/cases/blocking/etcd-6937/) |
| `etcd#5509` | `acquire()` 与 `reconnect()` 锁序相反（ABBA），一侧取写锁 | DEADLOCK | CLEAN | [`case`](code/cases/blocking/etcd-5509/) |
| `etcd#4679` | `Close()` 持 `c.mu` 等 watcher 退出，watcher 退出需要 `c.mu` | DEADLOCK | CLEAN | [`case`](code/cases/blocking/etcd-4679/) |

三条都在论文的 41 条复现集合内（`Reproduced?=1`），可直接计入 **Table 8** 的分母，不需要按"集合外补充"另算。

## 目录

```
11-18/
├── README.md                 本文件
├── code/cases/blocking/      三个 case，每个自包含（README + run.sh + buggy/fixed + logs + results）
│   ├── etcd-6937/
│   ├── etcd-5509/
│   └── etcd-4679/
├── data/etcd_targets.csv     13 条 etcd 目标，标注本批 3 条已完成、10 条待做
├── code/p5_run_one.sh        P5 单条 blocking 检测：裸进程 + `-test.timeout 0` + SIGQUIT 抓栈
├── docs/BATCH-11-18.md       选条标准、被否候选、方法与环境、剩余 10 条的建议顺序
├── docs/P5-CHECKLIST.md      P5 检测器评测：19 条要检测什么、四分类判据、实测结果
├── report/                   空（本批不出报告）
└── results/
    ├── data/repro_summary_1118.csv   3 行汇总，字段与 11-14 一致
    ├── data/p5_checklist.csv         P5 实测表，19 行（已填 15 行，4 行待跑）
    ├── logs/p5-1118/                 P5 原始证据：793/1293/1424/1459 的 goroutine 栈、race 报告
    └── shots/                空占位
```

`code/harness/` 不在本批复制：通用脚本在 `11-14/code/harness/` 只留一份，本批每个 case 自带 `run.sh`。

## 怎么重跑

单个 case：

```bash
cd code/cases/blocking/etcd-6937
./run.sh                                   # PATH 里的 go
GO=/usr/local/go1.10.8/bin/go ./run.sh     # 指定 2018 年工具链
```

三个一起（虚拟机上的做法）：

```bash
tar czf /tmp/etcd3.tgz --exclude='logs/.bin*' etcd-6937 etcd-5509 etcd-4679
scp -i ~/.ssh/id_repro /tmp/etcd3.tgz li@192.168.47.128:/tmp/
ssh -i ~/.ssh/id_repro li@192.168.47.128 \
  'rm -rf ~/repro-1118 && mkdir -p ~/repro-1118 && tar xzf /tmp/etcd3.tgz -C ~/repro-1118 &&
   cd ~/repro-1118 && for d in etcd-*; do (cd $d && GO=/usr/local/go1.10.8/bin/go ./run.sh); done'
```

每个 `run.sh` 都会写 `logs/verdict.txt`，形如 `buggy=DEADLOCK fixed=CLEAN`；脚本退出码 0 表示对照成立。

## 环境

| 项 | 值 |
|---|---|
| 主机 | `li@192.168.47.128` |
| 系统 | Ubuntu 18.04 / Linux 4.15.0-213-generic / x86_64 |
| Go | `/usr/local/go1.10.8` |
| 判定 | `all goroutines are asleep - deadlock!` + exit=2 为触发；exit=0 且打印完成行算干净 |

## 三条的共性

都是 blocking，且都能被 Go **内置死锁检测器**一次抓住 —— 这三条会同时成为 P5（Table 8）的样本。三条形态各不相同（重入 / 顺序反转 / 持锁等待），做 Table 6 的致因归类时不会挤在同一格。

## 已知边界

- 最小复现不是完整 etcd 构建，保真依据是每个 case 的 `results/real-source.txt`（`git show <fix>^` 的原生文件）与 README 第 2 节的行号级对照；
- `etcd#5509` 的 ABBA 本身是概率性的，buggy 侧用两个握手点固定交错，这一点在 case README 里写明，不算"改造 bug"；
- non-blocking 的 5 条 etcd 目标（`#3060 #3593 #4876 #7816 #8183`）本批未做，需要先确认虚拟机上 `-race` 可用。
