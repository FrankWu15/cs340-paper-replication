# etcd Reproduction Results

| Bug | Mode | Trials | Deadlocks detected | Elapsed ms (mean ± SD) |
|---|---|---:|---:|---|
| doublelock | buggy | 20 | 20/20 | n/a (deadlock) |
| doublelock | fixed | 20 | 0/20 | 0.75 ± 0.19 |
| etcd6873 | buggy | 20 | 20/20 | n/a (deadlock) |
| etcd6873 | fixed | 20 | 0/20 | 0.86 ± 0.42 |
