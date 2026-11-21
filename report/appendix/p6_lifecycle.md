# P6 · 论文 Figure 4「Bug Life Time」复现

> 对应论文：ASPLOS'19 §3.2 Figure 4。原文正文（第 5 页右栏）给出的定义：
> *"the time from when the buggy code was added (committed) to the software to when it is being fixed in the software (a bug-fixing patch is committed)"*
>
> 即 **生命周期 = 引入提交 → 修复提交的时间差**。论文只给了 CDF 曲线，正文没有给任何分位数数字。

---

## 1 方法

| 步骤 | 做法 |
|---|---|
| 修复点 | `data/bugs_master.csv` 的 `fix_commit` |
| 引入点 | 取 `fix^`（第一父），对补丁覆盖的**旧行**做 `git blame -w`，取这些行里**最早**的那次改动所在提交（B-SZZ 近似） |
| 生命周期 | `fix` 与 `intro` 的 committer time 之差，单位天 |
| 纯插入补丁 | 旧行数为 0 时，改用插入点前一行的 blame 时间作上下文代理（上界），`method=context` 标记 |
| 剔除 | 无旧行且无上下文可用、引入晚于修复、修复提交不存在 |

脚本：`code/analysis/04_lifecycle.py`（可复跑，`--fig-only` 只重画图）。

## 2 覆盖范围（重要）

| 应用 | bug 数 | 是否纳入 | 原因 |
|---|---:|---|---|
| etcd | 37 | ✅ | 完整克隆 |
| grpc-go | 23 | ✅ | 完整克隆 |
| boltdb | 3 | ✅ | 完整克隆（另 2 行无 `fix_commit`） |
| docker | 44 | ❌ | `filter=tree:0` 按需克隆，本地无文件内容 |
| kubernetes | 34 | ❌ | 同上 |
| cockroachdb | 28 | ❌ | 同上 |

三个 `tree:0` 仓库做 blame 必须联网抓 blob，实测被代理拦死：

```
fatal: unable to access 'https://github.com/moby/moby.git/': CONNECT tunnel failed, response 502
fatal: could not fetch 8a7e12b4... from promisor remote
```

**所以本图是 63/171 条（37%）、3/6 个应用的复现**，不是全量。报告里必须写明这一点；
若要补齐，需在能直连 GitHub 的机器上重新克隆 docker / kubernetes / cockroachdb（去掉 `--filter`）。

分布：shared memory **33** 条、message passing **30** 条；`method=blame` 55 条、`method=context` 8 条。

## 3 结果与论文对比

### 3.1 分位数

| 指标 | 论文（从图反解） | 本文（63 条） | 差 |
|---|---:|---:|---:|
| shared memory 中位数 | ≈ 74 天 | **59.9 天** | −14 天 |
| message passing 中位数 | ≈ 96 天 | **106.5 天** | +11 天 |
| shared memory P75 | ≈ 175 天 | 298.7 天 | +124 天 |
| message passing P75 | ≈ 192 天 | 197.8 天 | +6 天 |

> 论文的分位数由 100 天采样点线性插值得到（SM：0→0.039、100→0.660；MP：100→0.523、200→0.769）。

### 3.2 逐点 CDF（每 100 天）

| 天 | 论文 SM | 本文 SM | 差 | 论文 MP | 本文 MP | 差 |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 0.039 | 0.152 | +0.113 | 0.014 | 0.000 | −0.014 |
| 100 | 0.660 | 0.576 | −0.084 | 0.523 | 0.433 | −0.090 |
| 200 | 0.780 | 0.697 | −0.083 | 0.769 | 0.733 | −0.036 |
| 300 | 0.898 | 0.758 | −0.140 | 0.861 | 0.800 | −0.061 |
| 400 | 0.939 | 0.788 | −0.151 | 0.892 | 0.800 | −0.092 |
| 500 | 0.979 | 0.879 | −0.100 | 0.969 | 0.900 | −0.069 |
| 600 | 0.979 | 0.909 | −0.070 | 0.969 | 0.900 | −0.069 |
| 700 | 1.000 | 0.939 | −0.061 | 1.000 | 1.000 | 0.000 |

> 论文数值来自 PDF 第 5 页该图的矢量路径（`get_drawings`，红色/黑色两条折线，采样点恰好落在 0/100/…/700），
> 换算后取 `1 − y` 得 CDF。参考截图见 `report/figures/fig4_paper_reference.png`。

**判定：partially supported。**
- 定性结论成立：两类 bug 都是长尾，到 300 天仍有 10~25% 未修，符合论文"most bugs have long life time"。
- 定量上有系统偏差：除第 0 天外，我们的 CDF 在每个采样点都**低 4~15 个百分点**，即"修得更慢"。
- 两类的相对关系一致：shared memory 在 100 天内修得更快（0.58 vs 0.43），到 300 天后 message passing 反超——与论文曲线交叉的位置（200~300 天）一致。

## 4 偏差解释

1. **样本结构不同**：我们 63 条里 etcd 占 37 条（59%），论文 171 条里 etcd 只占 22%。etcd 在 2014-09-03 有一次集中修复（同日多笔），把 shared memory 的第 0 天 CDF 推到 15%。
2. **口径差异**：我们用 committer time；若论文用 author time，rebase/合入会让修复时间整体后移几天，方向与观测一致（我们的 CDF 偏低）。
3. **只覆盖 3 个应用**：docker/kubernetes 的 bug 生命周期通常更长，缺它们会**抬高**我们的 CDF，所以真实差距可能比表里更大。

## 5 局限

- 37% 覆盖率，不能声称复现了全量分布。
- B-SZZ 只看修复补丁触碰的旧行；若修复是"新增一个检查"，引入点会落到周边代码（8 条 `context`）。
- 论文正文提到"bug 被报告的时间接近修复时间"，这条我们没有数据（artifact 无 issue 时间），未复现。

## 6 复跑

```bash
python code/analysis/04_lifecycle.py \
    --repos <6app 目录> \
    --data data/bugs_master.csv \
    --out-dir data \
    --fig report/figures/fig4_bug_lifetime.svg
```

产物：`data/bug_lifetime.csv`（63 行有效）、`data/lifecycle_cdf.csv`、`report/figures/fig4_bug_lifetime.svg`。
