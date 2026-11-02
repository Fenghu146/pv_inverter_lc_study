# -*- coding: utf-8 -*-
"""工程口径参数源（唯一工程口径）

口径 = `params/params.json`（v1.0，源自 docx/《实现方案》附录A + 技术文件2），
即硬件/DSP/实验/报告采用的一套值：200 W / 36 Vrms / 50 Hz / f_sw 20 kHz /
L 0.5 mH / C 20 µF / R_d 0/1/2.2 Ω / L_g 0.5 mH / C_dc 4.5 mF / 死区 400 ns。

本模块不做第二次硬编码：所有数字都从 params.json 读，再按 engine.py 的键名与
量纲换算。换算规则逐条记在 PROVENANCE，docs/12 与 python/check_params.py 都读它。

与 params_merged.py 的关系：
  - params_merged.P  = 交叉验证口径（对方 Desktop/仿真/PV_LC_project 的设计值，
                       用于与对方基线逐位对齐，A0-A4 的既有数据）；
  - params_canonical.P = 工程口径（本模块），用于 A5 工程口径核心对比。
两者共享的部分（功率等级/电网/开关频率/THD 口径）必须一致，由 check_params.py 机器校验。

用途：`import params_merged; params_merged.use("canonical")`（见 params_merged.use）
"""
import json
import math
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_JSON = os.path.join(_HERE, os.pardir, "params", "params.json")


def load_json(path=_JSON):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


J = load_json()
R = J["rating"]
S = J["switching"]
PL = J["plant"]
CO = J["control"]
PR = J["protection"]
ME = J["metrics"]
PP = J["power_points"]

_FS = float(S["f_sw_Hz"])
_TS = 1.0/_FS
_TD = float(S["t_dead_ns"])*1e-9
_VDC = float(R["V_mpp_V"])
_L = float(PL["L_H"])
# 单极性倍频 SPWM 下电感电流纹波峰值（Vdc/(8·L·f_sw)），死区补偿饱和点取其一半
_DI_PP = _VDC/(8.0*_L*_FS)


def _pv_block():
    """PV 单二极管参数：json 有 pv_model（python/calib_pv.py --apply 写入）就用标定值，
    否则退回对方未标定值并置 pv_uncalibrated=True（A5 静态对比不依赖它）。
    fixed_i 静态对比不使用 PV 模型；MPPT 口径标定见 docs/12 §7。"""
    m = J.get("pv_model")
    if m:
        return ({"Isc": float(m["Isc_A"]), "Voc": float(m["Voc_V"]),
                 "Nser": float(m["Nser"]), "N": float(m["N"]),
                 "Rs": float(m["Rs_ohm"]), "Rp": float(m["Rp_ohm"]),
                 "Ki": float(m["Ki_per_K"]), "Tvco": float(m["Tvco_V_per_K"])}, False)
    return ({"Isc": float(R["Isc_A"]), "Voc": float(R["Voc_V"]),
             "Nser": 160.0, "N": 1.058, "Rs": 0.937, "Rp": 300.0,
             "Ki": 1.3e-3, "Tvco": -0.13}, True)


_PV_BLOCK, _PV_UNCAL = _pv_block()


P = {
    "profile": "canonical",
    "profile_name": "工程口径（《实现方案》/params/params.json）",

    # ---- 电网与功率等级（技术文件口径） ----
    "P_rated": float(R["P_n_W"]),
    "Ug_rms": float(R["U_g_Vrms"]),
    "fg": float(R["f_g_Hz"]),
    "fsw": _FS,
    "P_points": [float(pp["P_W_approx"]) for pp in PP],
    "G_points": [1000.0*float(pp["irradiance"]) for pp in PP],

    # ---- 直流侧（《实现方案》：MPPT 窗口 62-85 V，额定母线 = V_mpp） ----
    "Vdc": _VDC,
    "Cdc": float(PL["C_dc_F"]),
    "m_max": float(CO["modulation_limit"]),

    # ---- 耦合网络（《实现方案》4.1/4.2） ----
    "L": _L,
    "Rf": float(PL["R_parasitic_ohm"]),
    "C": float(PL["C_F"]),
    "Rd": float(PL["R_d_default_ohm"]),
    "Lg": float(PL["L_g_H"]),
    "Rg": 0.1,

    # ---- 死区（全桥双极性，两桥臂各 t_dead） ----
    "Td": _TD,
    "td_norm": 2.0*_TD/_TS,
    "i_sat_L": _DI_PP/2.0,
    "i_sat_LC": _DI_PP/2.0,
    "Tsoft": 0.05,

    # ---- 准 PR（DSP 侧 V/A 增益 ÷ V_dc 得到调制指数/A，量纲与 engine 一致） ----
    "Kp_pr": float(CO["current_pr_kp"])/_VDC,
    "Kr_pr": float(CO["current_pr_kr"])/_VDC,
    "f_bw_pr": float(CO["current_pr_wc_rad_s"])/(2.0*math.pi),
    "vmax_pr": float(CO["modulation_limit"]),

    # ---- PLL：引擎实现为 T/4 延时结构，工程口径为 SOGI 结构（结构不可移植） ----
    "pll_Kp": float(CO["pll_pi_kp"]),
    "pll_Ki": float(CO["pll_pi_ki"]),
    "pll_vq_max": 20.0,
    "pll_wint_max": 2.0*math.pi*10.0,     # PLL_DW_LIM ±10 Hz

    # ---- MPPT / 直流电压环（《实现方案》：0.5 V/100 ms，V 62-75 V） ----
    "mppt_Kp": float(CO["voltage_pi_kp"]),
    "mppt_Ki": float(CO["voltage_pi_ki"]),
    "mppt_dV": float(CO["mppt_dV_V"]),
    "mppt_Tp": float(CO["mppt_T_ms"])/1000.0,
    "mppt_Vmin": float(CO["Vdc_ref_limit_V"][0]),
    "mppt_Vmax": float(CO["Vdc_ref_limit_V"][1]),
    "mppt_Im_max": float(CO["I_amp_limit_A"][1]),
    "mppt_V0": float(CO["mppt_init_frac_Voc"])*float(R["Voc_V"]),

    # ---- PV：fixed_i 静态对比不使用；MPPT 口径见 docs/12 ----
    "pv": dict(_PV_BLOCK),
    "pv_uncalibrated": _PV_UNCAL,

    # ---- 仿真数值 ----
    "nsub": 10,
    "ctrl_delay_beats": 1.5,

    # ---- 口径附注（供文档/校验器引用，非 engine 键） ----
    "R_d_options": [float(v) for v in PL["R_d_options_ohm"]],
    "meas": {"thd_harmonic_range": ME["thd_harmonic_range"],
             "thd_window_ms": ME["thd_window_ms"],
             "freq_resolution_Hz": ME["freq_resolution_Hz"],
             "ripple_hp_cutoff_Hz": ME["ripple_hp_cutoff_Hz"],
             "ripple_target_freq_Hz": ME["ripple_target_freq_Hz"]},
}

