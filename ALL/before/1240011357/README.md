# Go 并发缺陷复现（BoltDB 与 gRPC-Go）

复现 *Understanding Real-World Concurrency Bugs in Go*（ASPLOS'19）公开数据集
[`system-pclub/go-concurrency-bugs`](https://github.com/system-pclub/go-concurrency-bugs)
中的并发缺陷，共 3 个案例：BoltDB 2 个、gRPC-Go 1 个。

方法为**缺陷版本（buggy）与修复版本（fixed）同程序对照**：同一份触发程序在两个
提交上分别编译运行，缺陷版出现可观测故障、修复版正常结束，方判定复现成立。

> 注：数据集中 BoltDB 的另一个缺陷（读事务引用共享 meta 页指针，修复提交
> `7fb06fee`）由小组另一成员完成并单独提交，不在本仓库范围内。

## 项目结构 / Project Structure

```
.
├── report/     最终报告草稿 / Final report draft
│   └── REPORT.md
├── code/       复现代码与实验脚本 / Replication code & scripts
│   ├── boltdb/         setup.sh、run.sh、触发程序、机理说明、补丁
│   └── grpc-go/        回归测试用例说明、补丁、构建环境记录
└── results/    实验日志与数据 / Experiment logs & data
    ├── summary.csv     结果汇总表
    ├── boltdb/         b2 / b3 两案例的 buggy、fixed 原始输出
    └── grpc-go/        gRPC 案例的 buggy、fixed 原始输出
```

## 结果汇总

| 编号 | 应用 | 缺陷 | 类型 | buggy 提交 | fixed 提交 | 结果 |
|---|---|---|---|---|---|---|
| 1 | BoltDB | `Close()` 未等待写事务 | non-blocking | `55af28c1` | `e929eba3` | 对照成立 |
| 2 | BoltDB | `beginTx` 错误分支漏解锁 → 死锁 | blocking | `01bc9be7` | `defdb743c` | 对照成立（触发路径与提交说明不同） |
| 3 | gRPC-Go | `DialContext` 协程泄漏 | blocking | `39c8c386` | `4e56696c` | 对照成立 |

## 快速开始

```bash
# BoltDB（Linux/WSL2 + Go 1.6.4，GOPATH 模式）
cd code/boltdb && bash setup.sh && bash run.sh 02 buggy

# gRPC-Go（Go 1.22.9，module 模式），见 code/grpc-go/README.md
```

完整步骤见 `report/REPORT.md` 第 8 节。
