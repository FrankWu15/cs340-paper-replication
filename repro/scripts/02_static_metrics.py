#!/usr/bin/env python3
"""P2 阶段：调用 tools/goast 统计一个仓库的 goroutine 创建点与并发原语用量，
并做 KLOC 归一化，输出可作为论文 Table 2 / Table 4 一行的结果。

用法:
    python scripts/02_static_metrics.py --repo vendor/etcd --app etcd \
        --out out/static_etcd.json

前置: 需要 Go 工具链（go run），或先 `cd tools/goast && go build -o ../../bin/goast`
     然后用 --goast-cmd 指向编译好的二进制，避免每个仓库都重新编译。
"""
from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPRO = HERE.parent
# 在 repro/ 目录下执行，保证 go.mod 生效（tools/goast 只用标准库）
DEFAULT_GOAST = "go run ./tools/goast"


def run_goast(cmd: str, repo: Path, include_tests: bool, skips: list[str]) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        tmp = Path(tf.name)
    args = shlex.split(cmd) + ["-root", str(repo), "-json", str(tmp)]
    if include_tests:
        args.append("-include-tests")
    for s in skips:
        args += ["-skip", s]

    proc = subprocess.run(args, capture_output=True, text=True, cwd=str(REPRO))
    if proc.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"goast 失败:\n{proc.stderr.strip()}")
    data = json.loads(tmp.read_text(encoding="utf-8"))
    tmp.unlink(missing_ok=True)
    return data


def count_kloc(repo: Path) -> tuple[float, str]:
    """优先用 cloc 统计 Go 代码行（排除注释/空行），与论文的 LOC 口径更接近。"""
    if shutil.which("cloc"):
        proc = subprocess.run(
            ["cloc", "--json", "--quiet", "--include-lang=Go", str(repo)],
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            try:
                info = json.loads(proc.stdout)
                return info.get("Go", {}).get("code", 0) / 1000.0, "cloc"
            except json.JSONDecodeError:
                pass
    if shutil.which("gocloc"):
        proc = subprocess.run(["gocloc", "--json", str(repo)], capture_output=True, text=True)
        if proc.returncode == 0:
            try:
                info = json.loads(proc.stdout)
                return info.get("total", {}).get("code", 0) / 1000.0, "gocloc"
            except json.JSONDecodeError:
                pass
    return 0.0, "unavailable"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--app", required=True)
    ap.add_argument("--out", required=True, help="输出 JSON")
    ap.add_argument("--goast-cmd", default=DEFAULT_GOAST)
    ap.add_argument("--include-tests", action="store_true")
    ap.add_argument("--skip", action="append", default=[], help="额外跳过目录，可重复")
    args = ap.parse_args()

    repo = Path(args.repo).expanduser().resolve()
    if not repo.is_dir():
        print(f"[x] 目录不存在: {repo}", file=sys.stderr)
        return 2

    print(f"[..] 统计 {args.app} ({repo})")
    counts = run_goast(args.goast_cmd, repo, args.include_tests, args.skip)

    kloc, kloc_src = count_kloc(repo)
    if kloc == 0:  # 退回原始行数，并在结果里标注，避免静默失真
        kloc = counts["lines"] / 1000.0
        kloc_src = "raw_lines(fallback)"

    sm = counts["mutex"] + counts["atomic"] + counts["once"] + counts["waitgroup"] + counts["cond"]
    chan = counts["chan_make"] + counts["chan_send"] + counts["chan_recv"]
    mp = chan + counts["misc"]
    total = sm + mp
    gsites = counts["go_stmt_normal"] + counts["go_stmt_anonymous"]

    def pct(v: int) -> float:
        return round(100.0 * v / total, 2) if total else 0.0

    result = {
        "app": args.app,
        "repo": str(repo),
        "kloc": round(kloc, 1),
        "kloc_source": kloc_src,
        "raw_counts": counts,
        # Table 2
        "goroutine_sites_total": gsites,
        "goroutine_sites_normal": counts["go_stmt_normal"],
        "goroutine_sites_anonymous": counts["go_stmt_anonymous"],
        "goroutine_sites_per_kloc": round(gsites / kloc, 3) if kloc else None,
        # Table 4
        "primitives_total": total,
        "shared_memory_pct": pct(sm),
        "message_passing_pct": pct(mp),
        "pct": {
            "mutex": pct(counts["mutex"]),
            "atomic": pct(counts["atomic"]),
            "once": pct(counts["once"]),
            "waitgroup": pct(counts["waitgroup"]),
            "cond": pct(counts["cond"]),
            "chan": pct(chan),
            "misc": pct(counts["misc"]),
        },
        "primitives_per_kloc": round(total / kloc, 2) if kloc else None,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"[ok] {args.app}: KLOC={result['kloc']}({kloc_src}) "
        f"goroutine 创建点={gsites} ({result['goroutine_sites_per_kloc']}/KLOC) "
        f"原语={total} 共享内存={result['shared_memory_pct']}% 消息传递={result['message_passing_pct']}%"
    )
    print(f"     -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