# 换算溯源：engine 键 -> (值, 来源/规则)。check_params.py 与 docs/12 直接引用。
PROVENANCE = [
    ("P_rated", P["P_rated"], "rating.P_n_W"),
    ("Ug_rms", P["Ug_rms"], "rating.U_g_Vrms"),
    ("fg", P["fg"], "rating.f_g_Hz"),
    ("fsw", P["fsw"], "switching.f_sw_Hz"),
    ("Vdc", P["Vdc"], "rating.V_mpp_V（额定母线 = PV MPP 电压）"),
    ("Cdc", P["Cdc"], "plant.C_dc_F"),
    ("L", P["L"], "plant.L_H"),
    ("Rf", P["Rf"], "plant.R_parasitic_ohm（电感 ESR）"),
    ("C", P["C"], "plant.C_F"),
    ("Rd", P["Rd"], "plant.R_d_default_ohm（LC 阻尼默认档；A5 扫 0/1/2.2）"),
    ("Lg", P["Lg"], "plant.L_g_H（隔离变压器漏感）"),
    ("Rg", P["Rg"], "—（工程口径未规定，取 0.1 Ω，与对方一致）"),
    ("Td", P["Td"], "switching.t_dead_ns"),
    ("td_norm", P["td_norm"], "2·t_dead/Ts（两桥臂死区；ΔV = td_norm·Vdc = %.2f V）" % (P["td_norm"]*P["Vdc"])),
    ("i_sat_L/i_sat_LC", P["i_sat_L"], "Δi_pp/2 = Vdc/(8·L·f_sw)/2 = %.4f A（按工程口径重算，非对方值）" % (_DI_PP/2)),
    ("Kp_pr", P["Kp_pr"], "control.current_pr_kp ÷ V_mpp（V/A → 调制指数/A）"),
    ("Kr_pr", P["Kr_pr"], "control.current_pr_kr ÷ V_mpp"),
    ("f_bw_pr", P["f_bw_pr"], "control.current_pr_wc_rad_s ÷ 2π"),
    ("vmax_pr", P["vmax_pr"], "control.modulation_limit"),
    ("pll_Kp/pll_Ki", P["pll_Kp"], "control.pll_pi_kp/ki（结构为 T/4 延时，非 SOGI，仅标称值借用）"),
    ("pll_wint_max", P["pll_wint_max"], "±10 Hz 频率限幅"),
    ("mppt_dV/mppt_Tp", P["mppt_dV"], "control.mppt_dV_V / mppt_T_ms"),
    ("mppt_Vmin/mppt_Vmax", P["mppt_Vmin"], "control.Vdc_ref_limit_V"),
    ("mppt_V0", P["mppt_V0"], "mppt_init_frac_Voc × rating.Voc_V"),
    ("mppt_Kp/mppt_Ki", P["mppt_Kp"], "control.voltage_pi_kp/ki"),
    ("mppt_Im_max", P["mppt_Im_max"], "control.I_amp_limit_A[1]"),
]


def derived(p=P):
    """与 params_merged.derived 同构（供 params_merged.use('canonical') 使用）"""
    d = {}
    d["wg"] = 2*math.pi*p["fg"]
    d["Ug_pk"] = math.sqrt(2)*p["Ug_rms"]
    d["Ts"] = 1.0/p["fsw"]
    d["Im_rated"] = math.sqrt(2)*p["P_rated"]/p["Ug_rms"]
    d["Im_rated_rms"] = p["P_rated"]/p["Ug_rms"]
    d["Im_ref"] = [math.sqrt(2)*Pw/p["Ug_rms"] for Pw in p["P_points"]]
    return d


if __name__ == "__main__":
    import pprint
    pprint.pprint(P)
    print("\n派生量:")
    pprint.pprint(derived())