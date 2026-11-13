**Table 1.** Paper vs. Ours on the same metric (fraction of reproduced blocking bugs reported by Go's built-in deadlock detector) under the same setting when applicable. The paper's scope is 21 bugs in six applications; ours is one bug at reduced scale, which the assignment explicitly permits if stated.

| Metric | Paper (ASPLOS'19) | Ours (reduced scale) |
|---|---|---|
| Reproduced blocking bugs | 21 (6 applications) | 1 (BoltDB#392) |
| Bugs reported by Go's deadlock detector | 2/21 (9.5%) | 1/1 (100%) |
| BoltDB#392 explicitly listed as detected (Table 8 / Sec. 5.3) | Yes | Yes |
| `Chan w/` category | 1/4 detected (25.0%) | 1/1 detected (100%) |
| Trials of BoltDB#392 | 1 (deterministic, stated in Sec. 5.3) | 10 |
| BoltDB#392 detection rate | 1/1 (100%) | 10/10 (100%) |
| Detection latency | not reported | 313.00 +/- 58.77 ms (wall clock) |
| Fixed variants deadlocking | not reported | 0/20 (`move`, `select`) |
