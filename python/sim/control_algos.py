"""控制算法层（Python 参考实现）—— 与 dsp/src 的 C 代码同参数、同结构，互为验证
SOGI-PLL / 准PR电流环 / 电压环PI / P&O MPPT / 保护 / 状态机
参数来源: params/params.json (与实施方案附录A一致)
"""
import json
import math
import os
from collections import namedtuple

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
P = json.load(open(os.path.join(ROOT, "params", "params.json"), encoding="utf-8"))

Ts = 1.0 / P["switching"]["f_s_Hz"]
OMEGA0 = 2 * math.pi * P["rating"]["f_g_Hz"]


class SogiPll:
    """SOGI-PLL: SOGI 生成 v_α/v_β → Park → v_q → PI → ω → 积分得 θ
    参数: k=1.41, PI: Kp=0.67, Ki=22 (v_q 按 U_m 归一化)"""

    def __init__(self, um=36.0 * math.sqrt(2)):
        c = P["control"]
        self.k = c["pll_sogi_k"]
        self.kp = c["pll_pi_kp"]
        self.ki = c["pll_pi_ki"]
        self.um = um
        self.reset()

    def reset(self):
        self.ialpha = 0.0   # SOGI 积分器1 (v_α' 即滤波后信号)
        self.ibeta = 0.0    # SOGI 积分器2 (v_β)
        self.omega = OMEGA0
        self.theta = 0.0
        self.pi_int = 0.0

    def step(self, v):
        """v: 电网电压瞬时采样(α轴)
        SOGI: d vα' = ω·k·(v - vα') - ω·vβ ; d vβ = ω·vα'
        鉴相: vq = vα·cosθ + vβ·sinθ = Um·sin(φ-θ), 锁定时 θ=φ(正弦相位)
        → θ 直接用于 i_ref = I_amp·sinθ, 与 u_g 同相(单位功率因数)"""
        self.ialpha += Ts * (self.k * self.omega * (v - self.ialpha) - self.omega * self.ibeta)
        self.ibeta += Ts * (self.omega * self.ialpha)
        valpha, vbeta = self.ialpha, self.ibeta
        vq = valpha * math.cos(self.theta) + vbeta * math.sin(self.theta)
        # PI on normalized v_q → ω
        vqn = vq / self.um
        self.pi_int += self.ki * vqn * Ts
        self.omega = OMEGA0 + self.kp * vqn + self.pi_int
        self.theta += self.omega * Ts
        if self.theta > 2 * math.pi:
            self.theta -= 2 * math.pi
        return self.theta, self.omega

    @property
    def locked(self):
        return True  # 由上层比较 ω 偏差判定


class PRController:
    """准PR: G(s) = Kp + 2Kr·ωc·s/(s² + 2ωc·s + ω0²)
    Tustin 离散 + 谐振频率预畸变 (k' = ω0/tan(ω0·Ts/2))"""

    def __init__(self):
        c = P["control"]
        self.kp = c["current_pr_kp"]
        self.kr = c["current_pr_kr"]
        self.wc = c["current_pr_wc_rad_s"]
        k = OMEGA0 / math.tan(OMEGA0 * Ts / 2.0)
        a0 = k * k + 2 * self.wc * k + OMEGA0 * OMEGA0
        a1 = -2 * k * k + 2 * OMEGA0 * OMEGA0
        a2 = k * k - 2 * self.wc * k + OMEGA0 * OMEGA0
        self.a1a0, self.a2a0 = a1 / a0, a2 / a0
        self.b0a0 = 2 * self.kr * self.wc * k / a0
        self.b2a0 = -2 * self.kr * self.wc * k / a0
        self.reset()

    def reset(self):
        self.x1 = self.x2 = self.y1 = self.y2 = 0.0

    def step(self, err):
        y = (self.b0a0 * err + self.b2a0 * self.x2
             - self.a1a0 * self.y1 - self.a2a0 * self.y2)
        self.x2, self.x1 = self.x1, err
        self.y2, self.y1 = self.y1, y
        return self.kp * err + y


class PIController:
    """通用 PI + 条件积分抗饱和
    dt: 实际调用间隔(默认 Ts); 1kHz 电压环应传 dt=20*Ts"""

    def __init__(self, kp, ki, out_min, out_max):
        self.kp, self.ki = kp, ki
        self.out_min, self.out_max = out_min, out_max
        self.integral = 0.0

    def step(self, err, dt=Ts):
        out_unsat = self.kp * err + self.integral
        # 条件积分: 输出饱和且误差仍向饱和方向时冻结积分
        if (out_unsat >= self.out_max and err > 0) or (out_unsat <= self.out_min and err < 0):
            pass
        else:
            self.integral += self.ki * err * dt
        out = self.kp * err + self.integral
        return min(max(out, self.out_min), self.out_max)


