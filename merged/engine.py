# -*- coding: utf-8 -*-
"""合并版仿真引擎 —— 对方算法的忠实 Python 移植（平均模型 + 功率级死区误差注入）

移植清单（出处 = merged/reference/control/*.m）：
  pr_design/pr_step      准 PR 预畸变 Tustin biquad + 饱和条件冻结
  pll_step               T/4 延时单相 PLL（100 拍循环队列）
  current_ctrl_step      电流环（LC 电容电流前馈 + 电网电压前馈 + 调制限幅）
  deadtime_step          功率级平均死区误差 m_eff = m - td_norm*sign(i_L)
  deadtime_comp_step     控制器补偿 m_comp = m + td_norm*s(i_ref)，s=sign 或 sat
  mppt_step              10 ms 滑动平均 + P&O(1V/0.5s) + 电压 PI(条件冻结)
  pv_current             PV 单二极管牛顿迭代

模型层级与对方 L2/L5-average 对应：平均功率级 + 死区电压误差在功率级注入、
控制器保持干净（补偿显式建模）。不含开关纹波（20 kHz 开关簇与载波相位
采样偏置不在本层口径内，对方 L3/L5 开关层数据仍然有效）。
"""
import math
import os
import sys

import numpy as np
from scipy.linalg import expm

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from params_merged import P, D

TS = D["Ts"]                 # 控制拍 50 µs
NSUB = P["nsub"]             # 每拍子步数
DT = TS / NSUB
WG = D["wg"]
UG_PK = D["Ug_pk"]


# ------------------------------------------------ 准 PR（pr_design/pr_step）
def pr_design(Kp, Kr, f_bw, f0, Ts):
    w0 = 2*math.pi*f0
    wc = 2*math.pi*f_bw
    k = w0/math.tan(w0*Ts/2.0)
    D0 = k*k + 2*wc*k + w0*w0
    D1 = -2*k*k + 2*w0*w0
    D2 = k*k - 2*wc*k + w0*w0
    N0 = 2*Kr*wc*k
    return {"Kp": Kp, "b0": N0/D0, "b1": 0.0, "b2": -N0/D0,
            "a1": D1/D0, "a2": D2/D0, "vmax": P["vmax_pr"]}


def pr_step(e, st, c):
    """DFII Transposed；输出饱和且误差仍同向时冻结谐振状态"""
    yres = c["b0"]*e + st["s1"]
    v_raw = c["Kp"]*e + yres
    if v_raw > c["vmax"]:
        v = c["vmax"]
    elif v_raw < -c["vmax"]:
        v = -c["vmax"]
    else:
        v = v_raw
    push = (v_raw > c["vmax"] and e > 0) or (v_raw < -c["vmax"] and e < 0)
    if not push:
        st["s1"] = c["b1"]*e - c["a1"]*yres + st["s2"]
        st["s2"] = c["b2"]*e - c["a2"]*yres
    sat = v_raw > c["vmax"] or v_raw < -c["vmax"]
    return v, sat


# ------------------------------------------------ T/4 延时 PLL（pll_step）
def pll_step(ug, st):
    udel = st["buf"][st["idx"]]
    st["buf"][st["idx"]] = ug
    st["idx"] += 1
    if st["idx"] >= len(st["buf"]):
        st["idx"] = 0
    ubeta = -udel
    vq = ug*math.cos(st["th"]) - ubeta*math.sin(st["th"])
    sat = abs(vq) >= P["pll_vq_max"]
    vq = max(-P["pll_vq_max"], min(P["pll_vq_max"], vq))
    st["wint"] += P["pll_Ki"]*vq*TS
    st["wint"] = max(-P["pll_wint_max"], min(P["pll_wint_max"], st["wint"]))
    w = 2*math.pi*P["fg"] + P["pll_Kp"]*vq + st["wint"]
    sin_ref = math.sin(st["th"])
    cos_ref = math.cos(st["th"])
    Uamp = math.sqrt(ug*ug + ubeta*ubeta)
    st["th"] += w*TS
    if st["th"] >= 2*math.pi:
        st["th"] -= 2*math.pi
    elif st["th"] < 0:
        st["th"] += 2*math.pi
    return sin_ref, cos_ref, Uamp, sat


# ------------------------------------------------ 死区补偿（deadtime_comp_step）
_CUR_IS_LC = [False]


