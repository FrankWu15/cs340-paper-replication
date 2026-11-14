# Real Upstream Source Evidence

Every file in this directory is extracted **verbatim** from the upstream etcd
git history (https://github.com/etcd-io/etcd) at the exact commits referenced
by the ASPLOS'19 paper's bug table. They prove the minimal reproductions in
`internal/bugs/` are faithful extractions of the real bugs, not hand-written
equivalents.

## etcd#6873 — watchBroadcasts.stop deadlock (lock + channel in critical section)

| Role | Commit | File |
|---|---|---|
| Buggy parent | `377f19b0031f9c0aafe2aec28b6f9019311f52f9` | `proxy/grpcproxy/watch_broadcasts.go` |
| Fix commit    | `7618fdd1d642e47cac70c03f637b0fd798a53a6e` | `proxy/grpcproxy/watch_broadcasts.go` |

The fix moves one line: in `stop()`, `wbs.mu.Unlock()` is relocated from before
`close(wbs.updatec)` to after it (just before `<-wbs.donec`). The buggy version
holds `mu` across `close(updatec)` and the `<-wbs.donec` wait, while the
coalesce loop needs `mu` to finish -> deadlock. This is the same
*lock + channel in critical section* family as `boltdb#392`.

## double-lock — httpClusterClient.Sync self-deadlock (double RWMutex lock)

| Role | Commit | File |
|---|---|---|
| Buggy parent | `83930ac113bf9f30f69ad6cbb33878d75f9684fe` | `client/client.go` |
| Fix commit    | `ae062a0825a4100d0cf9ac7c8bb0fa1ca69c6814` | `client/client.go` |

The fix moves `c.Lock()`/`defer c.Unlock()` from before `mAPI.List(ctx)` to
after it. The buggy version holds `c.Lock()` while
`List` -> `c.Do` -> `c.RLock()` requests the **same RWMutex** -> self-deadlock.
This is the *shared-memory / double-lock* family (same as the Kubernetes bugs).

## Reproducibility

Run `bash scripts/extract_real_source.sh` to regenerate every file. Requires a
local clone of etcd at `$HOME/etcd-src` whose history contains all four commits
(they are all reachable from current `main`).
