# -*- coding: utf-8 -*-
"""sitl_matrix.py — 一键跑 SITL 对比矩阵并落表

四组工况（L ／ LC-Rd0 ／ LC-Rd1 ／ LC-Rd2.2），开关级模型 + 子步连续波形记录，
输出 results/tables/SITL_core.csv，供 docs/17 引用。默认 1.2 s 一段（约 40 s/组）。

用法：
  python tools/sitl_matrix.py                 # 全跑，落 results/tables/SITL_core.csv
  python tools/sitl_matrix.py --dur 2.0       # 跑更长（结果更稳，耗时线性增长）
  python tools/sitl_matrix.py --cases L LC:1  # 只跑指定工况
"""
import argparse
import csv
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.path.insert(0, os.path.join(ROOT, "python"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import sitl  # noqa: E402

CASES = [("L", 0.0), ("LC", 0.0), ("LC", 1.0), ("LC", 2.2)]
COLS = ["structure", "Rd_ohm", "dur_s", "I1_A", "amp_err_pct", "phase_deg",
        "THD_pct", "HF_pct", "Idc_A", "sw40k_A", "sw40k_pct_fund",
        "band15_25k_A", "fs_hz", "state_final"]


def parse_cases(txt):
    if not txt:
        return CASES
    out = []
    for item in txt.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            s, rd = item.split(":")
            out.append((s.upper(), float(rd)))
        else:
            out.append((item.upper(), 0.0))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dur", type=float, default=1.2)
    ap.add_argument("--nsub", type=int, default=40)
    ap.add_argument("--cases", default="")
    ap.add_argument("--out", default=os.path.join(ROOT, "results", "tables", "SITL_core.csv"))
    args = ap.parse_args()

    stale, why = __import__("sitl_build").is_stale()
    if stale:
        print("SITL 库过期（%s），先编译" % why)
        if not __import__("sitl_build").build():
            return 1

    rows = []
    for struct, rd in parse_cases(args.cases):
        print("\n--- %s / Rd=%.1f ---" % (struct, rd))
        r = sitl.run(struct=struct, mode="sw", dur=args.dur, rd=rd, nsub=args.nsub,
                     log_sub=True)
        if "THD_pct" not in r:
            print("！该工况未取到稳态指标，跳过落表")
            continue
        rows.append([struct, "%.1f" % rd, "%.2f" % args.dur,
                     "%.4f" % r["I1_A"], "%.3f" % r["amp_err_pct"], "%.3f" % r["phase_deg"],
                     "%.3f" % r["THD_pct"], "%.3f" % r["HF_pct"], "%.5f" % r["Idc_A"],
                     "%.5f" % r["sw40k_A"], "%.4f" % (r["sw40k_A"] / r["I1_A"] * 100.0),
                     "%.5f" % r["band15_25k_A"], "%.0f" % r["fs_hz"],
                     sitl.R_NAME.get(int(r["rows"][-1, 15]), "")])

    if not rows:
        print("没有可用结果，未写表")
        return 1
    out = args.out
    d = os.path.dirname(out)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLS)
        w.writerows(rows)
    print("\n已写 %s（%d 行）" % (os.path.relpath(out, ROOT), len(rows)))

    # 顺手算 LC 相对 L 的 40 kHz 衰减比，和 A5 的解析值对照
    base = None
    for row in rows:
        if row[0] == "L":
            base = float(row[9])
    if base:
        print("40 kHz 衰减比（相对 L）：")
        for row in rows:
            if row[0] == "LC" and float(row[9]) > 0:
                print("  Rd=%.1f Ω → %.1f×" % (float(row[1]), base / float(row[9])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
