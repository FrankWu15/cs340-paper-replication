# ASPLOS'19 Go 并发 bug 论文复现 · 归档

论文：*Understanding Real-World Concurrency Bugs in Go*（ASPLOS'19）
归档：2026-11-04 · 只读快照，可整体打包交付

## 一、完成情况

| 阶段          | 状态   | 关键结果                                           |
|---------------|--------|----------------------------------------------------|
| P0 仓库固定   | 完成   | 6 仓库 commit 数与论文完全相等                     |
| P1 关键词筛选 | 有保留 | 3,105 vs 3,211（−3.3%），但集合不等价（§3.1）      |
| P2 静态测量   | 完成   | Table 2 偏差 4.5%、Table 4 偏差 5.8%、LOC 0.7%     |
| P4 前置       | 完成   | 41 条可行性表 + 表审计，A 14 / B 28 / C 2          |
| P4 复现       | 完成   | boltdb 2 + grpc-go 4，6/6 buggy 触发、fixed 不触发 |
| P4 剩余       | 进行中 | 其余 35 条；grpc#1850 卡在 end2end 环境            |
| P5 detector   | 未开始 | Table 8 / 12，尚未动工                             |
| Table 5–11    | 阻塞   | 需先人工填 `fix_strategy` 列（171 行全空）         |

## 二、核心结论

### 2.1 P2 静态测量（6 仓库合计）

| 项目        | 代码行        | 创建点    | 共享内存  | 消息传递  | 原语合计   | MP 占比   |
|-------------|---------------|-----------|-----------|-----------|------------|-----------|
| boltdb      | 9,100         | 2         | 34        | 13        | 47         | 27.7%     |
| etcd        | 444,500       | 270       | 1,260     | 863       | 2,123      | 40.7%     |
| grpc-go     | 52,800        | 48        | 587       | 184       | 771        | 23.9%     |
| docker      | 790,900       | 147       | 1,104     | 427       | 1,531      | 27.9%     |
| cockroachdb | 520,400       | 148       | 1,933     | 723       | 2,656      | 27.2%     |
| kubernetes  | 2,304,100     | 509       | 3,110     | 700       | 3,810      | 18.4%     |
| **合计**    | **4,121,800** | **1,124** | **8,028** | **2,910** | **10,938** | **26.6%** |

| 指标                                    | 偏差                         | 判定   |
|-----------------------------------------|------------------------------|--------|
| Table 2 创建点 Total                    | 平均 4.5%（最大 etcd −9.1%） | 通过   |
| Table 4 Total                           | 平均 5.8%                    | 通过   |
| **Table 4 Mutex 列**                    | **+1.8%**                    | 通过   |
| **Table 4 chan 列**                     | **−8.1%**                    | 通过   |
| LOC 分母                                | **0.7%**，六仓库全部 <2%     | 通过   |
| Once / atomic / WaitGroup / Cond / Misc | 51%~422%                     | 不可比 |

BoltDB 三项全中：LOC 9.1K（论文 9.1K）、per KLOC 0.221（0.22）、原语 47（47）。

论文两大支柱成立：**共享内存用得比消息传递多**（73.4% vs 26.6%），**Mutex 是最常用原语、chan 是最常用消息传递原语**。

### 2.2 P4 已复现的 6 条

每条都做「buggy 触发 / fixed 不触发」的对照，各侧重复 3 次（并发类 10 次）。

| bug               | 类型   | buggy 侧症状                         | fixed 侧        |
|-------------------|--------|--------------------------------------|-----------------|
| `boltdb#341`      | 非阻塞 | `Close()` 0ms 返回，`Commit` SIGSEGV | 阻塞 159~168ms  |
| `boltdb@7fb06fee` | 非阻塞 | 失败率 80~100%（10 次）              | 失败率 0~10%    |
| `grpc#793`        | 阻塞   | 二次 `GracefulStop` 自我死锁         | 3/3 通过，0.04s |
| `grpc#1293`       | 阻塞   | 删除在途流不通知，调用方空等         | 3/3 通过        |
| `grpc#1424`       | 阻塞   | `doneChan` 永不关闭，调用方空等      | 3/3 通过        |
| `grpc#1687`       | 非阻塞 | `panic: send on closed channel`      | 3/3 通过        |

崩溃位置：`boltdb#341` 的 SIGSEGV 在 `db.go:603` → `tx.go:162`（fixed 侧阻塞到事务结束后 `Commit` 成功）；`grpc#793` 卡在 `server.go:318` 的 `Mutex.Lock`；`grpc#1687` 在 `handler_server.go:170`。

## 三、有保留的地方

**3.1 P1 的 3,105 与论文 3,211 只是数字接近。** 44 个补丁 commit 里只有 34 个落在候选集；5 条（`moby#27782`、`etcd#4474`、`grpc#1293`、`etcd#7816`、`etcd#3060`）标题不含关键词、正文才含，却都被论文标为"已复现"。全文口径重算得 4,544（高 41%），说明论文还有未写明的过滤条件。**不能用「−3.3%」声称复现了筛选漏斗。**

**3.2 A 档不等于能跑。** `boltdb#341` 是 A 档，但补丁自带的测试完全无效（`TestDB.Close()` 静默劫持了 `bolt.DB.Close()` 的调用），只能用独立探针。`grpc#793` 同理必须精确到测试函数名。

