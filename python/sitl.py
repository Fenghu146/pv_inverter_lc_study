# -*- coding: utf-8 -*-
"""sitl.py — 软件在环（SITL）：Python 主电路模型 逐拍 驱动 DSP 真代码

与 A0–A5 的关系：
  A0–A5 是"算法移植到 Python"的对比仿真；SITL 跑的是 **dsp/src 里的同一份 C 代码**
  （经 gcc 编成 sitl.dll，ctypes 逐拍调用 app_isr），因此它验证的是"固件 + 主电路
  能不能闭环"，而不是"Python 移植像不像"。

链路（每 50 µs 一拍）：
  plant.measure() → sitl_step(si) → app_isr: ADC→SI→零偏→ctrl_isr→PWM→CMPA
                  ← cmpa_a/cmpa_b/状态/故障
  plant.integrate(cmpa) → 更新 i_L / v_c / i_g / v_dc → 下一拍

功率级接线模型（与 docs/14 的拓扑一致）：
  PV ──(预充电阻 100 Ω ── 接触器)── C_dc ── H 桥 ── L ─┬─ LC 时并 C(+R_d) ── PCC
                                                        └── 并网继电器 ── L_g ── 电网
  - 并网继电器断开且预充未使能：PV 与母线完全断开（i_pv = 0，v_pv 读到开路 Voc），
    这一段的电流必须为零，零偏标定才成立；
  - 预充阶段：经 100 Ω 给 C_dc 充电，i_pv 受 PV I-V 与电阻共同限制；
  - 合闸后：电阻被旁路，PV 直接接母线，并网回路闭合。

两种功率级模型（--mode）：
  avg : 一个控制拍内取平均电压 v_ab = m·Vdc（m 由 CMPA 还原）。用于闭环行为、
        状态机、MPPT、保护，计算快；纹波与 THD 会被低估（A1/A5 解析层与 Simulink
        开关层才是纹波口径）。
  sw  : 每个控制拍再细分 --nsub 步，按三角载波与 CMPA 比较得到 ±Vdc 瞬时电压，
        采样仍只在拍点发生（与真机 ADC 同步采样一致）。能看到开关纹波与混叠。

用法：
  python sitl.py --struct L  --mode avg --dur 2.0
  python sitl.py --struct LC --mode sw  --rd 1 --dur 2.0 --nsub 40 --out out.csv
"""
import argparse
import ctypes
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import params_canonical as C            # noqa: E402
from metrics import window_metrics       # noqa: E402

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
DLL = os.path.join(ROOT, "dsp", "sim", "build", "sitl.dll")

P = C.P
FS = float(P["fsw"])            # 20 kHz
TS = 1.0 / FS
TBPRD = 2500                    # param.h: PWM_TBPRD = 5000/2
F_G = float(P["fg"])            # 50 Hz
UG_RMS = float(P["Ug_rms"])     # 36 V
UG_PK = UG_RMS * math.sqrt(2.0)
ODE_NSUB_AVG = 4
R_PRE = 100.0                   # 预充电阻 100 Ω/25 W（docs/14 §2 定稿）
I_RATED_RMS = 7.857             # params.json 的 TDD 基准（Im_rated_rms）


# --------------------------------------------------------------- 桥接层
class Bridge(object):
    def __init__(self, path=DLL):
        if not os.path.isfile(path):
            raise SystemExit("找不到 %s —— 先跑 python tools/sitl_build.py" % path)
        self.lib = ctypes.CDLL(path)
        self.lib.sitl_reset.argtypes = [ctypes.c_float]
        self.lib.sitl_reset.restype = ctypes.c_int
        self.lib.sitl_request.argtypes = [ctypes.c_int, ctypes.c_int]
        self.lib.sitl_step.argtypes = [ctypes.POINTER(ctypes.c_double),
                                       ctypes.POINTER(ctypes.c_double)]
        self.lib.sitl_tbprd.restype = ctypes.c_uint
        self.tbprd = int(self.lib.sitl_tbprd())
        self.si = (ctypes.c_double * 6)()
        self.out = (ctypes.c_double * 20)()

    def reset(self, voc):
        return self.lib.sitl_reset(float(voc))

    def step(self, si):
        for k in range(6):
            self.si[k] = float(si[k])
        self.lib.sitl_step(self.si, self.out)
        return list(self.out)


