# -*- coding: utf-8 -*-
"""参数口径机器交叉校验器（P0 的"单一真源 + 交叉校验"落地）

真源：params/params.json（唯一工程口径，《实现方案》体系）
被校验对象：
  1) params.json 内部自洽（谐振频率、TBPRD、Z0、功率点、设计区间）
  2) dsp/include/param.h 的 #define 与 json 逐项一致
  3) python/params_canonical.py（工程口径参数源）与 json 逐项一致
  4) python/params_merged.py（交叉验证口径）与 json 的**共享项**一致；
     刻意不同的项（植物参数/控制律系数）必须在 WHITELIST_DIFF 中登记
  5) docs/01、docs/02 冻结口径文本与 json 一致
  6) docs/12 声明的口径与 json 一致（口径文档不得漂移）

用法：python python/check_params.py [--csv]
退出码：0 = 全部通过（FAIL 数为 0）；1 = 存在 FAIL
输出：results/tables/params_check.csv
"""
import json
import math
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(_HERE, os.pardir))
sys.path.insert(0, _HERE)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROWS = []


def rec(section, item, expected, actual, verdict, note=""):
    ROWS.append({"section": section, "item": item, "expected": expected,
                 "actual": actual, "verdict": verdict, "note": note})


def close(section, item, expected, actual, tol=1e-9, abs_tol=None, note=""):
    """数值/字符串比对：abs_tol 优先，否则相对 tol"""
    try:
        e, a = float(expected), float(actual)
    except (TypeError, ValueError):
        v = "PASS" if str(expected) == str(actual) else "FAIL"
        rec(section, item, expected, actual, v, note)
        return v == "PASS"
    d = abs(e - a)
    ok = (d <= abs_tol) if abs_tol is not None else (d <= tol*max(abs(e), 1e-12))
    rec(section, item, expected, actual, "PASS" if ok else "FAIL", note)
    return ok


def want(section, item, expected, actual, note=""):
    ok = (expected == actual)
    rec(section, item, expected, actual, "PASS" if ok else "FAIL", note)
    return ok


def info(section, item, value, note=""):
    rec(section, item, value, value, "INFO", note)


# ---------------------------------------------------------------- 真源
with open(os.path.join(ROOT, "params", "params.json"), encoding="utf-8") as f:
    J = json.load(f)
R, S, PL = J["rating"], J["switching"], J["plant"]
RES, CO, PR = J["resonance"], J["control"], J["protection"]
ME, SW, PTS = J["metrics"], J["sweep"], J["power_points"]

FS = float(S["f_sw_Hz"])
TS = 1.0/FS
L = float(PL["L_H"])
C = float(PL["C_F"])
LG = float(PL["L_g_H"])
TD = float(S["t_dead_ns"])*1e-9
VDC = float(R["V_mpp_V"])
UG = float(R["U_g_Vrms"])
FG = float(R["f_g_Hz"])
PN = float(R["P_n_W"])

# ================================================================ 1) json 自洽
f0 = 1.0/(2*math.pi*math.sqrt(L*C))
close("json 自洽", "f0_without_Lg vs 1/(2π√(LC))", RES["f0_without_Lg_Hz"], f0,
      tol=0.01, note="文档取整值 1590")
for key, lg in (("f_res_Lg05_Hz", LG), ("f_res_Lg01_Hz", float(PL["L_g_options_H"][0]))):
    f_res = 1.0/(2*math.pi)*math.sqrt((L + lg)/(L*lg*C))
    close("json 自洽", "%s vs 公式" % key, RES[key], f_res, tol=0.01)
close("json 自洽", "f_s_over_6_Hz", RES["f_s_over_6_Hz"], FS/6.0, tol=0.01)
want("json 自洽", "design_range_Hz == [10·f_g, f_sw/10]",
     [10*FG, FS/10.0], RES["design_range_Hz"], "谐振必须避开工频与开关频率")
close("json 自洽", "TBPRD vs EPWMCLK/(2·f_sw)", S["TBPRD"], float(S["EPWMCLK_Hz"])/(2*FS), abs_tol=0.5)
close("json 自洽", "Z0 vs √(L/C)", RES["Z0_ohm"], math.sqrt(L/C), tol=0.01)
for pp in PTS:
    close("json 自洽", "power_points %s ≈ irr×P_n" % pp["id"],
          pp["P_W_approx"], pp["irradiance"]*PN, tol=0.03, note="70/130/180 W")
