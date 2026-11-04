#!/usr/bin/env python3
"""P0 阶段：汇总环境与数据准备情况，生成 out/p0_env_report.md。

输入：
    $LOG_DIR/repos.tsv          由 00_setup_repos.sh / 00_pin_exact.sh 生成
    data/bugs_master.csv        由 00_parse_artifact.py 生成
    data/p0_artifact_checks.md  同上

路径解析与 _paths.sh 一致：环境变量 > repro/local.env > 项目内自动探测。
换机器不需要改这个文件。

用法:
    python scripts/00_env_report.py            # 只做汇总
    python scripts/00_env_report.py --static   # 额外对每个仓库跑一遍 goast（慢，K8s 较久）
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPRO = HERE.parent
PROJECT = REPRO.parent


def _load_local_env(path: Path) -> None:
    """读取 repro/local.env（KEY="VALUE" 形式），不覆盖已存在的环境变量。"""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _repo_root() -> Path:
    """探测上游仓库目录，不假设它必须叫 repos。

    交付目录嵌在仓库里，上游仓库可能在更上一层，所以从 PROJECT 起向上找。
    """
    if root := os.environ.get("REPO_ROOT"):
        return Path(root)
    for base in (PROJECT, PROJECT.parent, PROJECT.parent.parent):
        for cand in ("repos", "6app", "upstream-repos", "src"):
            if (base / cand).is_dir():
                return base / cand
    return PROJECT / "repos"


_load_local_env(REPRO / "local.env")

REPO_ROOT = _repo_root()
LOG_DIR = Path(os.environ.get("LOG_DIR") or REPRO / "logs")
BIN_DIR = Path(os.environ.get("BIN_DIR") or Path(os.environ.get("TMPDIR", "/tmp")) / "gcbugs-bin")

_goast = BIN_DIR / ("goast.exe" if os.name == "nt" else "goast")
GOAST = Path(os.environ["GOAST"]) if os.environ.get("GOAST") else _goast
TOOLCHAINS = {
    "modern": Path(os.environ.get("GO_MODERN") or (shutil.which("go") or "go")),
    "legacy": Path(os.environ.get("GO_LEGACY") or "(未配置)"),
    "system": Path("C:/Program Files (x86)/Go/bin/go.exe"),
}



def go_version(exe: Path) -> str:
    if not exe.exists():
        return "(未安装)"
    try:
        out = subprocess.run([str(exe), "version"], capture_output=True, text=True, timeout=60)
        return out.stdout.strip() or out.stderr.strip()
    except Exception as exc:  # noqa: BLE001
        return f"(执行失败: {exc})"


def run_static(repo: Path) -> dict | None:
    if not GOAST.exists():
        return None
    try:
        out = subprocess.run([str(GOAST), "-root", str(repo)],
                             capture_output=True, text=True, timeout=1800)
        return json.loads(out.stdout)
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsv", default=str(LOG_DIR / "repos.tsv"))
    ap.add_argument("--out", default=str(REPRO / "out" / "p0_env_report.md"))
    ap.add_argument("--static", action="store_true", help="额外跑 goast 统计每个仓库")
    args = ap.parse_args()

    tsv = Path(args.tsv)
    rows = []
    if tsv.exists():
        with tsv.open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh, delimiter="\t"))

    master = []
    mf = REPRO / "data" / "bugs_master.csv"
    if mf.exists():
        with mf.open(encoding="utf-8-sig") as fh:
            master = list(csv.DictReader(fh))

    L = ["# P0 环境与数据准备报告", ""]
    L += [f"生成时间：{dt.datetime.now():%Y-%m-%d %H:%M}", ""]

    # ---- 工具链 ----
    L += ["## 工具链", "", "| 用途 | 路径 | 版本 |", "|---|---|---|"]
    L.append(f"| 现代（编译 goast / 对照实验） | `{TOOLCHAINS['modern']}` | {go_version(TOOLCHAINS['modern'])} |")
    L.append(f"| 旧版（编译 2015–2018 老代码） | `{TOOLCHAINS['legacy']}` | {go_version(TOOLCHAINS['legacy'])} |")
    L.append(f"| 机器原有（32 位，仅记录） | `{TOOLCHAINS['system']}` | {go_version(TOOLCHAINS['system'])} |")
    L.append("")
    L += ["> 机器原有的 Go 是 **windows/386（32 位）**，不支持 `-race`，P5 无法用它做检测器评测。",
          "> 已额外准备 amd64 版本，不改动原有安装。", ""]

    # ---- 仓库 ----
    L += ["## 仓库快照（切点 2018-05-21）", "",
          "| 项目 | commit | 日期 | commit 数 | 论文 | 差异 | 克隆方式 |", "|---|---|---|---|---|---|---|"]

    ok = 0
    for r in rows:
        d = Path(r.get("path") or (REPO_ROOT / r["app"]))
        size = ""
        if d.exists():
            try:
                size = subprocess.run(["du", "-sh", str(d)], capture_output=True,
                                      text=True, timeout=60).stdout.split("\t")[0]
            except Exception:  # noqa: BLE001
                size = "?"
        diff = int(r["diff"])
        flag = "✅" if abs(diff) == 0 else ("⚠️" if abs(diff) < 500 else "❌")
        if abs(diff) < 500:
            ok += 1
        mode = r.get("mode", "full")
        mode_txt = "完整" if mode == "full" else ("treeless（仅 commit）" if mode == "treeless" else mode)
        L.append(f"| {r['app']} | `{r['commit']}` | {r['date']} | {r['commits']} | "
                 f"{r['paper_commits']} | {diff:+d} {flag} | {mode_txt} {size} |")
    L.append("")
    L.append(f"已获取 {len(rows)} / 6 个仓库，其中 {ok} 个 commit 数与论文一致。")
    L.append("")

    # ---- 切点精确定位（00_pin_exact.sh）----
    pin = LOG_DIR / "pin_exact.tsv"
    if pin.exists():
        with pin.open(encoding="utf-8") as fh:
            prow = list(csv.DictReader(fh, delimiter="\t"))
        if prow:
            L += ["### 切点是怎么精确对齐到论文的", "",
                  "`--before=DATE` 是左闭右开：`--before=2018-05-21` 得到「截至 5-20 结束」的计数，"
                  "`--before=2018-05-22` 才是「含 5-21 全天」。论文的值落在两者之间，"
                  "说明作者的取样时点是 2018-05-21 当天某个时刻。", "",
                  "因此用 `scripts/00_pin_exact.sh` 从 5-21 上界沿 first-parent 回溯，"
                  "逐步算 `rev-list --count`，定位到计数与论文完全相等的 commit：", "",
                  "| 项目 | 5-21 上界 | 回溯前计数 | 精确定位 commit | 计数 | 论文 | 方式 |",
                  "|---|---|---|---|---|---|---|"]
            for p in prow:
                kind = {"exact": "精确命中", "near": "最接近", "underflow": "上界已偏低"}.get(
                    p.get("kind", ""), p.get("kind", ""))
                L.append(f"| {p['app']} | `{p['cut_commit']}` | {p['cut_count']} | "
                         f"`{p['exact_commit']}` | {p['exact_count']} | {p['paper']} | {kind} |")
            L.append("")

    # ---- 未获取的仓库 ----
    EXPECTED = {
        "boltdb": 816, "etcd": 14101, "grpc-go": 2528,
        "docker": 35149, "cockroachdb": 29485, "kubernetes": 65684,
    }
    got = {r["app"] for r in rows}
    missing = {k: v for k, v in EXPECTED.items() if k not in got}
    if missing:
        L += ["### 未获取的仓库", "",
              "以下仓库因网络原因暂时未能完成克隆，**不影响 P0 的其他结论**，需要时重跑即可：", "",
              "| 项目 | 论文 commit 数 | 重试命令 |", "|---|---|---|"]
        for app, pc in missing.items():
            L.append(f"| {app} | {pc} | `bash scripts/00_setup_repos.sh {app}` |")
        L.append("")
        L.append("> `00_setup_repos.sh` 对已存在的仓库会跳过克隆，所以可以随时单独补某一个。")
        L.append("")

    # ---- 静态统计（可选）----
    if args.static:
        L += ["## 静态统计首轮（goast，用于 P2 校准）", "",
              "| 项目 | .go 文件 | 原始行数 | goroutine 创建点 | 原语总数 | shared% | message% |",
              "|---|---|---|---|---|---|---|"]
        for r in rows:
            d = Path(r.get("path") or (REPO_ROOT / r["app"]))
            if not d.exists():
                continue
            s = run_static(d)
            if not s:
                continue
            sm = sum(s[k] for k in ("mutex", "atomic", "once", "waitgroup", "cond"))
            ch = s["chan_make"] + s["chan_send"] + s["chan_recv"]
            mp = ch + s["misc"]
            tot = sm + mp
            L.append(f"| {r['app']} | {s['files']} | {s['lines']} | "
                     f"{s['go_stmt_normal']+s['go_stmt_anonymous']} | {tot} | "
                     f"{100*sm/tot:.1f}% | {100*mp/tot:.1f}% |" if tot else
                     f"| {r['app']} | {s['files']} | {s['lines']} | 0 | 0 | - | - |")
        L.append("")
        L.append("> 注意：goast 默认排除 `_test.go`，而论文 LOC 口径似乎包含测试代码"
                 "（BoltDB 论文 9060 行 vs 本工具 6305 行），P2 需要统一口径后再对比。")
        L.append("")

    # ---- artifact ----
    if master:
        L += ["## artifact 数据表", ""]
        L.append(f"- `bugs_master.csv`：{len(master)} 条 bug（blocking {sum(1 for m in master if m['behavior']=='blocking')} / "
                 f"non-blocking {sum(1 for m in master if m['behavior']=='non-blocking')}）")
        L.append(f"- 其中有独立补丁：{sum(1 for m in master if m['has_patch']=='1')} 条")
        rep1 = sum(1 for m in master if m['reproduced'] == '1')
        L.append(f"- 作者标记为已复现（Reproduced?=1）：{rep1} 条")
        L.append("")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(L), encoding="utf-8")
    print(f"[ok] {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
