#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""make_synthetic_scope.py — 生成合成示波器 CSV，用于空跑数据管线

目的：hardware 未到之前，先把 `matlab/process_scope_csv.m` + `matlab/thd_metrics.m`
的**列名、单位、采样率、窗口长度**口径跑通，避免硬件到货第一天卡在"导出的 CSV 对不上"。

输出（默认 `data/experiments/_synthetic/`，该目录不入库）：
  SYNTH_L_35.csv       L 结构 35 % 功率点，THD 偏大（无死区补偿形态）
  SYNTH_L_65.csv       L 结构 65 % 功率点
  SYNTH_LC_65_Rd1.csv  LC 结构 65 %、R_d=1 Ω，THD 与 40 kHz 纹波都更低

CSV 列（与 process_scope_csv.m 约定一致）：
  t_s, i_g_A, v_g_V, fs_Hz   —— 第 1 列时间、第 2 列并网电流（固定）、fs_Hz 写在首行
合成信号 = 基波 50 Hz + 2~50 次谐波（按设定 THD）+ 40 kHz 边带 + 白噪声。

用法：
  python tools/make_synthetic_scope.py                 # 默认 500 kHz / 0.25 s
  python tools/make_synthetic_scope.py --fs 1e6 --dur 0.3
  python tools/make_synthetic_scope.py --dir data/experiments/_synthetic
"""
import argparse
import math
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 三个合成工况：(文件名, 基波峰值 A, THD %, 40 kHz 纹波峰峰 A, 说明)
CASES = [
    ("SYNTH_L_35.csv", 2.75, 5.0, 0.90, "L 35% 无死区补偿形态"),
    ("SYNTH_L_65.csv", 5.11, 3.0, 0.90, "L 65%"),
    ("SYNTH_LC_65_Rd1.csv", 5.11, 0.8, 0.06, "LC 65% + R_d=1Ω"),
]

FG = 50.0
N_HARM = 50
FSW2 = 40000.0


def build_signal(i1, thd_pct, ripple_pp, fs, dur, seed=20261103):
    """合成并网电流：基波 + 谐波（总有效值 = THD×基波）+ 40 kHz 边带 + 噪声。"""
    rng = np.random.default_rng(seed)
    n = int(round(fs * dur))
    t = np.arange(n) / fs
    w = 2 * math.pi * FG

    # 谐波：把 THD 总有效值按 1/h 衰减分配到 2..50 次
    hs = np.arange(2, N_HARM + 1)
    weights = 1.0 / hs
    weights /= math.sqrt(float(np.sum(weights ** 2)))
    target_rms = thd_pct / 100.0 * i1 / math.sqrt(2.0)
    phases = rng.uniform(0, 2 * math.pi, hs.size)

    x = i1 * np.sin(w * t)
    for h, wt, ph in zip(hs, weights, phases):
        amp = target_rms * math.sqrt(2.0) * wt
        x = x + amp * np.sin(h * w * t + ph)

    # 40 kHz 簇：载波 + ±50 Hz 边带，峰峰值按 ripple_pp 给定
    amp40 = ripple_pp / 2.0
    x = x + 0.6 * amp40 * np.sin(2 * math.pi * FSW2 * t)
    x = x + 0.2 * amp40 * np.sin(2 * math.pi * (FSW2 - FG) * t)
    x = x + 0.2 * amp40 * np.sin(2 * math.pi * (FSW2 + FG) * t)

    # 少量白噪声（0.02 % 基波峰值）
    x = x + rng.normal(0.0, 2e-4 * i1, n)
    return t, x


def write_csv(path, t, x, fs):
    vg = 36.0 * math.sqrt(2.0) * np.sin(2 * math.pi * FG * t)  # PCC 36 Vrms
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("t_s,i_g_A,v_g_V,fs_Hz\n")
        for k in range(t.size):
            f.write("%.7f,%.6f,%.4f,%d\n" % (t[k], x[k], vg[k], int(fs)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.path.join("data", "experiments", "_synthetic"))
    ap.add_argument("--fs", type=float, default=500e3)
    ap.add_argument("--dur", type=float, default=0.25)
    args = ap.parse_args()

    outdir = args.dir if os.path.isabs(args.dir) else os.path.join(ROOT, args.dir)
    os.makedirs(outdir, exist_ok=True)
    print("合成示波器 CSV → %s  (fs=%.0f Hz, 时长 %.3f s)" % (outdir, args.fs, args.dur))
    for name, i1, thd, rip, note in CASES:
        t, x = build_signal(i1, thd, rip, args.fs, args.dur)
        path = os.path.join(outdir, name)
        write_csv(path, t, x, args.fs)
        rms = float(np.sqrt(np.mean(x ** 2)))
        print("  %-22s %7d 行  %.2f MB  基波峰值 %.2f A  有效值 %.2f A  THD≈%.1f%%  %s"
              % (name, t.size, os.path.getsize(path) / 1e6, i1, rms, thd, note))
    print("下一步（在仓库根目录）：")
    print('  matlab -batch "cd(\'matlab\'); process_scope_csv(\'../%s\', %d)"'
          % (args.dir.replace(os.sep, "/"), int(args.fs)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
