# 复现工作台：Go 并发 Bug 实证研究（ASPLOS'19）

论文：*Understanding Real-World Concurrency Bugs in Go*（Tu, Liu, Song, Zhang, ASPLOS'19）
复现对象：论文的 6 类实验结果（bug 分类统计 / 静态原语统计 / 动态 goroutine 测量 / 41 个 bug 复现 / 两个 detector 评测 / lift 与生命周期）

- **`复现方案.md`** — 流程与方法的完整梳理（先读这个）
- **本文件** — 怎么把脚本跑起来

---

## 当前状态（P0 已完成）

| 项 | 结果 |
|---|---|
| artifact 解析 | `data/bugs_master.csv` 171 行（85 blocking + 86 non-blocking），`data/artifact_manifest.csv` 169 个补丁，全部匹配 |
| 仓库快照 | **6/6，commit 数与论文完全一致**：boltdb `fd01fc79`(816)、etcd `346589ed`(14101)、grpc-go `f6692351`(2528)、docker `9bd5d991`(35149)、cockroachdb `cc4511e1`(29485)、kubernetes `1f0d9505`(65684) |
| 工具链 | Go 1.27.3 amd64（工具）+ Go 1.10.8 amd64（老代码），均已验证可用 |
| Linux 环境 | VMware + Ubuntu 18.04.6 server，快照 `01-base-ready`，SSH 免密 + sudo 免密已就绪 |
| 详情 | `out/p0_env_report.md`、`data/p0_artifact_checks.md` |

> 注意：`00_setup_repos.sh` 钉的是「含 2018-05-21 全天」的上界，commit 数会比论文多 3~41 个。之所以能对上，是因为随后跑了 `00_pin_exact.sh`——它从该上界沿 first-parent 回溯，找到计数与论文相等的那个 commit。只跑第一个脚本的话看到 `+41` 是正常的，别以为是切点错了。

## 目录

```
repro/
├── 复现方案.md                 六阶段流程 / 工具清单 / 风险 / 验收清单
├── Linux环境规格.md            P4 用：VMware 配置 / 发行版选型 / Go 版本矩阵
├── README.md                   本文件
├── go.mod                      tools/goast 的模块定义
├── config/apps.yaml            项目清单 / 关键词 / 统计口径 / 工具链路径
├── tools/goast/main.go         AST 静态统计器（Table 2、Table 4）
├── scripts/
│   ├── 00_parse_artifact.py    P0  artifact → bugs_master.csv + 校验报告
│   ├── 00_setup_repos.sh       P0  克隆 6 仓库并冻结到 2018-05-21（Windows）
│   ├── 00_provision_linux.sh   P0  Ubuntu 18.04 内一键准备环境（Go 双版本 + 调优 + 仓库）
│   ├── 00_env_report.py        P0  环境与快照汇总 → out/p0_env_report.md
│   ├── 01_mine_commits.py      P1  关键词挖掘 → commits_*.csv
│   ├── 02_static_metrics.py    P2  单仓库原语统计
│   ├── 03_history_usage.py     P2  月度快照 → Fig 2 / Fig 3
│   ├── 04_stats_figures.py     P6  交叉表 / lift / 生命周期 CDF
│   └── 05_repro.sh             P4  单 bug 复现驱动
├── data/                       bugs_master.csv 等
└── out/                        报告与中间结果
```

## 环境（路径不再写死）

项目内所有路径都由 `scripts/_paths.sh` 从仓库布局推导，换机器、换目录名都不用改脚本：

| 用途 | 默认位置 | 覆盖方式 |
|---|---|---|
| 上游仓库（6 个） | 项目根下的 `6app/`（或 `repos/`） | 环境变量 `REPO_ROOT` |
| pin 表、克隆日志 | `repro/logs/` | `LOG_DIR` |
| 报告与中间结果 | `repro/out/` | `OUT_DIR` |
| 二进制（goast 等） | 系统临时目录 | `BIN_DIR` |
| Go 工具链 | `PATH` 里的 `go` | `GO_MODERN` / `GO_LEGACY` |

机器相关的那几项写在 `repro/local.env`，**该文件不进版本库**：

```bash
cp repro/local.env.example repro/local.env   # 然后按本机情况改
```

