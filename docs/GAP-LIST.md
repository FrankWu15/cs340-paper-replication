# 仓库缺口清单（对照课程要求 + 论文原文）

- 核查时间：2026-11-21
- 核查对象：`origin/main` = `cc996c6`（2026-11-21，朱奕铭 "add two cases"），28 个提交，1114 个文件，5.4 MB
- 依据：`2609_CS340_Research_Paper_Replication.pdf`（第 1 节报告、第 3 节 Git 检查）+ `go-study.pdf`（ASPLOS'19）

> **本文是 `cc996c6` 时点的快照，不是当前状态。** 其后 11-18/11-21 两批已经把 Table 6/7/9/10/11、
> Fig 2/3、Table 3 比值列、补充 7 条复现等缺口补掉，下面的 ❌ 有一半已不成立。
> 当前完成度只看 [`COMPLETION-STATUS.md`](COMPLETION-STATUS.md)；本文保留作「当时缺什么」的记录。

---

## A. 课程硬性要求（Git / 仓库）

| # | 要求 | 现状 | 判定 | 还差什么 |
|---|---|---|---|---|
| A1 | 最终版本打 `v1.0` 标签 | 只有 `backup/before-rollback`、`pre-unify-2026-11-14` | ❌ | 答辩前打 `v1.0`（最后一步做） |
| A2 | 每周至少一条实质 commit | W43 3 条、W45 7 条、W46 10 条、W47 8 条；**W44（10/26–11/01）0 条** | ❌ 缺 1 周 | 补不回来（迟交只计下一周），只能在报告/邮件里说明 |
| A3 | 每条 commit message 含学号+姓名全名 | 28 条中 **9 条缺** | ❌ | 今后必须带；历史 9 条不建议改写历史 |
| A4 | 每位成员用自己的账号实质提交 | 吴德诚 13、李振炜 6、许汝轩 6、朱奕铭 3 | 🟡 | 朱奕铭仅 3 条且 W46 空白，报告贡献声明要对得上 |
| A5 | 仅凭 README 在干净机器跑通 | 有目的、运行命令、判定口径、已知限制 | 🟡 | 缺「从 0 到跑通」的依赖安装步骤、**预期输出**、**运行耗时** |
| A6 | 版本固定（Dockerfile / 镜像 / setup 脚本） | `00_setup_repos.sh` + `00_pin_exact.sh` + `p4_deps.sh`（`GOROOT=/usr/local/go1.10.8` 写死）；`repo.lock.tsv` 记 6 仓 commit | 🟡 | 无 Dockerfile；Go 1.6.4 / 1.8.7 / 1.18 / 1.26 的安装未脚本化 |
| A7 | 无硬编码路径 | 仅 `code/cases/blocking/grpc-1424/notes/env.md` 1 处 | 🟡 | 改成 `<REPO>` 占位符 |
| A8 | 原始代码出处、许可证、起始 commit、改动文件列表 | `repo.lock.tsv` 有 commit；`third_party/bolt/LICENSE` 有 | ❌ | **无根 `LICENSE` / `NOTICE`**；未列「相对上游改了哪些文件」 |
| A9 | 有 Makefile 或构建脚本 | `code/harness/Makefile`（setup-repos / check-pins / parse / static / compare） | ✅ | 可选：根目录加一层 `make all` 入口 |
| A10 | `.gitignore`，不传构建产物/大文件/凭据 | 有 `.gitignore`；最大文件 < 1 MB，全仓 5.4 MB | ✅ | — |

**个人 × 周 提交矩阵**（A2/A4 的证据）：

| 成员 | W43 | W44 | W45 | W46 | W47 |
|---|---|---|---|---|---|
| 吴德诚 1240012684 | 3 | — | 3 | 7 | 0 |
| 李振炜 1240012318 | 0 | — | 1 | 3 | 2 |
| 许汝轩 1240011357 | 0 | — | 1 | 0 | 5 |
| 朱奕铭 1240012557 | 0 | — | 2 | 0 | 1 |

> 注：同一人存在多个 git 身份（`Frank Wu` / `FrankWu15` / `吴德诚`；`Li Zhenwei` / `icecream1293`），上表已合并。

---

## B. 最终报告（占 70%，仓库里目前是空的）

`report/` 只有 7 个阶段性附录，**没有主报告**，也没有任何英文成稿。

| # | 报告要求 | 现状 | 判定 |
|---|---|---|---|
| B1 | 英文、PDF 提交 | 无 | ❌ |
| B2 | 引言 + 1–3 条 claim，每条挂到论文某张表/图 | 无 | ❌ |
| B3 | 起始代码 / commit / 改过哪些文件 | `MIGRATION.md`、`repo.lock.tsv` 可支撑 | 🟡 素材有，未成文 |
| B4 | 环境：硬件 / OS / 内核 / 编译器版本 | 只有 `boltdb-392/results/environment.txt` 等零散记录 | 🟡 缺全局一节 |
| B5 | 负载 / 输入及获取方式 | 散在各 case README | 🟡 |
| B6 | 偏差表（条目 / 原设置 / 实际 / 原因） | 无 | ❌ |
| B7 | Paper vs. Ours 对比表 | 仅 `boltdb-392/results/table_paper_vs_ours.md` 一条 | ❌ 缺全局表 |
| B8 | 至少 3 次运行，均值 ± 标准差 | 仅 `boltdb-392/results/statistics.csv`（40 次） | ❌ 其余 20 条没有 |
| B9 | 图表（编号、正文引用） | 仅 `boltdb-392/results/figures/` 3 张 SVG；`report/figures/`、`results/shots/` 空 | ❌ |
| B10 | 每个数字可追溯到日志 | 各 case `logs/` 齐全，这是仓库最强的一项 | ✅ |
| B11 | 每条 claim 判定（supported / partial / not / inconclusive） | 无 | ❌ |
| B12 | 偏差量化 + 受控重跑解释 + 局限 | 无 | ❌ |
| B13 | Extension（一次只改一个因素） | 无 | ❌ |
| B14 | 贡献声明 + AI 使用声明 | 无 | ❌ |

