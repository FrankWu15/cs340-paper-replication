# gRPC-C 原语对照（论文 §3.2 末段 746 vs 786）

论文原句：

> gRPC-C only uses lock, and it is used in 746 places (5.3 primitive usages per
> KLOC). gRPC-Go uses eight different types of primitives in 786 places (14.8
> primitive usages per KLOC).

这一条不涉及运行程序，只数源码，但论文没写统计规则。本 case 把规则写死并做成脚本，
目标是把 746 / 786 这两个数各归位到自己能复核的口径上。

## 怎么跑

```bash
# gRPC-C（C/C++ 实现）：gitee 镜像，默认分支历史完整
git clone --filter=blob:none https://gitee.com/mirrors/grpc.git grpc-c
cd grpc-c && git checkout v1.12.0 && cd ..

python count_primitives.py --root grpc-c --json out/grpc-c_v1.12.0.json

# gRPC-Go：goast 与本仓库 P2 阶段同一份工具
go build -o goast ../../../2026-11-11/code/tools/goast
python make_comparison.py --c-json out/grpc-c_v1.12.0.json \
    --go-repo <grpc-go 仓库> --goast ./goast --out out/grpc_c_vs_go.csv
```

`count_primitives.py` 只依赖标准库；`make_comparison.py` 需要 goast 二进制。

## 口径

| 项 | 取值 | 依据 |
|---|---|---|
| 范围 | `src/core/` + `include/` | 只算 C core；php/ruby/python 绑定是"用 gRPC 的客户端"，不是 gRPC-C 本体 |
| 排除 | `third_party/`、非 C/C++ 文件 | 与 Go 侧排除 vendor 对称 |
| 计数 | `gpr_mu_lock` / `gpr_mu_unlock` / `gpr_mu_trylock` 的**调用点** | 与 goast 的 `lock_calls` 同口径：加锁解锁都算，因为 Table 4 的 Mutex 列也是按调用点计 |
| 不计 | `gpr_mu_init/destroy`（对象生命周期）、`gpr_cv_*`（论文说"only uses lock"） | —— |

## 结果

| 版本 | 锁使用点 | 核心代码行（原始/代码） | 每 KLOC（原始行） |
|---|---:|---:|---:|
| v1.10.0 | 726 | 118.1K / 78.7K | 6.15 |
| **v1.11.0** | **746** | 134.5K / 88.8K | 5.55 |
| **v1.12.0** | **746** | 135.4K / 89.3K | 5.51 |
| v1.20.0 | 663 | 171.9K / — | 3.86 |
| 论文 | 746 | ≈140K | 5.3 |

**v1.11.0 与 v1.12.0 都是 746，逐点相同。** 这不是凑出来的：三个函数各自计数
（329 + 411 + 6 = 746），换个版本就变（v1.10 差 20，v1.20 差 83，因为 2019 年
gRPC-C 把同步原语换成了 C++ 的 `Mutex`/`MutexLock` 抽象）。

`140K` 与我们的 `135.4K` 差 3.4%，密度 5.51 vs 5.3 差 4.0%，说明论文的 LOC
是按**原始行**（含注释空行）数的；若按代码行（去注释空行）只有 89.3K，密度会是 8.35。

## 与 gRPC-Go 的对照

| | 原语种类 | 使用点 | 代码行 | 每 KLOC |
|---|---:|---:|---:|---:|
| gRPC-C v1.12.0 | 1（lock） | 746 | 89.3K | 8.35 |
| gRPC-Go f6692351 | 7 列 / 8 类 | 771（论文 786，−1.9%） | 32.1K（不含测试） | 24.0 |
| 比值 | 1 : 8 | 1 : 1.03 | | **1 : 2.87** |

"8 类"是 `sync.Mutex`、`sync.RWMutex`、`sync.Once`、`sync.WaitGroup`、`sync.Cond`、
`sync.Pool`、`sync/atomic`、`chan`——Table 4 把前两者并成一列，所以表里是 7 列。

## 三处与论文不一致的地方

**1）密度的分母口径不统一。** 论文的 Go 密度 14.8 = 786 / 53.1K，其中 53.1K 是
**含测试**的代码行；C 密度 5.3 = 746 / 140K，140K 是**原始行**。两个分母不是一回事，
所以 14.8/5.3 = 2.79 这个比值不能直接当"密度差 2.8 倍"来引用。统一到"不含测试的
代码行"两侧分别是 24.0 与 8.35，比值 2.87——量级一致，但单个数字对不上论文。

**2）"only uses lock" 不严谨。** gRPC-C 用了 80 处条件变量
（`gpr_cv_wait` 31 + `gpr_cv_signal` 35 + `gpr_cv_broadcast` 14）。真正成立的是
"只有一种锁、没有 channel/atomic/Once/WaitGroup"，而不是"只用锁"这一种原语。

**3）746 对版本敏感。** 同一条口径在 v1.10 是 726、v1.20 是 663。论文只写 746 不说版本，
复现时无法判断是不是同一个快照；v1.11/v1.12 都能给出 746，才让这个数站得住。

## 产物

```
data/grpc-c_v1.10.0.json  … v1.20.0.json   四个版本的逐项计数（脚本原始输出）
data/grpc_c_vs_go.csv                      两侧对照表
```