# --------------------------------------------------------------- PV 模型
class PvModel(object):
    """单二极管（参数来自 params.json 的 pv_model，calib_pv.py --apply 标定）。

    先按网格算一遍 I(V)，之后全部查表插值——每次子步都要用，不能现场牛顿迭代。
    """

    def __init__(self, pv, n=401):
        self.Isc = pv["Isc"]
        self.Voc = pv["Voc"]
        self.Rs = pv["Rs"]
        self.Rp = pv["Rp"]
        a = pv["Nser"] * pv["N"] * 1.380649e-23 * (273.15 + 25.0) / 1.602176634e-19
        self.a = a
        self.Iph = self.Isc * (1.0 + self.Rs / self.Rp)
        self.I0 = (self.Iph - self.Voc / self.Rp) / (math.exp(self.Voc / a) - 1.0)
        self.V = np.linspace(0.0, self.Voc * 0.999, n)
        self.I = np.array([self._solve(v) for v in self.V])

    def _solve(self, V, iters=40):
        I = max(self.Isc * (1.0 - V / self.Voc), 0.0)
        for _ in range(iters):
            Vl = V + I * self.Rs
            ex = math.exp(min(Vl / self.a, 700.0))
            f = self.Iph - self.I0 * (ex - 1.0) - Vl / self.Rp - I
            df = -self.I0 * ex * self.Rs / self.a - self.Rs / self.Rp - 1.0
            dI = f / df
            I -= dI
            if abs(dI) < 1e-10:
                break
        return max(I, 0.0)

    def current(self, V):
        if V >= self.Voc:
            return 0.0
        if V <= 0.0:
            return float(self.I[0])
        return float(np.interp(V, self.V, self.I))