**3.3 Table 4 的 Once / atomic 两列不可比。** 论文 `atomic` 列与我们 `sync.Once` 在 6/6 仓库吻合（平均 8%），而论文 `Once` 列是我们的 5~10 倍；PDF 文本坐标已排除排版错位，只能是论文统计脚本的归类不同。无原作者脚本，如实标注，不做猜测。

**3.4 CockroachDB 是唯一整体偏差较大的项目**（Total −18.2%）。它包装类型最多、类型推断最难（`syncutil.Mutex` 165 处 vs `sync.Mutex` 1 处）。

**3.5 bug 表的 89 行空白不是缺失。** 原表 `Reproduced?` 本就三值：`1` 44 行、`0` 38 行、空白 89 行。强行填 `0` 会凭空造出 89 条假记录。对外统一表述为「41 个已复现 bug，对应 44 个补丁 commit」。

**3.6 `grpc#1850` 尚未判定。** 该测试属于 end2end 套件，本机环境下连基础用例都会卡在 `Dial` 等连接就绪（两侧均超时），因此不能算复现成功，也不能算失败，悬置待查。

**3.7 可行性表 `new_test_funcs` 列被截断到 40 字符。** 例如 `TestHandlerTransport_HandleStreams_Write` 实际是 `..._WriteStatusWrite`。测试名必须从补丁 diff 里现取，不能直接用该列。

## 四、目录

按课程要求分三层：报告 / 代码 / 结果。

```
2026-11-4-1552/
├── README.md                        本文件
├── report/                          最终报告草稿
│   ├── p0_repo_pin.md               P0 仓库固定 + artifact 对账
│   ├── p2_static.md                 ★ P2 静态测量 + Table 2/4 逐格对照
│   ├── p4_feasibility.md            P4 前置：41 条分档 + 44 行口径溯源
│   ├── p4_repro_boltdb.md           ★ boltdb 复现报告（方法、证据、三个坑）
│   └── p1_limitation.md             P1 口径局限，不作为结论引用
├── code/                            复现代码与实验脚本
│   ├── run.sh / Makefile            统一入口（无硬编码路径）
│   ├── repo.lock.tsv                6 仓库 URL + 完整 SHA + commit 数
│   └── repro/
│       ├── scripts/                 00~08 各阶段脚本
│       │   ├── p4_case.sh           ★ 单条 bug 对照复现（仓库/commit/测试名参数化）
│       │   └── p4_deps.sh           自动补齐 GOPATH 依赖
│       ├── tools/goast/main.go      静态统计器
│       └── data/                    脚本运行输入（7 份 CSV）
└── results/                         实验日志与数据
    ├── data/
    │   ├── bugs_master.csv          171 行主表（14 列）
    │   └── feasibility_44.csv       44 行可行性明细（18 列）
    ├── logs/                        6 份原始日志（判定输出、SIGSEGV 栈、panic 现场）
    └── shots/                       5 张运行截图
```

`results/data/` 是成果副本，`code/repro/data/` 是脚本运行输入，内容同源。

## 五、怎么跑

```bash
cd code
export REPO_ROOT=<6 个上游仓库所在目录>

./run.sh audit          # 开箱可跑，不需要仓库快照
./run.sh goast && ./run.sh static-all     # 需仓库快照
./run.sh feasibility    # 需 artifact + 仓库快照
```

| target                              | 作用                  |
|-------------------------------------|-----------------------|
| `check-pins`                        | 校验 6 仓库 commit 数 |
| `mine`                              | P1 关键词筛选         |
| `static` / `compare` / `static-all` | P2 静态统计与对照     |
| `feasibility`                       | 41 条可行性表         |
| `audit`                             | bug 表一致性审计      |

bug 复现必须在 Linux 虚拟机里跑（见 §6）：

```bash
# boltdb 两条，一键跑完
bash code/repro/scripts/08_repro_boltdb.sh

# 任意一条：仓库 / fix commit / 测试名 / 包目录 / 次数 / 超时
bash code/repro/scripts/p4_case.sh ~/gopath/src/google.golang.org/grpc \
  5a547ed72c "^TestServerGracefulStopIdempotent$" test 3 30
```

`p4_case.sh` 的判定分五种：`PASS` / `FAIL` / `TIMEOUT`（死锁）/ `NOTRUN`（测试名没匹配上）/ `ERROR`（编译失败）。

## 六、环境

| 用途                | 环境                                                   |
|---------------------|--------------------------------------------------------|
| 静态统计 / 可行性表 | Windows + Go 1.27.3（`go/ast` 只解析不编译，版本无关） |
| bug 复现            | Ubuntu 18.04.6 + **Go 1.10.8** + GOPATH 模式           |

复现必须 Go 1.10.8：论文研究期对应 Go 1.4~1.10，新工具链对老代码不兼容（Example 后缀检查、`quick_test.go` 的 `flag.Parse()` 与 `testing.Init()` 冲突）。必须 Linux：Windows 上 `-race` 无法运行（`0xc0000139`）。

脚本已自带两处环境钉死，避免交互式 shell 里跑飞：

- `GOROOT=/usr/local/go1.10.8`（系统默认是 Go 1.27，混用会报 `internal/goarch` 之类怪错）
- `GOPATH=$HOME/gopath`（不继承 `/etc/profile.d/go-repro.sh` 里的 `/opt/gopath`）