close("json 自洽", "I_mpp vs P_n/V_mpp", R["I_mpp_A"], PN/VDC, tol=0.05,
      note="2.7 vs %.3f（文档取整）" % (PN/VDC))
close("json 自洽", "死区补偿 ΔV = 2·t_dead/Ts·V_mpp", 1.2,
      2*TD/TS*VDC, tol=0.02, note="与 param.h DT_COMP_COEF·Vdc 对照")

# ================================================================ 2) param.h
_H = os.path.join(ROOT, "dsp", "include", "param.h")
src = re.sub(r"/\*.*?\*/", " ", open(_H, encoding="utf-8").read(), flags=re.S)
_DEF = {}
for line in src.splitlines():
    m = re.match(r"\s*#define\s+([A-Za-z_]\w*)\s+(.*)$", line)
    if m and m.group(2).strip():
        _DEF[m.group(1)] = m.group(2).strip()
_VALS = {}


def pv(name, depth=0):
    """param.h 宏求值（剥离 f/u 后缀、递归展开已定义宏）"""
    if name in _VALS:
        return _VALS[name]
    if name not in _DEF or depth > 8:
        return None
    e = _DEF[name]
    e = re.sub(r"\b(\d+\.?\d*(?:[eE][+-]?\d+)?)[fFuU]\b", r"\1", e)
    e = re.sub(r"\b(\d+)[uU]\b", r"\1", e)
    e = re.sub(r"\b[A-Za-z_]\w*\b",
               lambda mm: ("(%r)" % pv(mm.group(0), depth+1)) if pv(mm.group(0), depth+1) is not None else "0",
               e)
    try:
        _VALS[name] = float(eval(e, {"__builtins__": {}}, {}))
    except Exception:
        _VALS[name] = None
    return _VALS[name]


H_PAIRS = [
    ("CTRL_FS_HZ", FS, "switching.f_sw_Hz"),
    ("CTRL_TS_S", TS, "1/f_sw"),
    ("GRID_U_RMS_NOM_V", UG, "rating.U_g_Vrms"),
    ("GRID_F_NOM_HZ", FG, "rating.f_g_Hz"),
    ("SOGI_K", CO["pll_sogi_k"], "control.pll_sogi_k"),
    ("PLL_KP", CO["pll_pi_kp"], "control.pll_pi_kp"),
    ("PLL_KI", CO["pll_pi_ki"], "control.pll_pi_ki"),
    ("PR_KP", CO["current_pr_kp"], "control.current_pr_kp"),
    ("PR_KR", CO["current_pr_kr"], "control.current_pr_kr"),
    ("PR_WC_RAD_S", CO["current_pr_wc_rad_s"], "control.current_pr_wc_rad_s"),
    ("MOD_DUTY_LIM", CO["modulation_limit"], "control.modulation_limit"),
    ("VDC_KP", CO["voltage_pi_kp"], "control.voltage_pi_kp"),
    ("VDC_KI", CO["voltage_pi_ki"], "control.voltage_pi_ki"),
    ("IAMP_MAX_A", CO["I_amp_limit_A"][1], "control.I_amp_limit_A[1]"),
    ("IAMP_MIN_A", CO["I_amp_limit_A"][0], "control.I_amp_limit_A[0]"),
    ("MPPT_DV_V", CO["mppt_dV_V"], "control.mppt_dV_V"),
    ("MPPT_PERIOD_S", CO["mppt_T_ms"]/1000.0, "control.mppt_T_ms"),
    ("MPPT_AVG_SAMPLES", CO["mppt_T_ms"]/1000.0*FS, "control.mppt_T_ms × f_sw"),
    ("MPPT_V_MIN_V", CO["Vdc_ref_limit_V"][0], "control.Vdc_ref_limit_V[0]"),
    ("MPPT_V_MAX_V", CO["Vdc_ref_limit_V"][1], "control.Vdc_ref_limit_V[1]"),
    ("MPPT_V_INIT_FRAC", CO["mppt_init_frac_Voc"], "control.mppt_init_frac_Voc"),
    ("OC_SOFT_A", PR["I_oc_soft_A"], "protection.I_oc_soft_A"),
    ("OC_HARD_A", PR["I_oc_hard_A"], "protection.I_oc_hard_A"),
    ("VDC_OV_V", PR["V_dc_ov_V"], "protection.V_dc_ov_V"),
    ("VDC_UV_V", PR["V_dc_uv_V"], "protection.V_dc_uv_V"),
    ("VAC_RMS_MIN_V", PR["U_g_range_Vrms"][0], "protection.U_g_range_Vrms[0]"),
    ("VAC_RMS_MAX_V", PR["U_g_range_Vrms"][1], "protection.U_g_range_Vrms[1]"),
    ("FREQ_MIN_HZ", PR["f_g_range_Hz"][0], "protection.f_g_range_Hz[0]"),
    ("FREQ_MAX_HZ", PR["f_g_range_Hz"][1], "protection.f_g_range_Hz[1]"),
    ("PWM_CLK_HZ", S["EPWMCLK_Hz"], "switching.EPWMCLK_Hz"),
    ("PWM_TBPRD", S["TBPRD"], "switching.TBPRD"),
    ("DEADTIME_NS", S["t_dead_ns"], "switching.t_dead_ns"),
    ("DT_COMP_COEF", 2*TD/TS, "2·t_dead/Ts（死区补偿系数）"),
]
for name, exp, src_note in H_PAIRS:
    v = pv(name)
    if v is None:
        rec("dsp/param.h", name, exp, "解析失败", "WARN", src_note)
    else:
        close("dsp/param.h", "%s ← %s" % (name, src_note), exp, v, abs_tol=1e-6)
