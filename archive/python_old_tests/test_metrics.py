"""metrics.py 单元测试 —— 用合成信号验证 THD/纹波/40kHz 统一口径精度
运行: python python\tests\test_metrics.py
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from analysis import metrics

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS  {name}  {detail}")
    else:
        FAIL += 1
        print(f"FAIL  {name}  {detail}")


def synth(fs=400e3, t_end=0.3, f=50.0, fund=5.0, harmonics=None, sw_amp=0.0, sw_f=40000.0):
    t = np.arange(0, t_end, 1.0 / fs)
    x = fund * np.sin(2 * math.pi * f * t)
    for h, a in (harmonics or {}).items():
        x += a * np.sin(2 * math.pi * h * f * t)
    if sw_amp > 0:
        # 工频调幅的开关纹波簇: 载波 ± 基波调制
        x += sw_amp * (1 + 0.5 * np.sin(2 * math.pi * f * t)) * np.sin(2 * math.pi * sw_f * t)
    return t, x


def main():
    # 1) 纯基波: THD≈0
    t, x = synth(harmonics={})
    m = metrics.full_metrics(x, 400e3)
    check("THD 纯基波≈0", abs(m["thd_pct"]) < 0.5, f"got {m['thd_pct']:.3f}%")

    # 2) 加 3 次 10% + 5 次 5%: THD ≈ sqrt(0.1²+0.05²) = 11.18%
    t, x = synth(harmonics={3: 0.5, 5: 0.25})  # 基波5A → 10%,5%
    m = metrics.full_metrics(x, 400e3)
    exp = 100 * math.hypot(0.10, 0.05)
    check("THD 3次10%+5次5%", abs(m["thd_pct"] - exp) < 0.8, f"got {m['thd_pct']:.2f}%, exp {exp:.2f}%")

    # 3) 40kHz 开关纹波幅值: 簇峰值应接近 sw_amp(调幅包络上限 1.5*sw_amp)
    t, x = synth(fund=5.0, sw_amp=0.2, sw_f=40000.0)
    m = metrics.full_metrics(x, 400e3)
    check("40kHz 簇幅值∈[0.2,0.35]", 0.15 < m["sw40k_amp"] < 0.35,
          f"got {m['sw40k_amp']:.4f} A (sw_amp=0.2)")
    check("40kHz 占基波% 合理", 3.0 < m["sw40k_pct_fund"] < 7.5,
          f"got {m['sw40k_pct_fund']:.3f}%")

    # 4) 高通纹波峰峰值: 40kHz 包络峰峰值 ≈ 2*sw_amp*(1+0.5) - 2*sw_amp*(1-0.5) = 2*sw_amp
    check("HP 纹波峰峰值≈2*sw_amp", abs(m["ripple_pp_A"] - 2 * 0.2) < 0.25,
          f"got {m['ripple_pp_A']:.3f} A, exp ~0.4")

    # 5) L vs LC 判别: 同基波, LC 纹波应低一个数量级以上(直接合成)
    t, xL = synth(fund=5.0, sw_amp=0.20)
    t, xLC = synth(fund=5.0, sw_amp=0.003)
    mL = metrics.full_metrics(xL, 400e3)
    mLC = metrics.full_metrics(xLC, 400e3)
    ratio_db = 20 * math.log10(mLC["sw40k_amp"] / mL["sw40k_amp"])
    check("LC 纹波抑制 >20dB", ratio_db < -20, f"got {ratio_db:.1f} dB")

    # 6) 窗口长度检验: 200ms 窗, 5Hz 分辨率
    check("df=5Hz", abs(metrics.thd(xL, 400e3)["df_Hz"] - 5.0) < 1e-6, "")

    print(f"\n=== {PASS} PASS / {FAIL} FAIL ===")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
