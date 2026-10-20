"""开关级时域仿真器 —— 对齐实施方案 6.1/6.2（S1–S6 任务）
拓扑: PV → C_dc → 单相H桥(单极性倍频SPWM+死区) → 耦合网络(L 或 LC+R_d) → L_g + 36V/50Hz 电压源
控制: SOGI-PLL + 准PR电流环 + 电压环PI + P&O (与 dsp/src 的 C 代码同参数)
数值: 状态空间 ZOH 精确离散化 (scipy.linalg.expm) + 标量快速内核
死区: 平均电压误差模型 v_err = -2·f_sw·td·Vdc·sign(i_leg) (开关级默认启用)
模式: switched(开关级, 含纹波/死区) / average(平均模型, 动态与MPPT长仿真)
"""
import json
import math
import os
import sys

import numpy as np
from scipy.linalg import expm

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pv_model import PVArray
from control_algos import SogiPll, PRController, PIController, PerturbObserve

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
P = json.load(open(os.path.join(ROOT, "params", "params.json"), encoding="utf-8"))

Ts = 1.0 / P["switching"]["f_s_Hz"]
OMEGA = 2 * math.pi * P["rating"]["f_g_Hz"]


class PowerStage:
    """耦合网络+电网的状态空间: x = [i_L, i_g, v_c] (LC) 或 [i_L] (L)
    LC: L di_L/dt = v_ab - v_c - r·i_L
        C dv_c/dt = i_L - i_g - v_c/R_d   (R_d=0 时无该泄放项)
        Lg di_g/dt = v_c - u_g
    L:  x=[i]; L di/dt = v_ab - u_g - r·i
    """

    def __init__(self, structure="L", L=None, C=None, Rd=None, Lg=None, dt=None):
        p = P["plant"]
        self.structure = structure
        self.L = L if L is not None else p["L_H"]
        self.C = C if C is not None else p["C_F"]
        self.Rd = Rd if Rd is not None else p["R_d_default_ohm"]
        self.Lg = Lg if Lg is not None else p["L_g_H"]
        self.r = p["R_parasitic_ohm"]
        self.dt = dt if dt is not None else Ts
        self._build()

    def _build(self):
        if self.structure == "L":
            A = np.array([[-self.r / self.L]])
            B = np.array([[1.0 / self.L, -1.0 / self.L]])
            n = 1
        else:
            A = np.zeros((3, 3))
            A[0, 0] = -self.r / self.L
            A[0, 2] = -1.0 / self.L
            A[2, 0] = 1.0 / self.C
            A[2, 1] = -1.0 / self.C
            if self.Rd > 0:
                A[2, 2] = -1.0 / (self.Rd * self.C)
            A[1, 2] = 1.0 / self.Lg
            B = np.zeros((3, 2))
            B[0, 0] = 1.0 / self.L
            B[1, 1] = -1.0 / self.Lg
            n = 3
        self.n = n
        M = np.zeros((n + 2, n + 2))
        M[:n, :n] = A * self.dt
        M[:n, n:] = B * self.dt
        E = expm(M)
        self.Ad = E[:n, :n]
        self.Bd = E[:n, n:]
        # 展开为标量系数(快速内核)
        a = self.Ad
        b = self.Bd
        if n == 1:
            self.k = (float(a[0, 0]), float(b[0, 0]), float(b[0, 1]))
        else:
            self.k = (float(a[0, 0]), float(a[0, 1]), float(a[0, 2]),
                      float(a[1, 0]), float(a[1, 1]), float(a[1, 2]),
                      float(a[2, 0]), float(a[2, 1]), float(a[2, 2]),
                      float(b[0, 0]), float(b[0, 1]),
                      float(b[1, 0]), float(b[1, 1]),
                      float(b[2, 0]), float(b[2, 1]))

    def step(self, x, v_ab, u_g):
        """x: list[float] 就地更新, 返回 x"""
        if self.n == 1:
            a00, b00, b01 = self.k
            x[0] = a00 * x[0] + b00 * v_ab + b01 * u_g
        else:
            (a00, a01, a02, a10, a11, a12, a20, a21, a22,
             b00, b01, b10, b11, b20, b21) = self.k
            iL, ig, vc = x[0], x[1], x[2]
            x[0] = a00 * iL + a01 * ig + a02 * vc + b00 * v_ab + b01 * u_g
            x[1] = a10 * iL + a11 * ig + a12 * vc + b10 * v_ab + b11 * u_g
            x[2] = a20 * iL + a21 * ig + a22 * vc + b20 * v_ab + b21 * u_g
        return x

    def currents(self, x):
        if self.structure == "L":
            return x[0], x[0], 0.0
        return x[0], x[1], x[2]