def deadtime_comp(m, i_ref, mode):
    if mode == "none":
        return max(-P["m_max"], min(P["m_max"], m))
    if mode == "sign":
        s = 1.0 if i_ref >= 0 else -1.0
    else:  # sat
        i_sat = P["i_sat_LC"] if _CUR_IS_LC[0] else P["i_sat_L"]
        s = max(-1.0, min(1.0, i_ref/i_sat))
    mc = m + P["td_norm"]*s
    return max(-P["m_max"], min(P["m_max"], mc))


# ------------------------------------------------ PV 单二极管（pv_current）
def pv_current(V, G, T_C=25.0):
    p = P["pv"]
    q = 1.602176634e-19
    kb = 1.380649e-23
    Vt = p["N"]*kb*(T_C + 273.15)/q
    Iph = p["Isc"]*(G/1000.0)*(1 + p["Ki"]*(T_C - 25))
    Voc_T = p["Voc"] + p["Tvco"]*(T_C - 25)
    I0 = Iph/(math.exp(min(Voc_T/(p["Nser"]*Vt), 690)) - 1)
    I = Iph*0.9
    for _ in range(60):
        x = (V + I*p["Rs"])/(p["Nser"]*Vt)
        ex = math.exp(min(x, 690))
        f = Iph - I0*(ex - 1) - (V + I*p["Rs"])/p["Rp"] - I
        df = -I0*ex*p["Rs"]/(p["Nser"]*Vt) - p["Rs"]/p["Rp"] - 1
        dI = f/df
        I -= dI
        if abs(dI) < 1e-10:
            break
    return max(0.0, I)


def pv_mpp(G, T_C=25.0, v_lo=55.0, v_hi=95.0, dv=0.005):
    """数值扫描求理论 MPP，返回 (P_mpp, V_mpp, I_mpp)"""
    best = (0.0, 0.0, 0.0)
    n = int((v_hi - v_lo)/dv) + 1
    for i in range(n):
        V = v_lo + i*dv
        I = pv_current(V, G, T_C)
        if V*I > best[0]:
            best = (V*I, V, I)
    return best


# ------------------------------------------------ 功率级（平均模型，ZOH 精确离散）
class Plant:
    """x = [i_L, i_g, v_c]（LC）或 [i_L]（L）"""

    def __init__(self, structure, L=None):
        self.structure = structure
        self.L = P["L"] if L is None else L
        r, Rg = P["Rf"], P["Rg"]
        n = 3 if structure == "LC" else 1
        self.n = n
        if structure == "L":
            # L 结构对象为 Ltot = L + Lg（对方 L0/L3 口径），电阻 Rf+Rg
            Ltot = self.L + P["Lg"]
            Rtot = r + Rg
            A = np.array([[-Rtot/Ltot]])
            B = np.array([[1.0/Ltot, -1.0/Ltot]])
        else:
            # LC：L -> PCC，PCC 上 (C 串 Rd) 并联、再经 Lg(Rg) 接电网源
            # v_PCC = vC + Rd*(iL - i_g)
            A = np.zeros((3, 3))
            A[0, 0] = -(r + P["Rd"])/self.L
            A[0, 1] = P["Rd"]/self.L
            A[0, 2] = -1.0/self.L
            A[1, 0] = P["Rd"]/P["Lg"]
            A[1, 1] = -(P["Rd"] + Rg)/P["Lg"]
            A[1, 2] = 1.0/P["Lg"]
            A[2, 0] = 1.0/P["C"]
            A[2, 1] = -1.0/P["C"]
            B = np.zeros((3, 2))
            B[0, 0] = 1.0/self.L
            B[1, 1] = -1.0/P["Lg"]
        M = np.zeros((n + 2, n + 2))
        M[:n, :n] = A*DT
        M[:n, n:] = B*DT
        E = expm(M)
        Ad, Bd = E[:n, :n], E[:n, n:]
        if n == 1:
            self.k = (float(Ad[0, 0]), float(Bd[0, 0]), float(Bd[0, 1]))
        else:
            self.k = tuple(float(v) for v in (
                Ad[0, 0], Ad[0, 1], Ad[0, 2],
                Ad[1, 0], Ad[1, 1], Ad[1, 2],
                Ad[2, 0], Ad[2, 1], Ad[2, 2],
                Bd[0, 0], Bd[0, 1], Bd[1, 0], Bd[1, 1], Bd[2, 0], Bd[2, 1]))

    def step(self, x, v_ab, u_g):
        if self.n == 1:
            a00, b00, b01 = self.k
            x[0] = a00*x[0] + b00*v_ab + b01*u_g
        else:
            (a00, a01, a02, a10, a11, a12, a20, a21, a22,
             b00, b01, b10, b11, b20, b21) = self.k
            iL, ig, vc = x
            x[0] = a00*iL + a01*ig + a02*vc + b00*v_ab + b01*u_g
            x[1] = a10*iL + a11*ig + a12*vc + b10*v_ab + b11*u_g
            x[2] = a20*iL + a21*ig + a22*vc + b20*v_ab + b21*u_g

    def currents(self, x):
        if self.n == 1:
            return x[0], x[0], 0.0
        return x[0], x[1], x[2]


