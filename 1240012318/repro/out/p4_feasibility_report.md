# P4 前置：41 个目标 bug 可行性表

数据源：`repro/data/bugs_master.csv` 中 `reproduced=1` 的 44 行，对应 **41 个唯一 bug**。
补丁特征解析自 artifact 的 `.txt`（内含完整 unified diff），不走 `git show`，
避免 treeless clone 触发网络拉取。

> **口径提醒**：44 行 ≠ 41 个 bug。论文正文按 bug 计（21 blocking + 20 non-blocking = 41），
> artifact 的 CSV 按补丁 commit 计。差出的 3 行全部来自 `etcd#4876`。
> 这些 bug 的补丁被拆成多段，P4 回滚时必须**整组一起回滚**，
> 只回滚其中一段通常不足以让 bug 复现。详见 `out/bug_table_audit.md`。

## 1. 总览

分档按**补丁 commit**计（44 行），不是按 bug 计（41 个）。

| 档位 | 含义 | 条数 |
|---|---|---|
| A | 补丁自带新增测试，可直接 `go test -run` | **14** |
| B | 仅改产品代码，需自写触发程序 | **28** |
| C | 阻塞（无补丁 / commit 不在库） | **2** |

- fix commit 在本地快照：**42/44**
- fix commit 在 P1 的候选集合中：**34/44**
- fix 日期晚于 pin 日期（2018-05-21）：**0/44**

## 2. 按项目分布

| 项目 | 条数 | A | B | C | 中位改动行数 |
|---|---|---|---|---|---|
| boltdb | 4 | 2 | 0 | 2 | 52 |
| cockroachdb | 2 | 0 | 2 | 0 | 22 |
| docker | 8 | 3 | 5 | 0 | 28 |
| etcd | 16 | 4 | 12 | 0 | 28 |
| grpc-go | 10 | 5 | 5 | 0 | 25 |
| kubernetes | 4 | 0 | 4 | 0 | 20 |

## 3. 逐条明细