info("dsp/param.h", "L / C / R_d / L_g / C_dc", "固件不引用",
     "这 5 个量只在 params.json、MATLAB、文档中；DSP 侧无需知道耦合网络元件值")

# ================================================================ 3) params_canonical
import params_canonical as PC   # noqa: E402
P = PC.P
C_PAIRS = [
    ("P_rated", PN), ("Ug_rms", UG), ("fg", FG), ("fsw", FS),
    ("Vdc", VDC), ("Cdc", PL["C_dc_F"]), ("L", L), ("C", C), ("Lg", LG),
    ("Rf", PL["R_parasitic_ohm"]), ("Rd", PL["R_d_default_ohm"]),
    ("Td", TD), ("td_norm", 2*TD/TS),
    ("Kp_pr", CO["current_pr_kp"]/VDC), ("Kr_pr", CO["current_pr_kr"]/VDC),
    ("f_bw_pr", CO["current_pr_wc_rad_s"]/(2*math.pi)),
    ("vmax_pr", CO["modulation_limit"]),
    ("mppt_dV", CO["mppt_dV_V"]), ("mppt_Tp", CO["mppt_T_ms"]/1000.0),
    ("mppt_Vmin", CO["Vdc_ref_limit_V"][0]), ("mppt_Vmax", CO["Vdc_ref_limit_V"][1]),
    ("mppt_Kp", CO["voltage_pi_kp"]), ("mppt_Ki", CO["voltage_pi_ki"]),
]
for k, exp in C_PAIRS:
    close("params_canonical", "%s ← json" % k, exp, P[k], abs_tol=1e-9)
want("params_canonical", "P_points ← power_points", [70.0, 130.0, 180.0], P["P_points"])
want("params_canonical", "G_points ← irradiance×1000", [350.0, 650.0, 900.0], P["G_points"])
want("params_canonical", "R_d_options", PL["R_d_options_ohm"], P["R_d_options"])
want("params_canonical", "meas 口径", ME["thd_harmonic_range"], P["meas"]["thd_harmonic_range"])
_PVM = J.get("pv_model")
if _PVM:
    # PV 已标定（python/calib_pv.py --apply）：标记必须为 False，且四个目标点在 json 里自洽
    want("params_canonical", "PV 已标定标记", False, P.get("pv_uncalibrated", True),
         "json 有 pv_model 块 ⇒ 已标定（docs/12 §7 已闭环）")
    want("params_canonical", "pv.N ← json pv_model", float(_PVM["N"]), P["pv"]["N"])
    want("params_canonical", "pv.Rp ← json pv_model", float(_PVM["Rp_ohm"]), P["pv"]["Rp"])
    want("params_canonical", "pv.Rs 不可辨识（固定物理值）", True, bool(_PVM.get("Rs_identifiable") is False),
         "四目标点对 Rs 不敏感，固定 0.937 Ω，见 results/tables/pv_calibration.csv")
    close("json 自洽", "pv_model Vmpp ← targets", float(_PVM["targets"]["Vmpp_V"]),
          float(_PVM["achieved"]["Vmpp_V"]), abs_tol=0.1)
    close("json 自洽", "pv_model Impp ← targets", float(_PVM["targets"]["Impp_A"]),
          float(_PVM["achieved"]["Impp_A"]), abs_tol=0.01)
