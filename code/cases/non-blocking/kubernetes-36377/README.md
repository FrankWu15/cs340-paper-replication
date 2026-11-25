# kubernetes#36377 —— store 返回共享指针，reconcile 直接改

| 项 | 值 |
|---|---|
| 类型 | non-blocking / shared_memory |
| 修复 commit | `647b826d697abdc50aa4808fa21604c9f6fe80a4` |
| 形态 | minimal（复刻 GetByKey → 原地修改的路径） |
| 判定 | buggy 3/3 BUG，fixed 0/3 |

## 1. 症状

namespace controller 的 reconcile 与其他读者并发访问同一个 `Namespace` 对象，
数据竞争；极端情况下触发 `fatal error: concurrent map read and map write`。

## 2. 机理

`federation/pkg/federation-controller/namespace/namespace_controller.go`：

```go
baseNamespaceObj, exist, err := nc.namespaceInformerStore.GetByKey(namespace)
baseNamespace := baseNamespaceObj.(*api_v1.Namespace)
if baseNamespace.DeletionTimestamp != nil {
    if err := nc.delete(baseNamespace); err != nil {   // 改的是 store 内部对象
```

`GetByKey` 的锁只保护「取指针」这一步，返回的指针指向 informer store 内部的
那个对象。reconcile 之后对它的任何写（annotations、finalizer、deletionTimestamp）
都直接落到共享对象上，与同时读它的其他协程构成数据竞争。

## 3. 修复

补丁在拿到对象后先 `DeepCopy`，只改副本：

```go
namespaceObj, err := conversion.NewCloner().DeepCopy(namespaceObjFromStore)
baseNamespace, ok := namespaceObj.(*api_v1.Namespace)
```

## 4. 判定口径

两个 goroutine 各跑 10 万次：一个反复 `GetByKey` 后读 `Annotations` 长度，
一个反复 reconcile。结束后检查 store 内部对象的 annotations 个数：

- 仍为 1 → `VERDICT: OK`
- 被改写 → `VERDICT: BUG`（退出码 3）

原记录（2026-11-21）没有用 `-race`（本机 Windows 不可用），而是用「共享对象是否被污染」这个不变量判定。
2026-11-25 已在 Linux 虚拟机上补跑检测器，见第 7 节。

## 5. 实测

buggy 3/3 显示 `annotations 从 1 个变成 2 个`；fixed 3/3 保持 1 个。
buggy 未触发 runtime 的 map 并发致命错误，说明本机调度下先命中的是不变量违反而非 map 检测。

## 6. 怎么重跑

```bash
bash run.sh
```

## 7. 竞争检测（2026-11-25，Ubuntu 18.04 虚拟机）

本机 Windows 上 `-race` 不可用（缺 race 运行时 DLL），2026-11-25 在虚拟机
`ubuntu1804-p4`（Ubuntu 18.04.6 / go1.27.3 / gcc 7.5 / 4 核）上补跑：

| 段 | 设置 | 结果 |
|---|---|---|
| 不变量 | 不带 `-race`，10 轮/侧 | buggy 10/10 BUG（annotations 1→2），fixed 0/10 |
| 竞争检测 | `-race`，100 轮/侧，`GORACE=halt_on_error=1` | **buggy 100/100，首次命中第 1 轮**；fixed 0/100 |

竞争点落在机制本身，不是旁支的偶然竞争：

```text
Read  at 0x... by goroutine 8:  main.main.func1()  buggy/main.go:71   len(obj.Annotations)
Write at 0x... by goroutine 9:  main.reconcile()   buggy/main.go:57   ns.Annotations[...] = "true"
```

fixed 侧 0/100，说明检测器报的确实是 DeepCopy 消除掉的那处访问。原始报告见
`logs/vm-1125/race/sample_buggy.log`。

重跑：`CASES=kubernetes-36377 RUNS=10 RACE_RUNS=100 bash ../run_race.sh`
汇总见 `results/vm-1125.txt`。
