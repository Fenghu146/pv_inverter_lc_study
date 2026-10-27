# -*- coding: utf-8 -*-
"""统一口径指标（与两份报告一致的 THD(2-50)/TDD/高频带 定义）

窗口：最后 200 ms（10 个工频周期），频率分辨率 5 Hz，矩形窗 DFT。
  THD(2-50)  = sqrt(Σ V_h², h=2..50) / V_1          （h 次谐波 100..2500 Hz）
  TDD        = sqrt(Σ V_h², h=2..50) / I_rated_rms  （对方第四轮修正口径）
  HF(>2kHz)  = sqrt(Σ 2.05kHz..fs/2 频段功率) / V_1
  Idc        = 窗口内并网电流平均值
  amp_err    = (I1 - I_ref)/I_ref
  phase_deg  = 电流基波相对电网电压基波的相位差
"""
import math
import numpy as np


def window_metrics(t, i_g, u_g, i_ref_amp, i_rated_rms,
                   win=0.2, f0=50.0):
    dt = t[1] - t[0]
    fs = 1.0/dt
    m = t >= (t[-1] - win)
    x = i_g[m] - np.mean(i_g[m])
    u = u_g[m] - np.mean(u_g[m])
    N = len(x)
    # 精确频率 DFT（避免栅栏效应；win 为整周期，等效 5 Hz 分辨率）
    n = np.arange(N)
    def phasor(sig, f):
        c = np.exp(-2j*np.pi*f*n/fs)
        return np.dot(sig, c)*2.0/N
    I1_c = phasor(x, f0)
    U1_c = phasor(u, f0)
    I1 = abs(I1_c)
    h_pow = 0.0
    hf_pow = 0.0
    for h in range(2, 51):
        h_pow += abs(phasor(x, h*f0))**2
    # >2 kHz 频段（平均模型下只有死区谐波尾）
    f_hi = 2050.0
    while f_hi < fs/2 - f0:
        hf_pow += abs(phasor(x, f_hi))**2
        f_hi += 5.0
    thd = math.sqrt(h_pow)/I1*100.0 if I1 > 0 else float("nan")
    tdd = math.sqrt(h_pow)/i_rated_rms*100.0
    hf = math.sqrt(hf_pow)/I1*100.0 if I1 > 0 else float("nan")
    idc = float(np.mean(i_g[m]))
    amp_err = (I1 - i_ref_amp)/i_ref_amp*100.0 if i_ref_amp else float("nan")
    phase = math.degrees(np.angle(I1_c*np.conj(U1_c)))
    return {"I1_A": I1, "amp_err_pct": amp_err, "phase_deg": phase,
            "THD_pct": thd, "TDD_pct": tdd, "HF_pct": hf, "Idc_A": idc}