else:
    want("params_canonical", "PV 未标定标记", True, P.get("pv_uncalibrated", False),
         "fixed_i 静态对比不使用 PV；MPPT 口径待标定（python/calib_pv.py --apply 后自动转为已标定）")

# ================================================================ 4) params_merged 共享项
import params_merged as PM   # noqa: E402
M = PM.P
SHARED = [("P_rated", PN), ("Ug_rms", UG), ("fg", FG), ("fsw", FS)]
for k, exp in SHARED:
    close("params_merged 共享项", "%s 必须与工程口径一致" % k, str(exp),
          str(M.get(k, "<缺失>")),
          note="功率等级/电网/开关频率为两口径共享")
# 刻意不同项：白名单登记（口径差异，不是错误）
WHITELIST_DIFF = {
    "Vdc": "80 V（对方）vs 75 V（工程）",
    "Cdc": "2.2 mF vs 4.5 mF（受 MPPT 扰动周期匹配影响）",
    "L": "2 mH vs 0.5 mH",
    "C": "12 µF vs 20 µF",
    "Rd": "1 Ω（对方折中）vs 0/1/2.2 档（工程）",
    "Lg": "1 mH vs 0.5 mH",
    "Rf": "50 mΩ vs 100 mΩ",
    "Td": "1 µs vs 400 ns",
    "td_norm": "0.04（ΔV 3.2 V）vs 0.016（ΔV 1.2 V）",
    "Kp_pr": "0.0785（对方 500 Hz 穿越）vs 0.0627（DSP 4.7 V/A ÷ 75 V）",
    "Kr_pr": "4.0 vs 4.0（数值巧合：300/75 也等于 4）",
    "f_bw_pr": "2 Hz（对方）vs 0.795 Hz（DSP ωc=5 rad/s）",
    "pll_Kp": "0.5 / Ki 30（T/4 结构）vs 0.67 / 22（DSP SOGI 标称）",
    "mppt_dV": "1 V / 0.5 s（对方）vs 0.5 V / 0.1 s（工程，匹配 4.5 mF）",
    "mppt_Vmax": "92 V vs 75 V",
    "mppt_Kp": "0.6 / 20 vs 0.2 / 5",
    "i_sat_L": "0.333 A vs 0.469 A（Δi_pp/2 按工程口径重算）",
    "pv": "Voc 96/80 V 标定 vs 待标定（Voc 90 / MPP 75 V）",
}
for k in ("Vdc", "Cdc", "L", "C", "Rd", "Lg", "Rf", "Td", "td_norm", "Kp_pr",
          "f_bw_pr", "pll_Kp", "mppt_dV", "mppt_Vmax", "mppt_Kp", "i_sat_L", "pv"):
    if k in WHITELIST_DIFF:
        info("params_merged 差异项（已登记）", k, "%.6g" % M[k] if isinstance(M[k], (int, float)) else "…",
             WHITELIST_DIFF[k])
    else:
        rec("params_merged 差异项（未登记）", k, "需登记到 WHITELIST_DIFF", M[k], "FAIL",
            "口径差异必须显式登记，不得默默并存")
info("params_merged 差异项（已登记）", "G_points", "400/700/1000 vs 350/650/900",
     "对方按 0.4/0.7/1.0 倍辐照；工程按 35/65/90%")
info("params_merged 差异项（已登记）", "P_points", "70/130/200 vs 70/130/180",
     "对方第三点取额定 200 W；工程按 90% 辐照 ≈180 W（docs/01 S4、docs/02 E3/E6 口径）")
info("params_merged 差异项（已登记）", "R_d 档位", "标量 Rd=1 Ω vs 0/1/2.2 Ω 三档",
     "对方取折中值；工程保留 0/1/2.2 三档（params.json plant.R_d_options_ohm）")