# --------------------------------------------------------------- 主电路
class Plant(object):
    """L / LC 单相并网逆变器（PV—H桥—耦合网络—PCC—L_g—电网）。"""

    def __init__(self, struct="L", rd=0.0, mode="avg", nsub=40, vdc0=0.0,
                 dt_error=True, dt_scale=1.0, delay_beats=1.5):
        self.struct = struct.upper()
        self.rd = float(rd)
        self.mode = mode
        self.nsub = max(1, int(nsub))
        # 死区电压误差：v_err = -2·fsw·td·Vdc·sign(i_L)。控制器在 control_isr.c:152
        # 用 v_cmd = v_star + DT_COMP_COEF·Vdc·sign(i_L) 反补，所以功率级必须施加
        # 这一项，否则"补偿是否真的有效"在环里根本看不出来。
        self.dt_error = bool(dt_error)
        self.dt_comp = 2.0 * FS * float(P["Td"])
        # dt_scale 放大"真实"死区误差而不动固件的补偿系数：1.0=完全补偿，
        # 2.0=误差是补偿能力的两倍（模拟 td 选型偏小/驱动延时偏大）。
        self.dt_scale = float(dt_scale)
        # 计算+装载延迟：ADC 采样到新占空比真正作用到桥臂之间是 1.5 个控制拍
        # （1 拍计算 + 0.5 拍 PWM 装载），与 engine.py 的 ctrl_delay_beats 同口径。
        # 这一项直接决定 LC 在谐振点的相位裕度，不能省。
        self.delay_beats = float(delay_beats)
        # trace：子步级连续电流记录（None=不记）。20 kHz 采样看不出 20 kHz 开关纹波，
        # 要评估纹波与 THD 必须在子步层面记录连续波形，再按 nsub·fsw 的采样率分析。
        self.trace = None
        self.trace_t = None
        self.L = float(P["L"])
        self.C = float(P["C"]) if self.struct == "LC" else 0.0
        self.Lg = float(P["Lg"])
        self.Cdc = float(P["Cdc"])
        self.Rf = float(P["Rf"])
        self.Rg = float(P["Rg"])
        self.pv = PvModel(P["pv"])
        # 状态
        self.iL = 0.0
        self.ig = 0.0
        self.vc = 0.0
        self.vcint = 0.0
        self.vdc = float(vdc0)
        self.v_pv = 0.0
        self.i_pv = 0.0
        self.pv_connected = False
        self._phase = 0.0

    # ---- 电网 ----
    def _vg(self, t):
        return UG_PK * math.sin(2.0 * math.pi * F_G * t)

    # ---- PV/母线接线状态 ----
    def pv_settle(self, precharge_on, relay_closed):
        """按接线状态更新 i_pv / v_pv，返回串入电阻（None = 断开）。"""
        if relay_closed:
            r = 0.0
        elif precharge_on:
            r = R_PRE
        else:
            r = None
        if r is None:
            self.pv_connected = False
            self.i_pv = 0.0
            self.v_pv = self.pv.Voc * 0.999      # 开路：传感器读到 Voc
            return None
        self.pv_connected = True
        if r <= 0.0:
            self.i_pv = self.pv.current(self.vdc)
            self.v_pv = self.vdc
            return 0.0
        V = self.vdc
        I = self.pv.current(V)
        for _ in range(4):
            V = self.vdc + r * I
            I = self.pv.current(V)
        self.i_pv = I
        self.v_pv = V
        return r

    # ---- 测量（送进 DSP 的 SI 值） ----
    def measure(self, t, precharge_on, relay_closed):
        self.pv_settle(precharge_on, relay_closed)
        return [self.v_pv, self.i_pv, self.vdc, self.vc, self.iL, self.ig]

    # ---- 功率级 ----
    def _dt_err(self):
        """死区造成的平均电压偏差（符号跟随电流；0.05 A 内不补，与固件一致）。"""
        if not self.dt_error:
            return 0.0
        if self.iL > 0.05:
            s = 1.0
        elif self.iL < -0.05:
            s = -1.0
        else:
            s = 0.0
        return self.dt_comp * self.vdc * s * self.dt_scale

    def _vab_avg(self, cmpa_a, cmpa_b):
        m = (float(cmpa_a) - float(cmpa_b)) / float(TBPRD)
        return m * self.vdc - self._dt_err()

    def _vab_sw(self, cmpa_a, cmpa_b):
        """三角载波（增减计数）与 CMPA 比较；返回本子步的瞬时 v_ab。

        死区在这里按"一拍平均偏差"近似施加（不是逐个开关沿插入 blanking），
        因为本轮关心的是它对 THD 的量级贡献与补偿效果，不是单次换流细节。
        """
        period = 2.0 * TBPRD
        self._phase = (self._phase + period / float(self.nsub)) % period
        ctr = self._phase if self._phase < TBPRD else period - self._phase
        s_a = 1.0 if ctr < cmpa_a else 0.0
        s_b = 1.0 if ctr < cmpa_b else 0.0
        return (s_a - s_b) * self.vdc - self._dt_err()

    def _deriv(self, v_ab, v_g):
        """返回 (diL, dig, dvc, dvcint, dvdc)。"""
        if self.struct == "LC":
            if self.rd > 0.0:
                i_c = self.iL - self.ig
                v_c = self.vcint + self.rd * i_c
                dvcint = i_c / self.C
                dvc = 0.0
            else:
                v_c = self.vc
                dvc = (self.iL - self.ig) / self.C
                dvcint = 0.0
            diL = (v_ab - v_c - self.Rf * self.iL) / self.L
            dig = (v_c - v_g - self.Rg * self.ig) / self.Lg
        else:
            # 串联 L + L_g，ig ≡ iL，PCC 取两点分压
            dvc = 0.0
            dvcint = 0.0
            diL = (v_ab - v_g - (self.Rf + self.Rg) * self.iL) / (self.L + self.Lg)
            dig = diL
        i_dc = v_ab * self.iL / max(self.vdc, 1.0)
        dvdc = (self.i_pv - i_dc) / self.Cdc
        return diL, dig, dvc, dvcint, dvdc

    def integrate(self, t, cmpa_a, cmpa_b, precharge_on, relay_closed=True,
                  cmpa_prev=None):
        n = self.nsub if self.mode == "sw" else ODE_NSUB_AVG
        dt = TS / float(n)
        v_g = self._vg(t)
        if not relay_closed:
            # 并网继电器断开：耦合网络与电网之间开路，没有电流回路；
            # 母线只受 PV（经预充电阻或断开）影响。
            self.iL = 0.0
            self.ig = 0.0
            self.vc = v_g
            if self.pv_connected:
                self.vdc += (self.i_pv / self.Cdc) * TS
            if self.vdc < 0.0:
                self.vdc = 0.0
            return
        iL0 = self.iL
        ig0 = self.ig
        # 延迟按"前 frac 比例的子步用上一拍的占空比"实现：frac=0.5 即等效 1.5 拍。
        if cmpa_prev is None or self.delay_beats <= 0.0:
            frac = 0.0
        else:
            frac = max(0.0, min(1.0, self.delay_beats - 0.5))
        n_prev = int(round(n * frac))
        for k_sub in range(n):
            ca, cb = (cmpa_prev if k_sub < n_prev else (cmpa_a, cmpa_b))
            if self.mode == "sw":
                v_ab = self._vab_sw(ca, cb)
            else:
                v_ab = self._vab_avg(ca, cb)
            diL, dig, dvc, dvcint, dvdc = self._deriv(v_ab, v_g)
            self.iL += diL * dt
            self.ig += dig * dt
            if self.trace is not None:
                self.trace.append(self.ig)
                self.trace_t.append(t + (k_sub + 1) * dt)
            self.vc += dvc * dt
            self.vcint += dvcint * dt
            self.vdc += dvdc * dt
            if self.vdc < 0.0:
                self.vdc = 0.0
        if self.struct == "LC" and self.rd > 0.0:
            self.vc = self.vcint + self.rd * (self.iL - self.ig)
        elif self.struct == "L":
            # PCC 电压 = 电网 + L_g 上的压降。这里必须用"整拍平均"电流斜率，
            # 不能用最后一个子步的瞬时斜率——开关沿上 di/dt = Vdc/L ≈ 1.5e5 A/s，
            # 乘 0.5 mH 会凭空给出几十伏，曾经把 v_grid 读数顶出 VAC_RANGE 而误触发保护。
            self.vc = v_g + self.Lg * (self.iL - iL0) / TS