---

## C. 与论文原文对照（表 / 图 / 实验）

| 论文产出 | 内容 | 仓库现状 | 判定 | 缺什么 |
|---|---|---|---|---|
| Table 1 | 6 个应用元信息 | `data/bug_table_application.csv` + `report/appendix/p0_repo_pin.md` | ✅ | — |
| Table 2 | goroutine 创建点 | `report/appendix/p2_static.md`，Total 列平均偏差 4.5% | ✅ | — |
| Table 3 | 动态创建点测量 | 无 | ❌ | P3 未做 |
| Table 4 | 并发原语用量 | `p2_static.md` §4，Mutex 合计偏差 +1.8% | ✅ | CockroachDB 偏差 −18%，需在报告里解释 |
| Table 5 | 二维分类（85/86、105/66） | `data/bug_table_{blocking,non_blocking}.csv` 原表 + 重算 | ✅ | — |
| Table 6 | blocking 致因分布 | 无输出表 | ❌ | 缺 `04_stats_figures.py` |
| Table 7 | blocking 修复策略 + lift | 无 | ❌ | 同上，lift 未算 |
| Table 8 | 死锁检测器 2/21 | 仓库内只有 `boltdb-392/results/race_check.txt`（10/10） | 🟡 1/13 | 本地 `ALL/11-18` 已实测 6/13（分 kind），**未推** |
| Table 9 | non-blocking 致因分布 | 无 | ❌ | 缺统计脚本 |
| Table 10 / 11 | non-blocking 修复策略 + lift | 无 | ❌ | 同上 |
| Table 12 | `-race` 10/20 | etcd#4997 RACE 20/20、k8s#9926 RACE 20/20、grpc#1667 ×3 | 🟡 3/6 | 缺 100 次统计与首次命中序号 |
| Fig 2 / Fig 3 | 创建点时间演化 | 无 | ❌ | P2 末段未出图 |
| Fig 4 | bug 生命周期 | `report/appendix/p6_lifecycle.md` + `fig4_bug_lifetime.svg`，63/171 条（3/6 应用） | ✅ 缩小规模 | 缺 docker/k8s/cockroachdb 三个应用（部分克隆无本地 blob） |
| §4 | 复现 41 条 | 仓库 **25 个 bug 点**，其中 **14 条落在论文 41 条内**（blocking 10/21、non-blocking 4/20） | 🟡 14/41 | 另 11 条在集合外，不能填分子 |

**已复现条目与论文 41 条的交集**：

- 在集合内（11）：boltdb#392、grpc#793、#1293、#1424、#1459、#1850、moby#17176、boltdb#341、boltdb@7fb06fee、grpc#1667、#1687
- 集合外（11）：boltdb `defdb743c`、cockroachdb `1cc69980`、etcd#6873、etcd `double-lock`、k8s#62464、#20697、etcd#4997、grpc#1546、k8s#9926、docker `0d9e543`、Moby#16309

---

## D. 现在就要传的东西（按优先级）

| 优先 | 内容 | 为什么 |
|---|---|---|
| 1 | 更新 `results/data/repro_summary.csv` 与 README 结果总表：20 → 22 条 | 今天新增的 `moby-0d9e543`、`moby-2d21996` 目录已进库，但汇总表、README 都还是 20 条，**两处口径已不一致** |
| 2 | `LICENSE` + `NOTICE`（论文与 artifact 署名） | A8 直接扣分项，10 分钟可补 |
| 3 | `ALL/11-18` 的 etcd 三条 + P5 实测清单与日志 | 本地已完成，仓库里没有；直接支撑 Table 8 / Table 12 |
| 4 | `04_stats_figures.py` 及其产物（Table 6/7/9/10/11 + 两组 lift） | 论文对照里最大的一片空白，纯统计，半天可出 |
| 5 | `setup_go_versions.sh` 或 `Dockerfile` | A6：五个 Go 版本目前靠口头说明 |
| 6 | README 补「干净机器从 0 跑通 + 预期输出 + 耗时」 | A5 |
| 7 | 最终报告英文 PDF + 图表 | B 全部 |
| 8 | 打 `v1.0` 标签 | A1，放最后 |

---

## E. 一句话结论

仓库的**工程侧已经成型**（22 个自包含 case、日志可追溯、`.gitignore` 干净、5.4 MB 无大文件），
缺的是**三块**：① 报告本体一份都没有；② 论文对照的后半段统计（Table 6/7/9/10/11 + lift）没做；
③ 几项管理动作（v1.0、LICENSE、汇总表同步、W44 空档）。