| # | bug_id | 项目 | 类型 | 致因 | 改动(文件/+/−) | 测试 | 档 | 说明 |
|---|---|---|---|---|---|---|---|---|
| 1 | boltdb#341 | boltdb | 非阻塞 | shared_memory | 2/51/1 | ✓ | **A** | merge commit，已用 diff <sha>^1 还原；补丁新增测试 TestDB_Close_PendingTx_RW, TestDB_Close_PendingTx_RO |
| 2 | (uid boltdb@7fb06fee) | boltdb | 非阻塞 | shared_memory | 8/145/11 | ✓ | **A** | 补丁新增测试 TestParallelTransactions |
| 3 | moby#17176 | docker | 阻塞 | shared_memory | 2/30/0 | ✓ | **A** | 补丁新增测试 TestDevmapperLockReleasedDeviceDeletion |
| 4 | moby#8909 | docker | 阻塞 | shared_memory | 2/79/1 | ✓ | **A** | 补丁新增测试 TestPsListContainersFilterExited |
| 5 | moby#256 | docker | 阻塞 | message_passing | 2/23/5 | ✓ | **A** | 补丁新增测试 TestCmdStreamLargeStderr |
| 6 | etcd#6278 | etcd | 阻塞 | message_passing | 3/32/5 | ✓ | **A** | 补丁新增测试 TestElectionOnPrefixOfExistingKey |
| 7 | etcd#5199 | etcd | 阻塞 | message_passing | 2/79/6 | ✓ | **A** | 补丁新增测试 TestMutexSessionRelock |
| 8 | etcd#5349 | etcd | 阻塞 | message_passing | 3/46/27 | ✓ | **A** | 补丁新增测试 TestElectionSessionRecampaign |
| 9 | etcd#4033 | etcd | 阻塞 | message_passing | 2/123/10 | ✓ | **A** | 补丁新增测试 TestProposeOnCommit |
| 10 | grpc#793 | grpc-go | 阻塞 | shared_memory | 2/22/1 | ✓ | **A** | merge commit，已用 diff <sha>^1 还原；补丁新增测试 TestServerGracefulStopIdempotent |
| 11 | grpc#1850 | grpc-go | 阻塞 | message_passing | 3/48/0 | ✓ | **A** | 补丁新增测试 TestClientDoesntDeadlockWhileWritingErrornousLargeMessages |
| 12 | grpc#1293 | grpc-go | 阻塞 | message_passing | 2/41/0 | ✓ | **A** | 补丁新增测试 TestInflightStreamClosing |
| 13 | grpc#1424 | grpc-go | 阻塞 | message_passing | 2/25/0 | ✓ | **A** | 补丁新增测试 TestClientLBWatcherWithClosedBalancer |
| 14 | grpc#1687 | grpc-go | 非阻塞 | message_passing | 2/34/16 | ✓ | **A** | 补丁新增测试 TestHandlerTransport_HandleStreams_WriteStatusWrite |
| 15 | cockroachdb#17112 | cockroachdb | 非阻塞 | shared_memory | 2/15/7 | ✓ | **B** | 补丁改动了测试文件但未新增 Test 函数 |
| 16 | cockroachdb#19962 | cockroachdb | 非阻塞 | shared_memory | 1/2/1 |  | **B** | 仅改产品代码，需自写触发程序 |
| 17 | moby#27782 | docker | 阻塞 | message_passing | 1/17/5 |  | **B** | 仅改产品代码，需自写触发程序 |
| 18 | Moby#28682 | docker | 非阻塞 | message_passing | 2/35/1 | ✓ | **B** | 补丁改动了测试文件但未新增 Test 函数 |
| 19 | Moby#22985 | docker | 非阻塞 | shared_memory | 1/8/1 | ✓ | **B** | 补丁改动了测试文件但未新增 Test 函数 |
| 20 | Moby#22940 | docker | 非阻塞 | shared_memory | 1/3/3 | ✓ | **B** | 补丁改动了测试文件但未新增 Test 函数 |
| 21 | Moby#27037 | docker | 非阻塞 | shared_memory | 1/9/3 | ✓ | **B** | 补丁改动了测试文件但未新增 Test 函数 |
| 22 | etcd#6937 | etcd | 阻塞 | shared_memory | 1/3/3 |  | **B** | 仅改产品代码，需自写触发程序 |
| 23 | etcd#4679 | etcd | 阻塞 | message_passing | 2/25/10 | ✓ | **B** | 补丁改动了测试文件但未新增 Test 函数 |
| 24 | etcd#4474 | etcd | 阻塞 | message_passing | 1/25/13 |  | **B** | 仅改产品代码，需自写触发程序 |
| 25 | etcd#5509 | etcd | 阻塞 | shared_memory | 2/10/14 | ✓ | **B** | 补丁改动了测试文件但未新增 Test 函数 |
| 26 | etcd#3593 | etcd | 非阻塞 | shared_memory | 1/22/6 | ✓ | **B** | 补丁改动了测试文件但未新增 Test 函数 |
| 27 | etcd#8183 | etcd | 非阻塞 | shared_memory | 2/11/5 | ✓ | **B** | 补丁改动了测试文件但未新增 Test 函数 |
| 28 | etcd#4876 | etcd | 非阻塞 | shared_memory | 3/19/11 | ✓ | **B** | 补丁改动了测试文件但未新增 Test 函数 |
| 29 | etcd#4876 | etcd | 非阻塞 | shared_memory | 1/7/3 |  | **B** | 仅改产品代码，需自写触发程序 |
| 30 | etcd#4876 | etcd | 非阻塞 | shared_memory | 1/10/2 |  | **B** | 仅改产品代码，需自写触发程序 |
| 31 | etcd#7816 | etcd | 非阻塞 | shared_memory | 1/18/2 |  | **B** | 仅改产品代码，需自写触发程序 |
| 32 | etcd#4876 | etcd | 非阻塞 | message_passing | 1/3/3 |  | **B** | 仅改产品代码，需自写触发程序 |
| 33 | etcd#3060 | etcd | 非阻塞 | message_passing | 3/4/3 | ✓ | **B** | 补丁改动了测试文件但未新增 Test 函数 |
| 34 | grpc#1459 | grpc-go | 阻塞 | message_passing | 1/4/0 |  | **B** | 仅改产品代码，需自写触发程序 |
| 35 | grpc#639 | grpc-go | 阻塞 | message_passing | 1/31/29 |  | **B** | merge commit，已用 diff <sha>^1 还原；仅改产品代码，需自写触发程序 |
| 36 | grpc#1803 | grpc-go | 非阻塞 | shared_memory | 1/6/5 |  | **B** | 仅改产品代码，需自写触发程序 |
| 37 | grpc#1667 | grpc-go | 非阻塞 | shared_memory | 1/7/0 |  | **B** | 仅改产品代码，需自写触发程序 |
| 38 | grpc#1662 | grpc-go | 非阻塞 | shared_memory | 1/2/0 |  | **B** | 仅改产品代码，需自写触发程序 |
| 39 | kubernetes#30872 | kubernetes | 阻塞 | shared_memory | 1/22/11 |  | **B** | 仅改产品代码，需自写触发程序 |
| 40 | kbernetes#49404 | kubernetes | 非阻塞 | shared_memory | 1/4/3 | ✓ | **B** | 补丁改动了测试文件但未新增 Test 函数 |
| 41 | kubernetes#36377 | kubernetes | 非阻塞 | shared_memory | 2/12/2 |  | **B** | 仅改产品代码，需自写触发程序 |
| 42 | kubernetes#26407 | kubernetes | 非阻塞 | shared_memory | 2/16/4 | ✓ | **B** | 补丁改动了测试文件但未新增 Test 函数 |
| 43 | boltdb#392 | boltdb | 阻塞 | message_passing | 0/0/0 |  | **C** | artifact 未提供修复补丁（论文也未给出 fix commit） |
| 44 | boltdb#240 | boltdb | 阻塞 | shared_memory | 0/0/0 |  | **C** | artifact 未提供修复补丁（论文也未给出 fix commit） |