# --------------------------------------------------------------- 连续波形指标
def cont_metrics(t, i_g, i_ref_amp, i_rated_rms, f0=50.0, n_per=10):
    """子步级连续波形的 THD/纹波指标（矩形窗 + FFT，取整数个工频周期）。

    与 metrics.window_metrics 同一套定义（THD 2–50 次、HF >2 kHz、Idc），
    只是换成 FFT——连续波形 fs 可达 800 kHz，逐点 DFT 算不动。
    额外给出 40 kHz 簇与 15–25 kHz 主峰，用于和 A5 的"LC 附加衰减"直接对照。
    """
    fs = 1.0 / (t[1] - t[0])
    N = int(round(n_per / f0 * fs))
    N = min(N, len(i_g))
    x = np.array(i_g[-N:], dtype=float)
    x = x - x.mean()
    X = np.fft.rfft(x) * 2.0 / N
    f = np.fft.rfftfreq(N, 1.0 / fs)

    def at(fc):
        k = int(np.argmin(np.abs(f - fc)))
        return float(np.abs(X[k]))

    def peak_in(a, b):
        k = (f >= a) & (f <= b)
        return float(np.abs(X[k]).max()) if k.any() else 0.0

    def band_rms(a, b):
        k = (f >= a) & (f <= b)
        return float(np.sqrt(np.sum(np.abs(X[k]) ** 2) / 2.0)) if k.any() else 0.0

    I1 = at(f0)
    h_pow = sum(at(h * f0) ** 2 for h in range(2, 51))
    thd = math.sqrt(h_pow) / I1 * 100.0 if I1 > 0 else float("nan")
    hf = band_rms(2051.0, fs / 2.0 - 1.0) / I1 * 100.0 if I1 > 0 else float("nan")
    # 相位：用同一窗的电网电压（源侧 50 Hz 基波）作参考
    u = UG_PK * np.sin(2.0 * math.pi * f0 * np.array(t[-N:]))
    U = np.fft.rfft(u) * 2.0 / N
    ku = int(np.argmin(np.abs(f - f0)))
    ki = ku
    phase = math.degrees(np.angle(X[ki] * np.conj(U[ku])))
    return {"I1_A": I1,
            "amp_err_pct": (I1 - i_ref_amp) / i_ref_amp * 100.0 if i_ref_amp else float("nan"),
            "phase_deg": phase,
            "THD_pct": thd,
            "TDD_pct": math.sqrt(h_pow) / i_rated_rms * 100.0,
            "HF_pct": hf,
            "Idc_A": float(x.mean() + np.mean(i_g[-N:])),
            "sw40k_A": peak_in(39500.0, 40500.0),
            "band15_25k_A": peak_in(15000.0, 25000.0),
            "fs_hz": fs}


