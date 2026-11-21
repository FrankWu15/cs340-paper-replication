# kubernetes#30872 —— 持锁调用 HasSynced()，回调再次拿同一把锁

| 项 | 值 |
|---|---|
| 类型 | blocking / shared_memory |
| 修复 commit | `681d153050930f67945fc308ad10566ec299edd5` |
| 形态 | minimal（复刻 ClustersSynced 的持锁检查） |
| 判定 | buggy 3/3 DEADLOCK，fixed 0/3 |

## 1. 症状

federation controller 在集群数量变化时永久卡住，日志停在同步检查附近，
之后所有依赖该 informer 的 reconcile 全部停摆。

## 2. 机理

`federation/pkg/federation-controller/util/federated_informer.go`：

```go
func (fs *federatedStoreImpl) ClustersSynced(clusters []*Cluster) bool {
    fs.federatedInformer.Lock()
    defer fs.federatedInformer.Unlock()
    for _, cluster := range clusters {
        if targetInformer, found := fs.federatedInformer.targetInformers[cluster.Name]; found {
            if !targetInformer.HasSynced() {   // ← 回调会拿同一把锁
```

`HasSynced()` 触发 informer 的同步回调，回调走 `NotifyClusterUpdate`
一类的更新路径，又要 `federatedInformer.Lock()`。`sync.Mutex` 不可重入，自死锁。

## 3. 修复

补丁把锁的范围缩小到「只取列表」：锁内把需要检查的 informer 拷进切片，
解锁后逐个 `HasSynced()`。

```go
okSoFar, informersToCheck := func() (bool, []informer) {
    fs.federatedInformer.Lock()
    defer fs.federatedInformer.Unlock()
    ...
}()
if !okSoFar { return false }
for _, in := range informersToCheck { if !in.HasSynced() { return false } }
```

## 4. 判定口径

`ClustersSynced` 放 goroutine 里，主 goroutine 等 3 秒：

- 返回 → `VERDICT: OK`
- 超时 → `VERDICT: DEADLOCK`（退出码 2）

## 5. 实测

buggy 3/3 卡死；fixed 3/3 返回 `synced=true updates=2`（两个 informer 各触发一次回调）。

## 6. 怎么重跑

```bash
bash run.sh
```

真实源码复现需要 Linux + k8s 1.5 的构建环境；当前机器不具备，故为 minimal。
