# CS340 论文复现 · Understanding Real-World Concurrency Bugs in Go

澳门科技大学 CS340 操作系统课程项目（2026–2027 学年）

复现论文：*Understanding Real-World Concurrency Bugs in Go*，Tu, Liu, Song, Zhang，ASPLOS'19
论文与官方 artifact：https://github.com/system-pclub/go-concurrency-bugs

## 组员

| GitHub | 姓名 | 分工 |
|---|---|---|
| FrankWu15 | 吴德诚 Wu Decheng | boltdb#392 复现 |
| DreamingZhu111 | 朱奕铭 Zhu Yiming | moby#17176 复现 |
| icecream1293 | 李振炜 Li Zhenwei | 环境/静态统计/复现驱动 |
| Semliii | 许汝轩 Xu Ruxuan | boltdb#194、boltdb#341、grpc#1424 |

每条 bug 与每项分析的负责人见 [CONTRIBUTORS.md](CONTRIBUTORS.md)。

## 目录结构

按**交付物类型**组织，不按人分层。一条 bug 的代码、日志、截图用同一个名字串起来。

```
.
├── report/   最终报告，分节写作，figures/ 放图
├── docs/     过程分析：每个阶段的判断依据与踩过的坑
├── code/
│   ├── analysis/   P0–P2 分析脚本（仓库固定、关键词挖掘、AST 统计）
│   ├── harness/    P4 通用驱动：单条 bug 对照复现、依赖补齐、日志归集
│   ├── tools/      goast 统计器
│   └── cases/      一条 bug 一个目录，见 code/cases/README.md
├── data/     输入数据：artifact 解析结果、bug 总表、41 条目标、repo.lock.tsv
└── results/  产出：data/ 统计表、logs/<case>/ 原始日志、shots/ 终端截图
```

`code/cases/grpc-793/` 对应 `results/logs/grpc-793/` 与 `results/shots/grpc-793_repro.png`，
命名一致，不必猜。

## 快速开始

```bash
# 1. 克隆 6 个上游仓库并精确对齐论文 commit（约 430 MB，只需一次）
make setup-repos

# 2. 校验是否停在 data/repo.lock.tsv 记录的 commit
make check-pins

# 3. 解析 artifact -> data/*.csv
make parse

# 4. 静态统计与论文 Table 2 / Table 4 逐格对照
make static-all

# 5. 单条 bug 复现（需要 Linux + Go 1.10.8 + GOPATH 布局）
bash code/cases/grpc-793/run.sh
```

Windows 上没有 make 也能用：所有目标都在 `./run.sh` 里，`make` 只是薄封装。

上游仓库与论文 artifact 不入库，脚本按 `REPO_ROOT` / `ARTIFACT_DIR` 或同级的 `6app/`、
`go-concurrency-bugs-master/` 查找，找不到时给出一句明确的提示。

## 当前进度

| 阶段 | 内容 | 状态 |
|---|---|---|
| P0 | 6 仓库按 commit 精确固定 | 完成，`make check-pins` 6/6 对齐 |
| P1 | commit 历史筛并发缺陷 | 数量 3,105 vs 论文 3,211，口径有差异，见 `docs/p1-screening.md` |
| P2 | AST 静态统计 | 完成，Table 2 偏差 4.5%，Table 4 偏差 5.8% |
| P3 | 动态测量（Table 3） | 未开始 |
| P4 | bug 复现 | 已复现 6 条，详见下表 |
| P5 | 检测器评测（Table 8） | 未开始 |
| P6 | 统计与图表 | 未开始 |

### P4 已复现的 bug

| case | 症状 | 类型 | buggy 侧 | fixed 侧 |
|---|---|---|---|---|
| `boltdb-341` | `Close()` 提前返回，`Commit` SIGSEGV | 非阻塞 | closeMs=0 | closeMs=159 |
| `boltdb-7fb06fee` | 并发读写 meta 撕裂 | 非阻塞 | 失败率 80%~100% | 0%~10% |
| `grpc-793` | 二次 `GracefulStop` 自我死锁 | 阻塞 | TIMEOUT ×3 | PASS ×3 |
| `grpc-1293` | 删除在途流不通知调用方 | 阻塞 | FAIL ×3 | PASS ×3 |
| `grpc-1424` | `doneChan` 永不关闭 | 阻塞 | FAIL ×3 | PASS ×3 |
| `grpc-1687` | `send on closed channel` | 非阻塞 | FAIL ×3 | PASS ×3 |

每条的参数、判定标准与证据位置写在 `code/cases/<case>/README.md`。

## 约定

- 每条结论都要能追到 `results/logs/<case>/` 里的某一行，报告里不出现无出处的数字
- 概率型 bug 至少跑 10 轮，用失败率区间而不是「是否触发」
- `go test -run` 空匹配仍会打印 `ok`，判定必须区分 `NOTRUN`
- 目录名用小写与连字符：`grpc-793`、`boltdb-7fb06fee`
- 大体积依赖、备份、参考资料不入库，见 `.gitignore`
