# docs —— 过程分析

不是最终报告，是每个阶段的**判断依据**与**踩过的坑**。报告中要引用某个结论时，
出处在这里；报告中出现「为什么这么做」的问题，答案也在这里。

| 文件 | 阶段 | 内容 |
|---|---|---|
| `p0-env.md` | P0 | 6 个仓库如何按 commit 数反推到论文那一天，环境规格 |
| `p1-screening.md` | P1 | 3,105 vs 3,211 的口径差，为什么不能声称复现了筛选漏斗 |
| `p2-static.md` | P2 | AST 统计口径，Table 2 / Table 4 逐项偏差 |
| `p4-feasibility.md` | P4 | 44 行 → 41 条唯一 bug 的 A/B/C 分级依据 |
| `p4-repro-boltdb.md` | P4 | boltdb 两条的复现细节、官方测试为何无效、环境坑 |
| `p5-detector.md` | P5 | 检测器评测口径（待写） |

## 待补

- `p3-dynamic.md`：gRPC benchmark 与 `runtime/trace` 的测量方案（P3 未开始）
- `p6-stats.md`：lift 显著性与生命周期 CDF 的统计方法（P6 未开始）