# --------------------------------------------------------------- 运行器
R_NAME = {0: "INIT", 1: "OFFSET_CAL", 2: "WAIT_GRID", 3: "PRECHARGE", 4: "SYNC",
          5: "CONNECT", 6: "MPPT_RUN", 7: "FAULT", 8: "OPEN_LOOP", 9: "FIXED_I"}


def run(struct="L", mode="avg", dur=2.0, rd=0.0, nsub=40, voc=90.0, vdc0=0.0,
        dt_error=True, dt_scale=1.0, delay_beats=1.5, log_sub=False,
        verbose=True, win=0.2):
    br = Bridge()
    br.reset(voc)
    if br.tbprd != TBPRD:
        raise SystemExit("TBPRD 不一致：dll=%d, python=%d" % (br.tbprd, TBPRD))
    pl = Plant(struct=struct, rd=rd, mode=mode, nsub=nsub, vdc0=vdc0,
               dt_error=dt_error, dt_scale=dt_scale, delay_beats=delay_beats)

    n = int(round(dur / TS))
    trace_from = n - int(round(win / TS)) if log_sub else -1
    rows = []
    states_seen = []
    t = 0.0
    pre = False
    relay = False
    cmpa_prev = (0.0, 0.0)
    for _ in range(n):
        if log_sub and len(rows) >= trace_from and pl.trace is None:
            pl.trace, pl.trace_t = [], []
        si = pl.measure(t, pre, relay)
        out = br.step(si)
        pre = bool(out[15])
        relay = bool(out[10])
        pl.integrate(t, out[0], out[1], pre, relay, cmpa_prev=cmpa_prev)
        cmpa_prev = (float(out[0]), float(out[1]))
        t += TS
        st = int(out[11])
        if not states_seen or states_seen[-1][1] != st:
            states_seen.append((t, st))
        rows.append([t, si[0], si[1], si[2], si[3], si[4], si[5],
                     out[12], out[2], out[3], out[4], out[5], out[6],
                     out[0], out[1], st, out[9], out[10], out[14], out[15], out[16],
                     out[7], out[8]])
    arr = np.array(rows)
    res = {"t": arr[:, 0], "i_g": arr[:, 6], "u_g": arr[:, 4],
           "vdc": arr[:, 3], "state": arr[:, 15], "rows": arr,
           "states_seen": states_seen, "struct": struct, "mode": mode, "rd": rd,
           "dt_error": dt_error, "dt_scale": dt_scale,
           "delay_beats": delay_beats}
    steady = False
    if len(arr) >= 2:
        w = min(win, float(arr[-1, 0]))
        if w >= 0.05:
            idx = arr[:, 0] >= (arr[-1, 0] - w)
            i_amp = float(arr[idx, 11][-1])
            steady = (arr[idx, 15].min() == 6.0) and (i_amp > 0.2)
            if steady:
                res.update(window_metrics(arr[idx, 0], arr[idx, 6], arr[idx, 4],
                                          i_amp, I_RATED_RMS))
    if log_sub and pl.trace and len(pl.trace) > 1000:
        tt = np.array(pl.trace_t)
        ii = np.array(pl.trace)
        fs_sub = 1.0 / (TS / float(pl.nsub if mode == "sw" else ODE_NSUB_AVG))
        i_amp = float(arr[-1, 11])
        res.update(cont_metrics(tt, ii, i_amp, I_RATED_RMS))
        res["cont"] = {"fs": fs_sub, "n": len(ii)}
        res["steady"] = steady = True
    if not steady:
        res["note"] = "末窗未进入 MPPT_RUN 稳态（电流或状态不满足），不出 THD"
    if verbose:
        report(res)
    return res


