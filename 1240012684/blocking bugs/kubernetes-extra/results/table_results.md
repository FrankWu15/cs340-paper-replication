**Table K1.** Minimal Kubernetes blocking-bug reproductions, 20 independent trials per group. SD is the sample standard deviation (n-1). Wall clock measured outside the process with `date +%s%N`.

| Bug | Mode | n | Deadlock reported | Wall clock (ms), mean +/- SD |
|---|---|---:|---:|---:|
| double-rlock | buggy | 20 | 20/20 (100%) | 236.30 +/- 37.68 |
| double-rlock | fixed | 20 | 0/20 (0%) | 128.05 +/- 8.00 |
| miss-unlock | buggy | 20 | 20/20 (100%) | 188.50 +/- 53.08 |
| miss-unlock | fixed | 20 | 0/20 (0%) | 125.85 +/- 6.17 |