## 4. 与 P1 候选集的交叉验证

44 行中有 **34 行**的 fix commit 落在 P1 的 3,105 个候选里，**10 条不在**。缺失的构成：

| 原因 | 条数 | 说明 |
|---|---|---|
| 无 fix commit | 2 | artifact 未提供补丁，必然不在候选集 |
| 是 merge commit | 3 | P1 主口径排除 merge，必然不在候选集 |
| 标题不含关键词 | 5 | **需要逐条查证** |

### 标题不含关键词的 5 条：正文全部命中

| bug_id | 项目 | fix commit | 标题 | 正文命中的关键词 |
|---|---|---|---|---|
| moby#27782 | docker | `a69a59ff` | Decouple removing the fileWatcher from reading | race, deadlock, lock |
| etcd#4474 | etcd | `0cb304ec` | contrib/raftexample: fix restart path | deadlock, lock |
| grpc#1293 | grpc-go | `7df48bee` | transport: fix error handling on Stream deletion (#1 | lock, context |
| etcd#7816 | etcd | `3ce31acd` | v3client: wrap watch ctxs with blank ctx | race |
| etcd#3060 | etcd | `7f95780b` | etcdserver: init raft internal var early | race |

**这 5 条在 commit message 正文里全部命中关键词，只是标题不含。**
它们都是论文标为「已复现」的 bug，说明论文的候选集**必然包含正文匹配**，
否则这些 bug 根本进不了人工筛选环节。

这暴露了 P1 的一个方法论问题：
我们选「标题 · 排除 merge」口径，是因为它的总数（3,105）最接近论文的 3,211（−3.3%），
但**总数接近不等于集合正确**——该口径至少漏掉了 5 条论文确实收录的 bug。
改用全文口径重算（含正文、排除 merge、起始日期 2015-02）得 4,544 条，
覆盖这 5 条，但总数比论文高 41%，说明论文还有别的过滤条件（论文未说明）。

结论：P1 的 3,105 与论文的 3,211 **只是数字接近，集合并不等价**。
这条必须写进复现报告的局限性一节，不能声称「复现了论文的筛选漏斗」。

## 5. 结论与下一步

**A 档不是「直接就能跑」**，只是「补丁里有现成测试用例」。真正跑起来还差三关：
1. `git checkout <fix>^` 到修复前的版本——treeless clone 会在这里联网拉 tree；
2. 用 Go 1.10 编译——2015–2018 年的代码用现代 Go 直接编译大概率失败；
3. 并发 bug 非确定性，要重复 N 次统计触发率，不能跑一次就下结论。

因此下一步应先拿 A 档里改动最小、依赖最少的 2~3 条打通全流程。按依赖从轻到重排：

| 建议顺序 | bug | 理由 |
|---|---|---|
| 1 | `boltdb` uid 7fb06fee | BoltDB 是单包项目，无外部依赖、编译最快；补丁含 `TestParallelTransactions` |
| 2 | `boltdb#341` | 同上；merge commit，已还原出 `TestDB_Close_PendingTx_RW/RO` |
| 3 | `etcd#5199` | etcd 依赖较重但可 `go test ./clientv3/...` 单包跑；补丁含 `TestMutexSessionRelock` |

Kubernetes 与 CockroachDB 各有 4 条和 2 条但全部是 B 档（无现成测试），且编译体量最大，放到模板验证通过之后再处理。

把「checkout → 编译 → 跑测试 → 判定」这套模板跑通后，再批量推进其余 41 条。