def report(r):
    print("== SITL 结果 ==")
    print("结构 %s ／ 功率级模型 %s ／ R_d = %.2f Ω ／ 死区误差 %s ／ 指令延迟 %.1f 拍"
          % (r["struct"], r["mode"], r["rd"],
             ("×%.2f" % r["dt_scale"]) if r.get("dt_error") else "关闭",
             r.get("delay_beats", 0.0)))
    print("状态序列：")
    for t, st in r["states_seen"]:
        print("  %.3f s → %s" % (t, R_NAME.get(st, st)))
    arr = r["rows"]
    print("末拍：vdc=%.2f V  i_L=%.3f A  i_ref=%.3f A  i_amp=%.3f A  vdc_ref=%.2f V"
          % (arr[-1, 3], arr[-1, 5], arr[-1, 10], arr[-1, 11], arr[-1, 12]))
    if "THD_pct" in r:
        print("末窗 200 ms：I1=%.4f A  amp_err=%.2f %%  phase=%.2f°  THD=%.3f %%  "
              "HF=%.3f %%  Idc=%.4f A"
              % (r["I1_A"], r["amp_err_pct"], r["phase_deg"], r["THD_pct"],
                 r["HF_pct"], r["Idc_A"]))
    if "sw40k_A" in r:
        print("纹波：40 kHz 簇 = %.4f A（基波 %.1f%%）／15–25 kHz 主峰 = %.4f A"
              % (r["sw40k_A"], r["sw40k_A"] / r["I1_A"] * 100.0, r["band15_25k_A"]))
    if "cont" in r:
        print("（以上指标取自子步级连续波形：%d 点 @ %.0f Hz）"
              % (r["cont"]["n"], r["cont"]["fs"]))
    if "note" in r:
        print("注：" + r["note"])
    fault = arr[:, 7].max()
    if fault:
        print("故障码最大值：%d" % int(fault))


HEADER = ("t_s,v_pv,i_pv,vdc,v_grid,i_L,i_g,fault,v_cmd,v_star,i_ref,i_amp,vdc_ref,"
          "cmpa_a,cmpa_b,state,pwm_req,relay,precharge_en,pwm_on,trip,theta,omega")


def save_csv(r, path):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    np.savetxt(path, r["rows"], delimiter=",", header=HEADER, comments="", fmt="%.9g")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--struct", default="L", choices=["L", "LC", "l", "lc"])
    ap.add_argument("--mode", default="avg", choices=["avg", "sw"])
    ap.add_argument("--dur", type=float, default=2.0)
    ap.add_argument("--rd", type=float, default=0.0)
    ap.add_argument("--nsub", type=int, default=40)
    ap.add_argument("--vdc0", type=float, default=0.0)
    ap.add_argument("--no-dt", action="store_true",
                    help="不注入死区电压误差（用于对照'无死区'理想功率级）")
    ap.add_argument("--dt-scale", type=float, default=1.0,
                    help="真实死区误差倍数（1=与固件补偿系数一致；2=只补一半）")
    ap.add_argument("--delay-beats", type=float, default=1.5,
                    help="控制指令延迟（拍），1.5 与 engine.py / 真机同口径")
    ap.add_argument("--log-sub", action="store_true",
                    help="按子步记录连续电流并用它算 THD/纹波（sw 模式才准）")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    r = run(struct=args.struct.upper(), mode=args.mode, dur=args.dur, rd=args.rd,
            nsub=args.nsub, vdc0=args.vdc0, dt_error=not args.no_dt,
            dt_scale=args.dt_scale, delay_beats=args.delay_beats,
            log_sub=args.log_sub)
    if args.out:
        save_csv(r, args.out)
        print("已写 %s（%d 行）" % (args.out, len(r["rows"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
