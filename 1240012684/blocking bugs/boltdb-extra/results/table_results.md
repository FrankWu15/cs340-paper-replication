**Table 2.** Per-mode results, 10 independent trials per mode. SD is the sample standard deviation (n-1). Wall clock is measured outside the process with `date +%s%N` and therefore includes Go runtime startup.

| Mode | n | Runtime deadlock reported | Silent hang (timeout) | Wall clock (ms), mean +/- SD |
|---|---:|---:|---:|---:|
| Buggy (`buggy`) | 10 | 10/10 (100%) | 0% | 313.00 +/- 58.77 |
| Fix: move (`move`) | 10 | 0/10 (0%) | 0% | 132.40 +/- 3.69 |
| Fix: select (`select`) | 10 | 0/10 (0%) | 0% | 130.80 +/- 5.69 |
| Buggy + live (`live`) | 10 | 0/10 (0%) | 100% | 5053.40 +/- 6.43 |