class PerturbObserve:
    """P&O MPPT: 每 T_mppt 执行一次, 用该周期平均功率判方向
    ΔV=0.5V, V* ∈ [62,75]V, 初始 0.8·Voc"""

    def __init__(self):
        c = P["control"]
        self.dv = c["mppt_dV_V"]
        self.vmin, self.vmax = c["Vdc_ref_limit_V"]
        self.v_ref = c["mppt_init_frac_Voc"] * P["rating"]["Voc_V"]
        self.last_p = None
        self.dir = 1

    def step(self, p_avg):
        if self.last_p is not None:
            dp = p_avg - self.last_p
            if dp < 0:
                self.dir = -self.dir
            self.v_ref += self.dir * self.dv
            self.v_ref = min(max(self.v_ref, self.vmin), self.vmax)
        self.last_p = p_avg
        return self.v_ref


# ---------- 保护 ----------
FaultCodes = namedtuple("FaultCodes", "oc_soft oc_hard vdc_ov vdc_uv ug_range freq pll_unlock")


def check_protection(i_ac_peak, vdc, ug_rms, fg, pll_ok, t_pll_bad):
    pr = P["protection"]
    f = FaultCodes(
        oc_soft=abs(i_ac_peak) > pr["I_oc_soft_A"],
        oc_hard=abs(i_ac_peak) > pr["I_oc_hard_A"],
        vdc_ov=vdc > pr["V_dc_ov_V"],
        vdc_uv=vdc < pr["V_dc_uv_V"],
        ug_range=not (pr["U_g_range_Vrms"][0] <= ug_rms <= pr["U_g_range_Vrms"][1]),
        freq=not (pr["f_g_range_Hz"][0] <= fg <= pr["f_g_range_Hz"][1]),
        pll_unlock=(not pll_ok) and t_pll_bad > pr["pll_unlock_time_s"],
    )
    return f, any(f)


# ---------- 状态机 ----------
class States:
    INIT, OFFSET_CAL, WAIT_GRID, PRECHARGE, SYNC, CONNECT, MPPT_RUN, FAULT, OPEN_LOOP, FIXED_I = range(10)


class StateMachine:
    """INIT→OFFSET_CAL→WAIT_GRID→PRECHARGE→SYNC→CONNECT→MPPT_RUN; 任意→FAULT; 人工复位→INIT"""

    def __init__(self):
        self.state = States.INIT
        self.fault_code = 0
        self.timer = 0.0

    def step(self, dt, pll_locked, vdc_ok, fault):
        self.timer += dt
        s = self.state
        if s == States.INIT:
            self.timer = 0.0
            self.state = States.OFFSET_CAL
        elif s == States.OFFSET_CAL:
            if self.timer >= 0.05:  # 1024点零偏校准 ~50ms
                self.state, self.timer = States.WAIT_GRID, 0.0
        elif s == States.WAIT_GRID:
            if pll_locked and self.timer >= 1.0:  # PLL锁定持续1s
                self.state, self.timer = States.PRECHARGE, 0.0
        elif s == States.PRECHARGE:
            if vdc_ok:  # 母线充至 ≥0.9·Voc, 短接预充电阻
                self.state, self.timer = States.SYNC, 0.0
        elif s == States.SYNC:
            if self.timer >= 0.2:  # 200ms 后闭合继电器
                self.state, self.timer = States.CONNECT, 0.0
        elif s == States.CONNECT:
            if self.timer >= 0.5:  # 参考0斜坡上升完成
                self.state, self.timer = States.MPPT_RUN, 0.0
        elif s == States.MPPT_RUN:
            pass
        elif s == States.FAULT:
            pass  # 人工清除
        if fault and s not in (States.FAULT, States.INIT):
            self.state = States.FAULT
        return self.state

    def manual_reset(self):
        self.state = States.INIT
        self.fault_code = 0


def control_step(I_amp_ref, vg, ig, vdc, pll: SogiPll, pr: PRController):
    """20kHz 电流环一步（含前馈与限幅 ±0.95·Vdc）"""
    theta, omega = pll.step(vg)
    i_ref = I_amp_ref * math.sin(theta)
    err = i_ref - ig
    u = pr.step(err) + vg  # 电网电压前馈
    ulim = P["control"]["modulation_limit"] * vdc
    u = min(max(u, -ulim), ulim)
    return u, i_ref
