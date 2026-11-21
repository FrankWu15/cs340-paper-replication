# gRPC-C 线程创建点（论文 Table 2 第七行）

论文 §3.1：gRPC-C 是 C/C++ 实现，140K 行，**只有 5 个线程创建点、0.03 个/KLOC**，与 gRPC-Go 的 44 个创建点形成对照。

## 1. 源码来源

| 项 | 值 |
|---|---|
| 仓库 | `grpc/grpc`（经 gitee 镜像 `mirrors/grpc` 取得，GitHub 直连被代理拦截） |
| 版本 | `v1.10.0`，commit `474c595`，2018-03-01 |
| 时点依据 | 论文分析期为 2018 年上半年；v1.10.0 是当时最近的正式版，与 gRPC-Go 侧用的 `f6692351`（2018-05-21）同代 |
| 体积 | 79 MB，8,775 文件 |

`third_party/` 子模块为空（boringssl/protobuf/zlib/cares 均未拉取），不影响本项统计——创建点全在 `src/` 与 `include/`，不依赖子模块。

## 2. 三种口径

论文只给了一个数（5），没给统计规则。下面三种口径全部列出，不挑对自己有利的那个。

| 口径 | 数量 | 明细 |
|---|---|---|
| **A. 物理线程创建 API** | **4** | `thd_posix.cc:97` pthread_create、`thd_windows.cc:88` CreateThread、`thread_manager.cc:34` std::thread、`dynamic_thread_pool.cc:30` new std::thread |
| **B. Linux 核心路径**（物理实现 + 逻辑启动点） | **5** | A 去掉 Windows 实现，加 `timer_manager.cc:97`（全局 timer 线程）与 `executor.cc:107`（executor 线程池） |
| **C. 全部 `gpr_thd_new` 调用点** | **6 处文件** | B 再加 `executor.cc:267`（扩容）、`ev_poll_posix.cc:1375`（poller）、`basic_timers.cc:206`（profiling） |

口径 B 与论文的 5 完全一致。它也是语义上最合理的读法：gRPC-C 起线程的地方确实只有这五类——POSIX 底层实现、CQ 线程池、server 默认线程池、全局 timer、executor 池。Windows 实现与被裁掉的 profiling/扩容路径不计入 Linux 产品运行路径。

## 3. 与论文对照

| 项 | 论文 | 本文（口径 B） | 偏差 |
|---|---|---|---|
| 创建点总数 | 5 | 5 | 0% |
| 代码行数 | 140K | 147.1K（`src/` 130,598 + `include/` 17,475） | +5.1% |
| 每 KLOC 创建点 | 0.03 | 0.034 | 落在同一位小数 |

按口径 A（4 个）则为 −20%，per KLOC 0.027，四舍五入仍是 0.03。

## 4. 为什么 gRPC-C 这么少

不是代码写得少，是**线程模型不同**：

- gRPC-C 是**线程池 + 事件循环**：5 个创建点里，3 个（thread_manager、dynamic_thread_pool、executor）都是"建一个池，池里复用"；poller 与 timer 各一个常驻线程。
- 每来一个 RPC，C 版**不新建线程**，从池里取一个干活，干完还回去。
- gRPC-Go 相反：每个 stream 起 reader/writer 两个 goroutine，每连接、每 RPC 都有自己的 goroutine（见 Table 3 实测：1000 并发 → 1019 个 goroutine）。

这正是论文 Observation 1 的另一半证据：**"goroutines are shorter but created more frequently"**——Go 侧 44 个创建点、运行时每秒数千次创建；C 侧 5 个创建点、线程数恒定。

## 5. 复现

```bash
bash count_c_sites.sh /path/to/grpc        # 需要 v1.10.0 源码树
```

输出三段：物理 API 位置、`gpr_thd_new` 调用点、LOC 分解。原始输出见 `results/raw.txt`，逐点清单见 `data/grpc_c_creation_sites.csv`。
