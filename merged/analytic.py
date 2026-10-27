# -*- coding: utf-8 -*-
"""A0 解析层（对应对方 L0/run_resonance 的纯数学部分，不依赖 Simulink）

  1) LCL/L 谐振振铃：线性网络状态空间 + 1 V 阶跃，测 v_C 振铃周期，
     与解析式 f0 = (1/2π)·sqrt((L+Lg)/(L·Lg·C)) 对比（15 工况）；
  2) 15-25 kHz 开关频段纹波衰减比 |i_g/v_ab|_L ÷ |i_g/v_ab|_LC（Lg 依赖）；
  3) 额定运行最小母线电压（基波压降口径）。
"""
import math
import os
import sys

import numpy as np
from scipy.linalg import expm

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from params_merged import P, D


def _ring_freq(L, Lg, C, Rd, Rf, Rg):
    """Π 型网络（两端理想电压源钳位）：v_ab=1V 阶跃、u_g=0，测电容电流振铃频率

    状态 [i_L, i_g, v_C]；v_PCC = v_C + Rd*(i_L - i_g)。
    振铃观测量用 i_C = i_L - i_g（稳态 0、振铃分量显著）；v_C 的阶跃响应
    在部分参数下不振铃（振荡模态留数小），不可用。
    自然频率解析式 f0 = (1/2π)·sqrt((L+Lg)/(L·Lg·C))（C 两端各经 L、Lg 接源）
    """
    A = np.array([[-(Rf + Rd)/L, Rd/L,      -1.0/L],
                  [Rd/Lg,        -(Rg + Rd)/Lg, 1.0/Lg],
                  [1.0/C,        -1.0/C,        0.0]])
    B = np.array([[1.0/L], [0.0], [0.0]])
    dt = 2e-6
    n = 3
    M = np.zeros((n + 1, n + 1))
    M[:n, :n] = A*dt
    M[:n, n:] = B*dt
    E = expm(M)
    Ad, Bd = E[:n, :n], E[:n, n:n+1]
    x = np.zeros(n)
    sig = []
    # 注意：系统含 τ≈20 ms 的慢实极点，须仿真足够长再取终值
    t_end = 0.15
    for _ in range(int(t_end/dt)):
        x = Ad@x + Bd.ravel()*1.0
        sig.append(x[0] - x[1])          # 振铃观测量 i_C
    vc = np.array(sig)
    vcf = vc[-int(20e-3/dt):].mean()
    y = vc - vcf
    peak = np.max(np.abs(y))
    # 过零（上升沿）有效性：附近 ±半周期窗口内的局部振幅须 >5% 峰值，
    # 防止衰减尾段数值噪声制造假过零
    half = int(2.5e-4/dt)
    zc = []
    for i in range(1, len(y)):
        if i > 20 and y[i-1] < 0 <= y[i]:
            lo, hi = max(0, i - half), min(len(y), i + half)
            if np.abs(y[lo:hi]).max() > 0.05*peak:
                zc.append(i)
    if len(zc) < 3:
        return float("nan"), _f0_analytic(L, Lg, C)
    periods = np.diff(zc[:5])*dt          # 用最初几个周期
    return 1.0/np.mean(periods), _f0_analytic(L, Lg, C)


def _f0_analytic(L, Lg, C):
    return (1.0/(2*math.pi))*math.sqrt((L + Lg)/(L*Lg*C))


def resonance_table():
    """L∈{1,1.5,2,3,4} mH × Lg∈{0.5,1,2} mH，Rd=1"""
    rows = []
    for L_mH in (1.0, 1.5, 2.0, 3.0, 4.0):
        for Lg_mH in (0.5, 1.0, 2.0):
            f_num, f_ana = _ring_freq(L_mH*1e-3, Lg_mH*1e-3, P["C"],
                                      P["Rd"], P["Rf"], P["Rg"])
            rows.append({"L_mH": L_mH, "Lg_mH": Lg_mH,
                         "f_res_analytic_Hz": f_ana,
                         "f_res_sim_Hz": f_num,
                         "err_pct": (f_num - f_ana)/f_ana*100.0})
    return rows


def hf_attenuation(Lg=1.0e-3, f_lo=15e3, f_hi=25e3, nf=21):
    """15-25 kHz 频段 |i_g/v_ab| 的 L vs LC 之比（频段内 RMS 平均）"""
    s_band = np.linspace(2*math.pi*f_lo, 2*math.pi*f_hi, nf)
    def gain_L(w):
        return 1.0/np.abs(P["Rf"] + P["Rg"] + 1j*w*(P["L"] + Lg))
    def gain_LC(w):
        # LC：Z_L 支路与 (C 串 Rd) 并联，再串 Lg
        Zc = P["Rd"] + 1.0/(1j*w*P["C"])
        Zp = Zc/(1.0 + Zc*(1j*w*P["L"] + P["Rf"]))  # 简化：先并后串推导
        Zp = (Zc*(P["Rf"] + 1j*w*P["L"]))/(Zc + P["Rf"] + 1j*w*P["L"])
        Zt = Zp + P["Rg"] + 1j*w*Lg
        return np.abs(1.0/Zt)*np.abs(Zp/(P["Rf"] + 1j*w*P["L"]))
    r = [gain_L(w)/gain_LC(w) for w in s_band]
    return {"Lg_mH": Lg*1e3, "atten_mean": float(np.mean(np.abs(r))),
            "atten_20k": float(np.abs(r[len(r)//2]))}


def vdc_min_rated():
    """额定最小母线电压：√2·Ug + ω(L+Lg)·Im_rated（基波压降口径，m_max 裕量另计）"""
    drop = D["wg"]*(P["L"] + P["Lg"])*D["Im_rated"]
    return {"vdc_min_V": D["Ug_pk"] + drop,
            "fund_drop_pct": drop/D["Ug_pk"]*100.0}