# ------------------------------------------------ 主仿真器
def run_case(structure="L", mode="fixed_i", fixed_P=200.0, t_end=1.0,
             comp="none", bias_i=0.0, L=None, V0=None, G_sched=None,
             P_sched=None, T_C=25.0, nsub=None, record=True):
    """单算例。mode: 'fixed_i'（固定功率指令）| 'mppt'（PV+P&O+电压环）。

    G_sched: None 或 [(t0,G0),(t1,G1),...] 阶跃表（mppt 模式，取 t>=tt 的最后档）。
    P_sched: None 或 [(t0,P0),(t1,P1),...] 功率指令阶跃表（fixed_i 模式，
             对方 A7 口径：在电流峰值处阶跃）。
    返回 dict(t, i_g, i_L, v_dc, u_g, i_ref, meta)。
    """
    nsub = NSUB if nsub is None else nsub
    dt = TS/nsub
    _CUR_IS_LC[0] = (structure == "LC")
    plant = Plant(structure, L=L)
    pr_cfg = pr_design(P["Kp_pr"], P["Kr_pr"], P["f_bw_pr"], 50.0, TS)
    st_pr = {"s1": 0.0, "s2": 0.0}
    st_pll = {"buf": [0.0]*100, "idx": 0, "th": 0.0, "wint": 0.0}

    mppt = (mode == "mppt")
    if mppt:
        Nma, Np = 200, int(round(P["mppt_Tp"]/TS))
        vbuf = [0.0]*Nma
        ibuf = [0.0]*Nma
        mstate = {"vsum": 0.0, "isum": 0.0, "midx": 0, "cnt": 0,
                  "Vref": P["mppt_V0"] if V0 is None else V0,
                  "dir": 1.0, "Pprev": -1e9, "integ": 0.0,
                  "first": True, "Im": 0.0}
        G_now = G_sched[0][1] if G_sched else P["G_points"][2]
    else:
        Im0 = math.sqrt(2)*fixed_P/P["Ug_rms"]
        P_beat = fixed_P

    x = [0.0]*plant.n
    vdc = P["Vdc"]
    steps = int(round(t_end/dt))
    sub_per_beat = int(round(TS/dt))
    delay_subs = int(round(P["ctrl_delay_beats"]*sub_per_beat))

    t_arr = np.zeros(steps) if record else None
    ig_arr = np.zeros(steps) if record else None
    il_arr = np.zeros(steps) if record else None
    vdc_arr = np.zeros(steps) if record else None
    ug_arr = np.zeros(steps) if record else None
    iref_arr = np.zeros(steps) if record else None

    m_applied = 0.0
    m_queue = []        # [(apply_substep, m)]，FIFO：防止新指令覆盖未应用的旧指令
    i_ref_rec = 0.0
    ipv_beat = 0.0
    G_beat = G_now if mppt else 0.0

    for kk in range(steps):
        t = kk*dt
        if kk % nsub == 0:
            # ---- 控制拍（20 kHz） ----
            iL, _, _ = plant.currents(x)
            iL_meas = iL + bias_i
            ug_s = UG_PK*math.sin(WG*t)
            ss = 1.0 if t >= P["Tsoft"] else t/P["Tsoft"]
            sin_ref, cos_ref, Uamp, _ = pll_step(ug_s, st_pll)
            if mppt:
                if G_sched:
                    G_beat = G_sched[-1][1]
                    for (tt, GG) in G_sched:
                        if t >= tt:
                            G_beat = GG
                else:
                    G_beat = G_now
                ipv_beat = pv_current(vdc, G_beat, T_C)
            # ---- 电流参考（LC 电容电流前馈） ----
            if not mppt and P_sched:
                P_beat = P_sched[-1][1]
                for (tt, PP) in P_sched:
                    if t >= tt:
                        P_beat = PP
                Im0 = math.sqrt(2)*P_beat/P["Ug_rms"]
            Im = mstate["Im"] if mppt else Im0
            i_ref = ss*Im*sin_ref
            if _CUR_IS_LC[0]:
                i_ref += ss*P["C"]*WG*Uamp*cos_ref
            i_ref_rec = i_ref
            e = i_ref - iL_meas
            vpr, _ = pr_step(e, st_pr, pr_cfg)
            vff = ss*ug_s/max(vdc, 10.0)
            m_raw = max(-P["m_max"], min(P["m_max"], vpr + vff))
            m_cmd = deadtime_comp(m_raw, i_ref, comp)
            m_queue.append((kk + delay_subs, m_cmd))
            # ---- MPPT 外环（mppt_step：滑动平均 + P&O + 电压 PI 条件冻结） ----
            if mppt:
                if mstate["first"]:
                    for i in range(Nma):
                        vbuf[i], ibuf[i] = vdc, ipv_beat
                    mstate["vsum"], mstate["isum"] = vdc*Nma, ipv_beat*Nma
                    mstate["first"] = False
                oldv, oldi = vbuf[mstate["midx"]], ibuf[mstate["midx"]]
                vbuf[mstate["midx"]], ibuf[mstate["midx"]] = vdc, ipv_beat
                mstate["vsum"] += vdc - oldv
                mstate["isum"] += ipv_beat - oldi
                mstate["midx"] += 1
                if mstate["midx"] >= Nma:
                    mstate["midx"] = 0
                vdc_f = mstate["vsum"]/Nma
                ipv_f = mstate["isum"]/Nma
                Pav = vdc_f*ipv_f
                mstate["cnt"] += 1
                if mstate["cnt"] >= Np:
                    if Pav < mstate["Pprev"]:
                        mstate["dir"] = -mstate["dir"]
                    mstate["Vref"] += mstate["dir"]*P["mppt_dV"]
                    if mstate["Vref"] > P["mppt_Vmax"]:
                        mstate["Vref"] = P["mppt_Vmax"]
                        mstate["dir"] = -1.0
                    elif mstate["Vref"] < P["mppt_Vmin"]:
                        mstate["Vref"] = P["mppt_Vmin"]
                        mstate["dir"] = 1.0
                    mstate["Pprev"] = Pav
                    mstate["cnt"] = 0
                err = vdc_f - mstate["Vref"]
                integ_old = mstate["integ"]
                integ = integ_old + P["mppt_Ki"]*err*TS
                integ = max(0.0, min(P["mppt_Im_max"], integ))
                Im_raw = P["mppt_Kp"]*err + integ
                if Im_raw > P["mppt_Im_max"]:
                    mstate["Im"] = P["mppt_Im_max"]
                    if err > 0:            # 仍在往上推 -> 冻结积分
                        mstate["integ"] = integ_old
                    else:
                        mstate["integ"] = integ
                elif Im_raw < 0:
                    mstate["Im"] = 0.0
                    if err < 0:            # 仍在往下推 -> 冻结积分
                        mstate["integ"] = integ_old
                    else:
                        mstate["integ"] = integ
                else:
                    mstate["Im"] = Im_raw
                    mstate["integ"] = integ
        # ---- 应用 1.5 拍延时后的调制波（FIFO，逐个到期应用） ----
        while m_queue and kk >= m_queue[0][0]:
            m_applied = m_queue.pop(0)[1]
        # ---- 功率级：平均 + 功率级死区误差（deadtime_step） ----
        iL, ig, vc = plant.currents(x)
        ug = UG_PK*math.sin(WG*t)
        m_eff = m_applied - P["td_norm"]*(1.0 if iL >= 0 else -1.0)
        v_ab = m_eff*vdc
        plant.step(x, v_ab, ug)
        if mppt:
            i_inv = v_ab*iL/vdc if vdc > 1.0 else 0.0
            vdc += dt*(pv_current(vdc, G_beat, T_C) - i_inv)/P["Cdc"]
            vdc = max(10.0, min(120.0, vdc))
        if record:
            iL2, ig2, _ = plant.currents(x)
            t_arr[kk] = t
            ig_arr[kk] = ig2
            il_arr[kk] = iL2
            vdc_arr[kk] = vdc
            ug_arr[kk] = ug
            iref_arr[kk] = i_ref_rec

    return {"t": t_arr, "i_g": ig_arr, "i_L": il_arr, "v_dc": vdc_arr,
            "u_g": ug_arr, "i_ref": iref_arr,
            "meta": {"structure": structure, "mode": mode, "comp": comp,
                     "fixed_P": fixed_P, "bias_i": bias_i,
                     "L": L if L is not None else P["L"]}}
