# 研究论文复现（Research Paper Replication）

**CS340 – 操作系统** · 2026–2027 学年

> 本文件是 `2609_CS340_Research_Paper_Replication.pdf`（共 5 页）的中文译文，供组内阅读使用。术语、评分项名称与链接保留英文原文；如有歧义，以英文原文为准。

---

## 分组

- **组队人数**：每组四名学生。不足四人的小组，将由教学团队随机分配成员补足规定人数。
- **论文**：每组从本文档末尾的论文清单（Paper List）中选择一篇进行复现。
- **更换论文**：仅在组队截止后一周内允许更换，即 **2026 年 11 月 1 日前**；更换须向助教提交申请（2250025281@student.must.edu.mo）。

## 暂定时间节点（Tentative DDL）

| 里程碑 | 日期 |
|---|---|
| 组队截止 | 10 月 25 日 |
| 更换论文截止 | 11 月 1 日 |
| 答辩（Presentation） | 12 月 1 日 |

从组队到答辩期间，GitHub 仓库将被**每周检查**。每周检查时间与评分标准见第 3 节。

## 小组信息收集

请通过以下表单提交小组信息与复现用的 GitHub 仓库链接：

https://v.wjx.cn/vm/rZCQLSE.aspx

## 提交物

每组需提交以下三项，每项按各自的评分标准单独按 100% 计分：

- **最终报告（Final Report）**：关于复现工作的书面报告（见第 1 节）。
- **最终答辩（Final Presentation）**：以小组为单位对复现工作进行汇报，具体要求见《答辩说明》（Presentation Instruction）。
- **Git 历史检查（Git History Check）**：小组的 GitHub 仓库，每周检查并在最终截止时检查；最终版本必须打上 **v1.0** 标签（见第 3 节）。

---

## 1 最终报告

### 格式

- 报告必须用**英文**撰写。
- 可用 LaTeX 或 Word 排版，但必须以 **PDF** 提交。

### 报告结构

报告可按以下方式组织：

- **引言与论点（Introduction and Claims）**
  - 论文与问题：论文所解决的系统层面挑战
  - 待验证的论点：一到三个，每一个都要关联到论文中的某张表或某张图
  - 范围：复现了论文的哪些部分，以及复现的规模
- **复现环境搭建（Reproduction Setup）**
  - 起始代码：所用仓库、所用 commit，以及修改过的文件
  - 环境：硬件、操作系统与内核版本、编译器与工具版本
  - 负载：所用 benchmark、trace 或输入，以及它们的获取方式
  - 偏差：相对论文设置的每一处改动，须给出原设置、实际使用的设置与原因
- **结果（Results）**
  - 对比：一张 Paper vs. Ours 表，在同一指标、同一设置下对比
  - 统计：至少三次运行的**均值 ± 标准差**
  - 可视化：用图表呈现关键结果
  - 可追溯性：每个报告的数字都能追溯到仓库中的日志
- **差异分析（Analysis of Discrepancies）**
  - 论点判定：supported（支持）、partially supported（部分支持）、not supported（不支持）、inconclusive（无法定论）
  - 差距：与论文结果相比的绝对差与相对差
  - 证据：用受控重跑或核查来支持每一条解释，而非猜测
  - 局限：本次复现无法证明的内容
- **扩展（Extension）**
  - 问题：要测试的新条件，以及测试动机
  - 设计：一次只改变一个因素，硬件与负载保持一致
  - 结果：结果的含义，须结合论文的论点来解读
- **结论（Conclusion）**
  - 总体判定：用一句话说明是 reproduced（已复现）、partially reproduced（部分复现）还是 not reproduced（未复现）
  - 经验教训：关于复现系统研究工作的见解

### 评分标准（报告）

- **复现结果（Reproduction Results，30%）**：复现论文主要论点所依赖的实验（允许缩小规模，但须说明），并在同一指标、同一设置下用 Paper vs. Ours 表与论文对比。结果以至少三次运行的均值 ± 标准差报告，并用清晰的图表呈现。每个数字都能追溯到仓库中的日志。
- **批判性分析（Critical Analysis，30%）**：每个被测试的论点都要给出判定（supported / partially supported / not supported / inconclusive）。每一处与论文的偏差都要量化，并用证据（例如受控重跑）解释，而不是主观推测。局限须明确承认。
- **复现环境（Reproduction Setup，15%）**：报告须说明所测试的论点并逐一关联论文中的表或图；起始代码及其 commit；环境（硬件、操作系统与内核版本、编译器与工具版本，以及任何影响结果的设置）；以及与论文相比的完整偏差表（条目、原设置、实际设置、原因）。
- **扩展（Extension，15%）**：报告须在论文之外提出一个动机充分的实验（例如新的负载、配置或内核版本），一次只改变一个因素，并结合论文的论点解读其结果。
- **写作质量（Writing Quality，10%）**：报告结构清晰（引言、环境搭建、结果、分析、扩展、结论与参考文献）；图表编号并在正文中被引用；所有来源均正确引用。还须包含**贡献声明（contribution statement）**与**AI 使用声明（AI usage statement）**。

---

## 2 最终答辩

最终答辩的格式、结构与评分标准在另一份文档《答辩说明》（Presentation Instruction）中规定。

---

## 3 Git 历史检查

### 每周检查（Weekly Check）

- 教学团队**每周日 23:59** 检查每个仓库，自项目第一周起，直至最终截止。
- 每次检查要求：当周推送了**至少一个有实质内容的 commit**（代码、脚本、结果或文档）。只修改空白字符或修正拼写的 commit 不计入。
- 每条 Git commit message 必须包含提交该 commit 的组员的**学号与姓名全名**。
- 某周没有 commit 会被扣分，扣分从下面的 Weekly Commits 评分项中扣除。
- **不接受迟交**：检查时间之后才推送的 commit 只计入下一周；错过的周无法补回。