# ================================================================ 5) docs 冻结口径
DOC_TOKENS = {
    "docs/01_implementation_plan.md": [
        (r"20\s*kHz", "f_sw 20 kHz"), (r"0\.5\s*mH", "L 0.5 mH"),
        (r"20\s*µF", "C 20 µF"), (r"0\s*/\s*1\s*/\s*2\.2", "R_d 0/1/2.2 Ω"),
        (r"0\.5\s*mH", "L_g 0.5 mH"), (r"4\.5\s*mF", "C_dc 4.5 mF"),
        (r"400\s*ns", "死区 400 ns"), (r"36\s*V", "交流 36 V"), (r"F28379D", "平台 F28379D"),
    ],
    "docs/02_experiment_protocol.md": [
        (r"20\s*kHz", "f_sw 20 kHz"), (r"0\.5\s*mH", "L 0.5 mH"),
        (r"20\s*µF", "C 20 µF"), (r"4\.5\s*mF", "C_dc 4.5 mF"),
        (r"400\s*ns", "死区 400 ns"), (r"36\s*V", "交流 36 V"),
    ],
}
for doc, toks in DOC_TOKENS.items():
    path = os.path.join(ROOT, doc.replace("/", os.sep))
    if not os.path.exists(path):
        rec("docs 冻结口径", doc, "文件存在", "缺失", "FAIL")
        continue
    text = open(path, encoding="utf-8").read()
    for pat, label in toks:
        rec("docs 冻结口径", "%s: %s" % (doc.split("/")[-1], label), "出现", 
            "出现" if re.search(pat, text) else "未出现",
            "PASS" if re.search(pat, text) else "FAIL", "冻结口径文本必须与 params.json 一致")

# ================================================================ 6) docs/12 口径声明
d12 = os.path.join(ROOT, "docs", "12_参数口径与单一真源.md")
if os.path.exists(d12):
    t12 = open(d12, encoding="utf-8").read()
    for pat, label in ((r"params/params\.json", "真源路径"), (r"36\s*V", "交流 36 V"),
                       (r"0\.5\s*mH", "L 0.5 mH"), (r"20\s*µF", "C 20 µF"),
                       (r"400\s*ns", "死区 400 ns"), (r"4\.5\s*mF", "C_dc 4.5 mF")):
        rec("docs/12 口径", label, "出现", "出现" if re.search(pat, t12) else "未出现",
            "PASS" if re.search(pat, t12) else "FAIL")
else:
    rec("docs/12 口径", "docs/12_参数口径与单一真源.md", "存在", "缺失", "WARN",
        "口径文档未写（先建文档再校验）")

# ================================================================ 输出
csv_path = os.path.join(ROOT, "results", "tables", "params_check.csv")
os.makedirs(os.path.dirname(csv_path), exist_ok=True)
with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
    f.write("section,item,expected,actual,verdict,note\n")
    for r in ROWS:
        f.write(",".join('"%s"' % str(r[k]).replace('"', "'")
                         for k in ("section", "item", "expected", "actual", "verdict", "note")) + "\n")

n_pass = sum(1 for r in ROWS if r["verdict"] == "PASS")
n_fail = sum(1 for r in ROWS if r["verdict"] == "FAIL")
n_warn = sum(1 for r in ROWS if r["verdict"] == "WARN")
n_info = sum(1 for r in ROWS if r["verdict"] == "INFO")
seen = set()
for r in ROWS:
    if r["verdict"] == "FAIL":
        print("FAIL  [%s] %s | 期望 %s | 实际 %s | %s"
              % (r["section"], r["item"], r["expected"], r["actual"], r["note"]))
    elif r["verdict"] == "WARN":
        print("WARN  [%s] %s | %s" % (r["section"], r["item"], r["note"]))
    elif r["section"] not in seen:
        seen.add(r["section"])
        print("PASS  [%s] 其余 %d 项通过" % (r["section"],
              sum(1 for x in ROWS if x["section"] == r["section"] and x["verdict"] == "PASS")))
print("\n合计：PASS %d / FAIL %d / WARN %d / INFO %d（明细 %s）"
      % (n_pass, n_fail, n_warn, n_info, os.path.relpath(csv_path, ROOT)))
sys.exit(1 if n_fail else 0)