# BoltDB 并发缺陷复现

复现 *Understanding Real-World Concurrency Bugs in Go*（ASPLOS'19）数据集中
BoltDB 的 2 个并发 bug，并对每个 bug 做 **buggy 提交 vs 修复提交** 的对照实验。

数据来源：[`system-pclub/go-concurrency-bugs`](https://github.com/system-pclub/go-concurrency-bugs)

> 注：数据集中 BoltDB 的另一个缺陷（读事务引用共享 meta 页指针，
> 修复提交 `7fb06fee`）由小组另一成员完成，不在本目录范围内。

---

## 结果一览

| # | 缺陷 | 类型 | buggy 现象 | fixed 现象 |
|---|---|---|---|---|
| [02](cases/02-close-race/) | `Close()` 不等待写事务 | non-blocking | Close 35 µs 返回 → Commit 空指针 panic | Close 阻塞 55 ms → Commit 成功 |
| [03](cases/03-begin-lock-leak/) | `beginTx` 错误分支漏解锁 | blocking | `all goroutines are asleep - deadlock!` | 127 ns 正常返回错误 |

详细分析见 [../report/REPORT.md](../../report/REPORT.md)，原始输出见 [../../results/boltdb/](../../results/boltdb/)。

---

## 快速开始

环境要求：Linux（WSL2 可用）+ Go 1.6.4。这批代码早于 go.mod，必须用 GOPATH 模式。

```bash
# 1. 下载源码快照（4 份：2 个 bug × buggy/fixed）
bash setup.sh

# 2. 运行某个 case
bash run.sh 02 buggy      # 预期崩溃
bash run.sh 02 fixed      # 预期通过

bash run.sh 03 buggy      # 预期 deadlock
bash run.sh 03 fixed      # 预期通过
```

Go 1.6.4 默认取 `/usr/local/go-versions/go1.6.4`，可覆盖：

```bash
GOROOT=/path/to/go1.6.4 bash run.sh 02 buggy
```

`setup.sh` 默认通过 `ghproxy.net` 下载 GitHub 归档包；能直连 GitHub 时：

```bash
GOPROXY= bash setup.sh
```

---

## 目录

```
.
├── setup.sh                  下载源码快照
├── run.sh                    运行指定 case 的 buggy / fixed
├── cases/
│   ├── 02-close-race/        机理说明 + 最小复现程序
│   └── 03-begin-lock-leak/   机理说明 + 最小复现程序
└── patches/                  两个修复提交的 diff
```

`_work/` 是 `setup.sh` 生成的源码与构建目录，不需要提交。

---

## 复现方法要点

1. 从数据集的 `.txt` 取**修复提交**；用 GitHub API 查 `parents[0].sha` 得到 **buggy 提交**。
2. 两个快照各建一套独立 GOPATH，避免互相污染。
3. 同一份复现程序分别跑两个版本：buggy 必须出故障，fixed 必须正常结束。

每个 case 的具体触发条件（程序时序、为什么这样触发）写在各 case 的 README 里。

---

## 说明与限制

- 编号沿用数据分析阶段的序列（02、03），编号 01 即上述由另一成员完成的缺陷；
- Case 03 修复说明中的 "remap 死锁" 路径在该快照上不可触发，实际复现的是同一提交
  修复的错误分支漏解锁；
- 使用的 Go 版本（1.6.4）晚于缺陷发生年代（1.2 / 1.4），`-race` 行为存在差异。

---

## 许可

本目录的复现程序与文档为课程作业用途。`patches/` 中的 diff 来自
[boltdb/bolt](https://github.com/boltdb/bolt) 上游提交，版权归原作者所有。
