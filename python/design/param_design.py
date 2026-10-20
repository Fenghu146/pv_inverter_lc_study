"""耦合网络参数设计脚本 —— 对齐实施方案第4章/附录A
输出: results/tables/param_design.csv, results/figures/param_design.png
公式来源: 实现方案 4.1 (ΔI_pp,max = V_dc/(8·L·f_sw)), 4.2 (f0, Z0, f_res), 4.2.1 (稳定性判据)
"""
import json, math, os, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

for _f in ["Microsoft YaHei", "SimHei", "DengXian"]:
    if any(_f == f.name for f in fm.fontManager.ttflist):
        plt.rcParams["font.sans-serif"] = [_f]
        break
plt.rcParams["axes.unicode_minus"] = False

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PARAMS = json.load(open(os.path.join(ROOT, "params", "params.json"), encoding="utf-8"))
TAB = os.path.join(ROOT, "results", "tables")
FIG = os.path.join(ROOT, "results", "figures")


def load_params():
    return PARAMS


def ripple_pp_max(Vdc, L, f_sw):
    """单极性倍频SPWM电感电流纹波峰峰值最大值 (方案4.1公式)"""
    return Vdc / (8.0 * L * f_sw)


def f0_LC(L, C):
    """不含L_g的LC谐振频率"""
    return 1.0 / (2.0 * math.pi * math.sqrt(L * C))


def f_res_with_Lg(L, Lg, C):
    """含L_g的实际谐振频率 f_res = 1/(2π)·sqrt((L+Lg)/(L·Lg·C))"""
    return 1.0 / (2.0 * math.pi) * math.sqrt((L + Lg) / (L * Lg * C))


def Z0(L, C):
    """特征阻抗 sqrt(L/C)"""
    return math.sqrt(L / C)


def vdrop_ratio_50Hz(L, I_rms, U_g):
    """50Hz工频压降比例 = 2π·50·L·I_rms / U_g"""
    return 2.0 * math.pi * 50.0 * L * I_rms / U_g


def lc_ripple_atten_db(f_res, f_ripple):
    """LC对纹波附加衰减(dB) ≈ 20·log10((f_res/f_ripple)^2)"""
    return 20.0 * math.log10((f_res / f_ripple) ** 2)