本机（Windows）的实测值在 `local.env.example` 里已作为示例列出。

> 关于「二进制为什么不放在项目目录」：这台 Windows 上，放在 Desktop 下的自编译 exe 会被系统策略拒绝读写文件（`winapi error #5`）。所以 `BIN_DIR` 指向 `C:/gs/bin`，由 `local.env` 指定；Linux 上没有这个限制，`local.env.example` 里给了 `$HOME/.local/bin` 的写法。

> 机器原有的 `C:\Program Files (x86)\Go` 是 **go1.27.3 windows/386**，32 位，不支持 `-race`，P5 不能用它。已另装 amd64 版本，不动原安装。

## 一键跑通

在项目根目录（不是 `repro/`）执行：

```bash
./run.sh help          # 列出所有目标
./run.sh check-pins    # 先确认 6 个仓库停在 repo.lock.tsv 的 commit 上

./run.sh parse         # P0  artifact -> data/*.csv
./run.sh env-report    # P0  环境与快照汇总 -> out/p0_env_report.md
./run.sh goast         # 编译 AST 统计器
./run.sh mine          # P1  6 个仓库关键词挖掘
./run.sh static        # P2  6 个仓库静态原语统计
```

Linux 上有 `make` 的话，`make <同名目标>` 等价。

单独跑某一个仓库时用原始脚本，参数如下：

```bash
# P1：关键词挖掘（单仓库）
python repro/scripts/01_mine_commits.py --repo 6app/etcd --app etcd \
    --until 2018-05-21 --out repro/out/commits_etcd.csv

# P2：静态统计（单仓库）
python repro/scripts/02_static_metrics.py --repo 6app/etcd --app etcd \
    --goast-cmd "$BIN_DIR/goast.exe" --out repro/out/static_etcd.json

# P4：复现单个 bug（示例：BoltDB 死锁）
./repro/scripts/05_repro.sh --repo 6app/boltdb --app boltdb --bug-id boltdb#392 \
    --commit <buggy_commit> --build "GO111MODULE=off go build ./cmd/bolt" \
    --run "./bolt bench -n 1000" --runs 30 --timeout 60 --out repro/out/repro_boltdb.csv
```

# P6：统计
python scripts/04_stats_figures.py --bugs data/bugs_master.csv --outdir out
```

## 三个必须注意的点

1. **快照日期是 2018-05-21，不是 05-31**。这个日期来自 artifact 的 `bug table.xlsx`（Date 列 Excel 序列号 43241）。切点用 `--before=2018-05-22` 才能含当天全天；BoltDB 在该切点恰好 816 个 commit，与论文完全一致。
2. **口径先定后跑**。`config/apps.yaml` 的 `static_rules` 就是你的口径；chan 是否计入 send/recv 会直接改变 Table 4 的比例。
3. **复现与检测分开跑**。`-race` 会改变调度，先统计不带 race 的复现率，再单独评测 detector。

## Windows 上踩过的坑（已规避）

| 坑 | 表现 | 处理 |
|---|---|---|
| Desktop 下运行自编译 exe | `winapi error #5`，读任何文件都失败 | 二进制放 `C:/gs/bin` 运行 |
| `core.autocrlf=true`（系统默认） | 补丁行号错位，P4 diff 定位失效 | 克隆时 `-c core.autocrlf=false`，并写入仓库 config |
| 深路径 | Kubernetes 路径超 260 字符 | `core.longpaths=true`（Git 走 `\\?\` 前缀），项目路径本身已无法再缩短 |
| 32 位 Go | `-race` 不受支持 | 另装 amd64 工具链 |
| `bolt` 主包不是根包 | `go build .` 出 `.a` 归档而非 exe | 编译 `./cmd/bolt` |
| 代理对 curl/schannel | TLS 握手失败 | 用 git（OpenSSL）或走阿里云镜像 |

## 已知限制

- `tools/goast` 用轻量启发式推断变量类型，跨包传递的原语会漏计；默认排除 `_test.go`，而论文 LOC 口径疑似包含测试。
- `05_repro.sh` 只做症状判定与统计，触发输入必须人工从 bug report 抠。
- 人工分类（171 个 bug）不可复现，只能做一致性检验。
