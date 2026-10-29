# -*- coding: utf-8 -*-
"""合并版统一参数源（单一来源）

合并原则（详见 README.md）：
  - 电网/开关/功率等级：技术文件口径（200 W / 36 Vrms / 50 Hz / 20 kHz），两组一致；
  - 直流侧与耦合网络：采用对方（Desktop\\仿真）经 1-4 mH 扫描与组合工况验证的
    设计值（Vdc=80 V, L=2 mH, C=12 µF, Rd=1 Ω, Lg=1 mH）——技术文件对这些值
    均无规定，我方《实现方案》的 75 V/0.5 mH 系列保留在 A1 扫描中作对照；
  - 控制器：对方 pr_design/cfg_L/cfg_LC 的冻结系数（Kp=2π·500·L/Vdc≈0.0785，
    Kr=4, wc=2π·2 Hz，预畸变 Tustin biquad，vmax=0.9，m_max=0.95）；
  - MPPT：对方 mppt_step 结构（10 ms 滑动平均 + P&O 1 V/0.5 s + 电压 PI
    Kp=0.6/Ki=20，条件冻结抗饱和）；
  - PV：对方单二极管标定（G=1000 时 80.00 V / 2.500 A / 200.0 W）；
  - 死区：Td=1 µs -> Δm=2·Td/Tsw=0.04（ΔV=3.2 V），功率级注入 + 控制器
    饱和补偿 sat(i_ref/i_sat)，i_sat_L=0.333 A, i_sat_LC=0.5 A。
"""
import math

P = {
    # ---- 电网与功率等级（技术文件口径） ----
    "P_rated": 200.0,            # [W]
    "Ug_rms": 36.0,              # [V]
    "fg": 50.0,                  # [Hz]
    "fsw": 20e3,                 # [Hz] 开关/控制频率
    "P_points": [70.0, 130.0, 200.0],
    "G_points": [400.0, 700.0, 1000.0],   # [W/m^2]

    # ---- 直流侧（对方设计值） ----
    "Vdc": 80.0,                 # [V] 额定母线（=PV MPP）
    "Cdc": 2200e-6,              # [F]
    "m_max": 0.95,

    # ---- 耦合网络（对方设计值；技术文件无规定） ----
    "L": 2.0e-3,                 # [H]
    "Rf": 0.05,                  # [Ω] 电感 ESR
    "C": 12e-6,                  # [F]
    "Rd": 1.0,                   # [Ω] 电容支路阻尼
    "Lg": 1.0e-3,                # [H] 电网/变压器漏感
    "Rg": 0.1,                   # [Ω]

    # ---- 死区（对方口径：全桥双极性，两个桥臂都有死区） ----
    "Td": 1e-6,                  # [s]
    "td_norm": 0.04,             # 2*Td/Tsw（ΔV = td_norm*Vdc = 3.2 V）
    "i_sat_L": 0.333,            # [A] 半个开关纹波峰峰值
    "i_sat_LC": 0.5,             # [A]
    "Tsoft": 0.05,               # [s] 软启动

    # ---- 准 PR（对方 pr_design 冻结值，50 Hz 预畸变 Tustin） ----
    "Kp_pr": 2*math.pi*500*2.0e-3/80.0,   # 0.0785398...（Kp∝L，500 Hz 穿越）
    "Kr_pr": 4.0,
    "f_bw_pr": 2.0,              # [Hz] 谐振半带宽
    "vmax_pr": 0.9,

    # ---- T/4 延时 PLL（对方 pll_step） ----
    "pll_Kp": 0.5,
    "pll_Ki": 30.0,
    "pll_vq_max": 20.0,          # [V]
    "pll_wint_max": 31.4,        # [rad/s]

    # ---- MPPT / 直流电压环（对方 mppt_step） ----
    "mppt_Kp": 0.6,              # [A/V]
    "mppt_Ki": 20.0,             # [A/(V·s)]
    "mppt_dV": 1.0,              # [V] P&O 步长
    "mppt_Tp": 0.5,              # [s] P&O 判决周期
    "mppt_Vmin": 58.0,
    "mppt_Vmax": 92.0,
    "mppt_Im_max": 8.5,          # [A]
    "mppt_V0": 79.0,             # 默认起点

    # ---- PV 单二极管（对方 pv_current.m 标定值） ----
    "pv": {"Isc": 2.9, "Voc": 96.0, "Nser": 160, "N": 1.058,
           "Rs": 0.937, "Rp": 300.0, "Ki": 1.3e-3, "Tvco": -0.13},

    # ---- 仿真数值 ----
    "nsub": 10,                  # 每控制拍子步数（dt = Ts/nsub = 5 µs）
    "ctrl_delay_beats": 1.5,     # 1 拍计算 + 0.5 拍 ZOH（对方 Td_ctrl）
}


def derived(p=P):
    """派生量"""
    d = {}
    d["wg"] = 2*math.pi*p["fg"]
    d["Ug_pk"] = math.sqrt(2)*p["Ug_rms"]
    d["Ts"] = 1.0/p["fsw"]
    d["Im_rated"] = math.sqrt(2)*p["P_rated"]/p["Ug_rms"]       # 7.857 A
    d["Im_rated_rms"] = p["P_rated"]/p["Ug_rms"]                # 5.556 A
    d["Im_ref"] = [math.sqrt(2)*Pw/p["Ug_rms"] for Pw in p["P_points"]]
    return d


D = derived()