### 评分标准（Git）

- **每周提交（Weekly Commits，30%）**：仓库必须每周都体现出进展；未能做到将被扣分。
- **可复现性与环境（Reproducibility and Environment，25%）**：仅依照 README 就能在干净机器、虚拟机或容器上构建代码并运行主实验。操作系统、内核、编译器与工具的版本被**固定（pinned）**（例如写在 Dockerfile、虚拟机镜像或 setup 脚本中）；负载与输入通过脚本获取；影响结果的设置被记录；不存在硬编码路径。
- **README 与代码质量（README and Code Quality，25%）**：README 描述项目目的、环境搭建步骤、构建与运行命令、预期输出与运行耗时。代码可读、组织清晰，并有 Makefile 或构建脚本。原始代码的出处被正确署名，且附带其许可证；起始 commit 被记录；所有被修改的文件均被列出。
- **个人贡献（Individual Contributions，10%）**：每位成员都用自己的 GitHub 账号做出过实质性提交，且与最终报告中的贡献声明一致。
- **提交质量与仓库管理（Commit Quality and Repository Management，10%）**：commit message 描述所做的改动；使用 `.gitignore` 文件；不提交构建产物、磁盘镜像、大型 trace、超过 50 MB 的文件或凭据；最终版本打上 **v1.0** 标签。

---

## 论文清单（Paper List）

**1. Toward Understanding Operating System Defects**（《迈向理解操作系统缺陷》）
Hongyao Zuo, Jiali Li, Jiajun Jiang. arXiv 预印本（2026，尚未正式发表）。
论文：https://arxiv.org/abs/2608.20643
数据：https://zuohongyao.github.io

**2. The Battle of the Schedulers: FreeBSD ULE vs. Linux CFS**（《调度器之战：FreeBSD ULE 与 Linux CFS》）
Justinien Bouron, Sebastien Chevalley, Baptiste Lepers 等. USENIX ATC 2018（CCF-A）。
论文：https://www.usenix.org/system/files/conference/atc18/atc18-bouron.pdf
代码：https://github.com/JBouron/linux/tree/loadbalancing

**3. Optimizing Input Minimization in Kernel Fuzzing (SyzMini)**（《优化内核模糊测试中的输入最小化（SyzMini）》）
Hui Guo, Hao Sun, Shan Huang 等. USENIX ATC 2025（CCF-A）。
论文：https://www.usenix.org/system/files/atc25-guo.pdf
代码：https://github.com/ecnusse/SyzMini

**4. Controlled Concurrency Testing via Periodical Scheduling (PERIOD)**（《通过周期性调度实现可控并发测试（PERIOD）》）
Cheng Wen, Mengda He, Bohao Wu 等. ICSE 2022（CCF-A）。
论文：https://wcventure.github.io/pdf/ICSE2022_PERIOD.pdf
代码：https://github.com/wcventure/PERIOD

**5. Understanding Real-World Concurrency Bugs in Go**（《理解 Go 中的真实并发缺陷》）
Tengfei Tu, Xiaoyu Liu, Linhai Song, Yiying Zhang. ASPLOS 2019（CCF-A）。
论文：https://songlh.github.io/paper/go-study.pdf
代码：https://github.com/system-pclub/go-concurrency-bugs

**6. Fuzzing File Systems via Two-Dimensional Input Space Exploration (Janus)**（《通过二维输入空间探索对文件系统进行模糊测试（Janus）》）
Wen Xu, Hyungon Moon, Sanidhya Kashyap 等. IEEE S&P 2019（CCF-A）。
论文：https://taesoo.kim/pubs/2019/xu:janus.pdf
代码：https://github.com/sslab-gatech/janus

**7. Finding Crash-Consistency Bugs with Bounded Black-Box Crash Testing**（《用有界黑盒崩溃测试发现崩溃一致性缺陷》）
Jayashree Mohan, Ashlie Martinez, Soujanya Ponnapalli 等. OSDI 2018（CCF-A）。
论文：https://www.usenix.org/system/files/osdi18-mohan.pdf
代码：https://github.com/utsaslab/crashmonkey

**8. AddressSanitizer: A Fast Address Sanity Checker**（《AddressSanitizer：一种快速的地址合法性检查器》）
Konstantin Serebryany, Derek Bruening, Alexander Potapenko, Dmitry Vyukov. USENIX ATC 2012（CCF-A）。
论文：https://www.usenix.org/system/files/conference/atc12/atc12-final39.pdf
工具：https://clang.llvm.org/docs/AddressSanitizer.html

**9. An Analysis of Performance Evolution of Linux's Core Operations**（《Linux 核心操作性能演化分析》）
Xiang (Jenny) Ren, Kirk Rodrigues, Luyuan Chen 等. SOSP 2019（CCF-A）。
论文：https://www.eecg.toronto.edu/~stumm/Papers/Ren-sosp-19.pdf
代码：https://github.com/LinuxPerfStudy/LEBench

**10. Understanding Memory and Thread Safety Practices and Issues in Real-World Rust Programs**（《理解真实 Rust 程序中的内存与线程安全实践与问题》）
Boqin Qin, Yilun Chen, Zeming Yu 等. PLDI 2020（CCF-A）。
论文：https://cseweb.ucsd.edu/~yiying/RustStudy-PLDI20.pdf
代码：https://github.com/system-pclub/rust-study

---

## 联系方式（Contact）

如有任何问题，请联系助教（2250025281@student.must.edu.mo）。