class InverterSim:
    def __init__(self, structure="L", L=None, C=None, Rd=None, Lg=None,
                 power_point=1.0, mode="switched", deadtime=True, dead_comp=True):
        dt = Ts / 20.0 if mode == "switched" else Ts
        self.ps = PowerStage(structure, L, C, Rd, Lg, dt=dt)
        self.pv = PVArray()
        self.mode = mode
        self.dead_comp = dead_comp
        self.G = power_point
        self.Cdc = P["plant"]["C_dc_F"]
        self.f_sw = P["switching"]["f_sw_Hz"]
        self.td = P["switching"]["t_dead_ns"] * 1e-9 if deadtime else 0.0
        self.Vdc0 = P["rating"]["V_mpp_V"]
        self.ug_amp = math.sqrt(2) * P["rating"]["U_g_Vrms"]

    def run(self, t_end=1.0, mppt=True, fixed_i_amp=None, vdc_ref=None,
            g_step=None, ug_step=None):
        """g_step=(t,G2) 辐照阶跃; ug_step=(t,factor) 电网幅值阶跃
        返回 dict: t/i_g/i_L/v_dc/v_c/i_amp/fs"""
        ps = self.ps
        x = [0.0] * ps.n
        Vdc = self.Vdc0
        pll = SogiPll()
        pr = PRController()
        pi_vdc = PIController(P["control"]["voltage_pi_kp"], P["control"]["voltage_pi_ki"],
                              *P["control"]["I_amp_limit_A"])
        mppt_alg = PerturbObserve()
        if vdc_ref is not None:
            mppt_alg.v_ref = vdc_ref
        use_mppt = mppt and fixed_i_amp is None
        i_amp = fixed_i_amp if fixed_i_amp is not None else 0.0
        # 模式: 'mppt' | 'fixed_i' | 'vref'(电压环整定电流, PV自然工作点)
        if use_mppt:
            self.mode_ctrl = "mppt"
        elif fixed_i_amp is not None:
            self.mode_ctrl = "fixed_i"
        else:
            self.mode_ctrl = "vref"

        dt = Ts / 20.0 if self.mode == "switched" else Ts
        nsw = int(round(Ts / dt))
        steps = int(round(t_end / dt))

        t_arr = np.zeros(steps)
        ig_arr = np.zeros(steps)
        il_arr = np.zeros(steps)
        vdc_arr = np.zeros(steps)
        vc_arr = np.zeros(steps)
        iamp_arr = np.zeros(steps)

        cnt_isr = 0
        p_pv_acc, p_pv_n = 0.0, 0
        m_avg = 0.0
        TWO_PI = 2 * math.pi
        f_sw = self.f_sw
        td = self.td
        Cdc = self.Cdc
        G0 = self.G
        ug_amp0 = self.ug_amp
        mod_lim = P["control"]["modulation_limit"]
        mppt_every = int(round(0.1 / Ts))  # 100ms

        for k in range(steps):
            t = k * dt
            G = G0 if (g_step is None or t < g_step[0]) else g_step[1]
            ug_amp = ug_amp0 if (ug_step is None or t < ug_step[0]) else ug_amp0 * ug_step[1]
            ug = ug_amp * math.sin(OMEGA * t)

            il, ig, vc = ps.currents(x)
            ipv = self.pv.current(Vdc, G)

            if self.mode == "switched":
                carrier = 2.0 * abs((t * f_sw) % 1.0 - 0.5)
                duty = 0.5 * (1.0 + m_avg)
                sa = 1.0 if duty > carrier else 0.0
                sb = 1.0 if (1.0 - duty) > carrier else 0.0
                v_ab = (sa - sb) * Vdc
                if td > 0.0:
                    v_ab -= 2.0 * f_sw * td * Vdc * (1.0 if il >= 0.0 else -1.0)
            else:
                v_ab = m_avg * Vdc

            i_pv_inv = v_ab * il / Vdc if Vdc > 1.0 else 0.0
            Vdc += dt * (ipv - i_pv_inv) / Cdc
            if Vdc < 10.0:
                Vdc = 10.0
            elif Vdc > 120.0:
                Vdc = 120.0

            ps.step(x, v_ab, ug)
            il, ig, vc = ps.currents(x)

            if (k + 1) % nsw == 0:
                cnt_isr += 1
                theta, _omega = pll.step(ug)
                if use_mppt:
                    if cnt_isr % 20 == 0:
                        # 电压环(1kHz): 母线低于参考 → 功率不足 → 增大电流幅值指令
                        i_amp = pi_vdc.step(Vdc - mppt_alg.v_ref, dt=20 * Ts)
                    p_pv_acc += Vdc * ipv
                    p_pv_n += 1
                    if cnt_isr % mppt_every == 0:
                        mppt_alg.step(p_pv_acc / max(p_pv_n, 1))
                        p_pv_acc, p_pv_n = 0.0, 0
                elif fixed_i_amp is not None:
                    i_amp = fixed_i_amp
                else:
                    # vref 模式: 电压环(1kHz)整定 i_amp, MPPT 断开
                    if cnt_isr % 20 == 0:
                        i_amp = pi_vdc.step(Vdc - mppt_alg.v_ref, dt=20 * Ts)
                i_ref = i_amp * math.sin(theta)
                # PR 反馈取逆变器侧 i_L (方案 5.1 控制框图 + 4.2.1 自然阻尼判据的前提);
                # i_g 为滤波后并网电流, 用于性能评估
                u = pr.step(i_ref - il) + ug
                # 死区补偿 (方案5.5): 抵消 v_err = -2·f_sw·td·Vdc·sign(i_L), 用实测电流符号
                if self.dead_comp and td > 0.0 and i_amp > 1e-6:
                    u += 2.0 * f_sw * td * Vdc * (1.0 if il >= 0.0 else -1.0)
                ulim = mod_lim * Vdc
                if u > ulim:
                    u = ulim
                elif u < -ulim:
                    u = -ulim
                m_avg = u / Vdc

            t_arr[k] = t
            ig_arr[k] = ig
            il_arr[k] = il
            vdc_arr[k] = Vdc
            vc_arr[k] = vc
            iamp_arr[k] = i_amp

        return {"t": t_arr, "i_g": ig_arr, "i_L": il_arr, "v_dc": vdc_arr,
                "v_c": vc_arr, "i_amp": iamp_arr, "fs": 1.0 / dt}
