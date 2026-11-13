# GitHub Submission Checklist (Git History Check, 30% + 25% + 25% + 10% + 10%)

The **whole `boltdb392-replication/` directory is the code to upload** — not
just `report/report.pdf`. This is the repository root: 95 files, ~473 KB,
largest file ~35 KB, no build output, no credentials, no file > 50 MB.
`.gitattributes` forces LF line endings so the shell scripts still run on
Linux when a teammate commits from Windows.

| What | Where |
|---|---|
| Go source (the reproduction) | `cmd/repro/main.go`, `internal/harness/harness.go`, `go.mod` |
| Vendored original application (MIT) | `third_party/bolt/` incl. `LICENSE`, `UPSTREAM_COMMIT.txt` |
| Experiment / analysis / report scripts | `scripts/*.sh`, `scripts/*.py` |
| Build + environment pinning | `Makefile`, `setup.sh`, `Dockerfile`, `.gitignore` |
| Evidence (commit these on purpose) | `results/` (41 raw logs, CSVs, 3 figures, `environment.txt`) |
| Documentation + report | `README.md`, `docs/`, `report/report.md`, `report/report.pdf` |

## 1. Local state (already prepared)

`git init` has been run in this directory and all files were staged with
`git add .`. Nothing has been committed yet: **commit messages must contain the
student ID and full name of the committing member**, which only your group can
supply. Check with `git status --short`.

## 2. First commit — replace the placeholders

```bash
cd boltdb392-replication
git config user.name  "YOUR FULL NAME"
git config user.email "YOUR GITHUB EMAIL"

git commit -m "<STUDENT_ID> <FULL_NAME>: add BoltDB#392 reproduction harness, 40-trial experiment and report"
```

The message must contain **both** the student ID and the full name, and must
describe a real change (whitespace/typo-only commits do not count).

## 3. Create the remote and push

```bash
git branch -M main
git remote add origin https://github.com/<your-group>/<repo>.git
git push -u origin main
```

Then submit the group information **and the repository link** in the course
form: <https://v.wjx.cn/vm/rZCQLSE.aspx>.

## 4. Weekly commits (checked every Sunday 23:59)

- Today is Thu 5 Nov 2026; the **first check is Sun 9 Nov 2026 23:59**.
- At least one meaningful commit per week until the presentation on
  1 Dec 2026. Late commits count for the following week only; a missed week
  cannot be recovered.
- Every member must push substantive commits **from their own GitHub account**,
  each message containing that member's student ID and full name.
- A sensible split for the remaining weeks (one topic per week, no filler):

| Week | Meaningful change |
|---|---|
| before 9 Nov | initial harness + experiment + report (this commit) |
| before 16 Nov | extension experiment / extra repetition runs / new figure |
| before 23 Nov | critical analysis update, Contribution Statement filled in |
| before 30 Nov | final review, README polish, `v1.0` tag |

## 5. Final tag

```bash
git tag v1.0
git push origin v1.0
```

## 6. Rules the repository already satisfies

- `.gitignore` excludes `bin/`; no build outputs, disk images, traces > 50 MB
  or credentials are staged.
- All raw logs and results are committed for traceability (intentional).
- Original code is credited: `third_party/bolt/LICENSE`, starting commit in
  `third_party/bolt/UPSTREAM_COMMIT.txt`; all modified/added files are listed
  in `README.md`.
- Pinned OS, kernel, compiler and tool versions: `results/environment.txt`.
- README alone is enough to rebuild and rerun on a clean Linux machine:
  `bash setup.sh && make build && make verify && make run`.

## Important

An AI assistant cannot create commits or push on your behalf: the grading
requires each member's own GitHub account and their own student ID in the
commit message. Run the commands above from your own account.
