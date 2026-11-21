#!/usr/bin/env python3
"""make_comparison.py — 生成 gRPC-C vs gRPC-Go 的原语对照表（论文 §3.2 末段）。

两侧用**同一套**代码行/原始行定义，避免"Go 用代码行、C 用原始行"的口径混用。
计数本身分别来自：
    gRPC-C  count_primitives.py（gpr_mu_lock/unlock/trylock 调用点）
    gRPC-Go tools/goast（lock_calls + atomic + once + waitgroup + cond + chan + Pool）
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import tempfile
from pathlib import Path

SKIP = {"vendor", "third_party", ".git", "node_modules"}


def code_raw(path: Path) -> tuple[int, int]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return 0, 0
    code = raw = 0
    in_block = False
    for line in text.splitlines():
        raw += 1
        s = line.strip()
        if not s:
            continue
        if in_block:
            if "*/" in s:
                in_block = False
                rest = s.split("*/", 1)[1].strip()
                if rest and not rest.startswith("//"):
                    code += 1
            continue
        if s.startswith("/*"):
            if "*/" not in s:
                in_block = True
            else:
                rest = s.split("*/", 1)[1].strip()
                if rest and not rest.startswith("//"):
                    code += 1
            continue
        if s.startswith("//"):
            continue
        code += 1
    return code, raw


def go_metrics(root: Path, goast: str, include_tests: bool) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        tmp = Path(tf.name)
    cmd = [goast, "-root", str(root), "-json", str(tmp)]
    if include_tests:
        cmd.append("-include-tests")
    subprocess.run(cmd, check=True, capture_output=True)
    c = json.loads(tmp.read_text(encoding="utf-8"))
    tmp.unlink(missing_ok=True)

    code = raw = files = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP]
        for fn in filenames:
            if not fn.endswith(".go"):
                continue
            if not include_tests and fn.endswith("_test.go"):
                continue
            f = Path(dirpath) / fn
            a, b = code_raw(f)
            code += a
            raw += b
            files += 1

    sm = c["lock_calls"] + c["atomic"] + c["once"] + c["waitgroup"] + c["cond"]
    mp = c["chan_send"] + c["chan_recv"] + c.get("misc_pool", 0)
    return {
        "files": files, "code_lines": code, "raw_lines": raw,
        "usage": sm + mp,
        "types": sum(1 for k in ("lock_calls", "atomic", "once", "waitgroup",
                                "cond", "chan_send", "misc_pool") if c[k]),
        "counts": c,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--c-json", required=True, help="count_primitives.py 输出的 JSON")
    ap.add_argument("--go-repo", required=True)
    ap.add_argument("--goast", default="/tmp/goast")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    c = json.loads(Path(args.c_json).read_text(encoding="utf-8"))
    go = go_metrics(Path(args.go_repo).expanduser().resolve(), args.goast, False)
    go_t = go_metrics(Path(args.go_repo).expanduser().resolve(), args.goast, True)

    rows = [
        {"side": "gRPC-C", "version": c["version"], "primitive_types": 1,
         "usage_sites": c["lock_usage"],
         "code_kloc": round(c["code_lines"] / 1000, 1),
         "raw_kloc": round(c["raw_lines"] / 1000, 1),
         "per_kloc_code": round(c["lock_usage"] / (c["code_lines"] / 1000), 2),
         "per_kloc_raw": round(c["lock_usage"] / (c["raw_lines"] / 1000), 2)},
        {"side": "gRPC-Go", "version": "f6692351(2018-05-21)", "primitive_types": go["types"],
         "usage_sites": go["usage"],
         "code_kloc": round(go["code_lines"] / 1000, 1),
         "raw_kloc": round(go["raw_lines"] / 1000, 1),
         "per_kloc_code": round(go["usage"] / (go["code_lines"] / 1000), 2),
         "per_kloc_raw": round(go["usage"] / (go["raw_lines"] / 1000), 2)},
        {"side": "gRPC-Go(含测试)", "version": "f6692351(2018-05-21)",
         "primitive_types": go_t["types"], "usage_sites": go_t["usage"],
         "code_kloc": round(go_t["code_lines"] / 1000, 1),
         "raw_kloc": round(go_t["raw_lines"] / 1000, 1),
         "per_kloc_code": round(go_t["usage"] / (go_t["code_lines"] / 1000), 2),
         "per_kloc_raw": round(go_t["usage"] / (go_t["raw_lines"] / 1000), 2)},
        {"side": "论文 gRPC-C", "version": "-", "primitive_types": 1, "usage_sites": 746,
         "code_kloc": "", "raw_kloc": 140.8, "per_kloc_code": "", "per_kloc_raw": 5.3},
        {"side": "论文 gRPC-Go", "version": "-", "primitive_types": 8, "usage_sites": 786,
         "code_kloc": 53.1, "raw_kloc": "", "per_kloc_code": 14.8, "per_kloc_raw": ""},
    ]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    print(f"[done] -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