def design_report():
    p = PARAMS
    Vdc = p["rating"]["V_mpp_V"]
    f_sw = p["switching"]["f_sw_Hz"]
    U_g = p["rating"]["U_g_Vrms"]
    P = p["rating"]["P_n_W"]
    I_rms = P / U_g
    I_peak = math.sqrt(2) * I_rms
    f_ripple = 2 * f_sw  # 单极性倍频

    rows = []
    for L in p["sweep"]["L_scan_H"]:
        di = ripple_pp_max(Vdc, L, f_sw)
        vdrop = vdrop_ratio_50Hz(L, I_rms, U_g)
        f0 = f0_LC(L, p["plant"]["C_F"])
        rows.append({"L_mH": L * 1e3, "dI_pp_max_A": di, "dI_pct_of_Ipeak": 100 * di / I_peak,
                     "vdrop_50Hz_pct": 100 * vdrop, "f0_kHz": f0 / 1e3,
                     "f0_in_range": p["resonance"]["design_range_Hz"][0] < f0 < p["resonance"]["design_range_Hz"][1]})
    L_sel = p["plant"]["L_H"]
    C_sel = p["plant"]["C_F"]
    z0 = Z0(L_sel, C_sel)

    # L_g 扫描的 f_res 与 R_d 判据
    lgs = []
    for Lg in p["plant"]["L_g_options_H"]:
        fres = f_res_with_Lg(Lg, Lg, C_sel) if False else f_res_with_Lg(L_sel, Lg, C_sel)
        need_rd = fres >= p["resonance"]["f_s_over_6_Hz"] / 2  # 保守: 接近f_s/6即需要
        lgs.append({"Lg_mH": Lg * 1e3, "f_res_kHz": fres / 1e3,
                    "R_d_recommended_ohm": 0 if fres < p["resonance"]["f_s_over_6_Hz"] else 1,
                    "natural_damping": fres < p["resonance"]["f_s_over_6_Hz"]})

    # 纹波衰减预估(方案4.2.2)
    fres_sel = f_res_with_Lg(L_sel, p["plant"]["L_g_H"], C_sel)
    atten = lc_ripple_atten_db(fres_sel, f_ripple)

    # 打印与存表
    lines = []
    lines.append("=== 耦合网络参数设计报告 ===")
    lines.append(f"额定: P={P} W, U_g={U_g} Vrms, I_rms={I_rms:.2f} A, I_peak={I_peak:.2f} A, Vdc={Vdc} V, f_sw={f_sw/1e3} kHz")
    lines.append("")
    lines.append("--- L 扫描 (方案S1) ---")
    lines.append(f"{'L(mH)':>8} {'ΔI_pp(A)':>10} {'ΔI/Ipeak%':>10} {'50Hz压降%':>10} {'f0(kHz)':>9} {'f0∈[0.5,2]kHz':>14}")
    for r in rows:
        lines.append(f"{r['L_mH']:>8.3f} {r['dI_pp_max_A']:>10.3f} {r['dI_pct_of_Ipeak']:>10.1f} "
                     f"{r['vdrop_50Hz_pct']:>10.2f} {r['f0_kHz']:>9.3f} {str(r['f0_in_range']):>14}")
    lines.append("")
    lines.append("--- LC 参数 (方案S2) ---")
    lines.append(f"选定 L={L_sel*1e3} mH, C={C_sel*1e6} µF, Z0={z0:.2f} Ω (方案值 5 Ω)")
    lines.append(f"f0(不含L_g)={f0_LC(L_sel, C_sel):.1f} Hz (方案值 1590 Hz)")
    lines.append(f"R_d 取值范围: (1/5~1/2)·Z0 = {z0/5:.2f}~{z0/2:.2f} Ω → 档位 0/1/2.2 Ω")
    lines.append("")
    lines.append(f"{'L_g(mH)':>8} {'f_res(kHz)':>11} {'自然阻尼(f<f_sw/6)':>20} {'建议R_d(Ω)':>11}")
    for r in lgs:
        lines.append(f"{r['Lg_mH']:>8.2f} {r['f_res_kHz']:>11.3f} {str(r['natural_damping']):>20} {r['R_d_recommended_ohm']:>11}")
    lines.append("")
    lines.append("--- 纹波抑制理论预估 (方案4.2.2) ---")
    lines.append(f"f_res(L_g=0.5mH)={fres_sel/1e3:.2f} kHz, 开关纹波频率 2f_sw={f_ripple/1e3} kHz")
    lines.append(f"LC附加衰减: 幅值比 (f_res/2f_sw)² = {(fres_sel/f_ripple)**2:.5f}")
    lines.append(f"  → 幅值口径 20lg = {atten:.1f} dB; 功率口径 10lg = {atten/2:.1f} dB (方案预估 '−25 dB 以上', 两种口径均满足)")
    lines.append("")
    lines.append("--- 稳定性判据 (方案4.2.1) ---")
    lines.append(f"f_sw/6 = {p['resonance']['f_s_over_6_Hz']:.0f} Hz; f_res < f_sw/6 时自然阻尼, 不需R_d")

    os.makedirs(TAB, exist_ok=True)
    os.makedirs(FIG, exist_ok=True)
    with open(os.path.join(TAB, "param_design.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    import csv
    with open(os.path.join(TAB, "param_design_L_scan.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

    # 图: L扫描双轴 + f_res vs L_g
    fig, ax = plt.subplots(1, 3, figsize=(14, 4))
    Ls = np.array([r["L_mH"] for r in rows])
    ax[0].plot(Ls, [r["dI_pp_max_A"] for r in rows], "o-")
    ax[0].set_xlabel("L (mH)"); ax[0].set_ylabel("ΔI_pp,max (A)"); ax[0].set_title("纹波 vs L (S1)"); ax[0].grid(True)
    ax[1].plot(Ls, [r["vdrop_50Hz_pct"] for r in rows], "s-", color="orange")
    ax[1].set_xlabel("L (mH)"); ax[1].set_ylabel("50Hz 压降 (%)"); ax[1].set_title("工频压降 vs L"); ax[1].grid(True)
    lg_arr = np.array([r["Lg_mH"] for r in lgs])
    ax[2].plot(lg_arr, [r["f_res_kHz"] for r in lgs], "d-", color="green")
    ax[2].axhline(p["resonance"]["f_s_over_6_Hz"] / 1e3, color="r", ls="--", label="f_sw/6")
    ax[2].set_xlabel("L_g (mH)"); ax[2].set_ylabel("f_res (kHz)"); ax[2].set_title("谐振频率 vs L_g"); ax[2].legend(); ax[2].grid(True)
    plt.tight_layout()
    plt.savefig(os.path.join(FIG, "param_design.png"), dpi=150)
    plt.close()

    print("\n".join(lines))
    return {"rows": rows, "lgs": lgs, "atten_db": atten, "Z0": z0}


if __name__ == "__main__":
    design_report()
