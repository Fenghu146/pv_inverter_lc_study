"""仿真任务运行器 S1–S6 —— 对齐实施方案 6.2 仿真任务清单
S1: L值扫描 (0.3/0.5/0.75/1.0/1.5 mH) 额定功率 → L选型表+曲线
S2: LC 参数谐振频率表(C=10/20/30µF × L_g=0.1/0.3/0.5mH × R_d=0/1/2.2Ω) + Bode(i_g/v_ab)
S3: 稳定性: 电流环开环 Bode 与闭环极点(含1.5拍延时) → 相位裕度 ≥30°
S4: 3功率点(35%/65%/90%) L vs LC 稳态对比 → i_g波形/FFT/THD/纹波
S5: 动态: 辐照 35%→90% 阶跃、电网 +10% 阶跃 → 过渡波形/超调/调节时间
S6: MPPT 跟踪效率与 P&O 步长/周期敏感性 → η_MPPT
输出: data/sim_results/*.csv, results/tables/sim_summary.{csv,json}, results/figures/S*.png
"""
import csv
import json
import math
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from inverter_sim import InverterSim, PowerStage
from analysis import metrics
from control_algos import PRController
from pv_model import PVArray

for _f in ["Microsoft YaHei", "SimHei", "DengXian"]:
    if any(_f == f.name for f in fm.fontManager.ttflist):
        plt.rcParams["font.sans-serif"] = [_f]
        break
plt.rcParams["axes.unicode_minus"] = False

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
P = json.load(open(os.path.join(ROOT, "params", "params.json"), encoding="utf-8"))
DATA = os.path.join(ROOT, "data", "sim_results")
TAB = os.path.join(ROOT, "results", "tables")
FIG = os.path.join(ROOT, "results", "figures")
for d in (DATA, TAB, FIG):
    os.makedirs(d, exist_ok=True)

Ts = 1.0 / P["switching"]["f_s_Hz"]
FS_SW = 1.0 / (Ts / 20.0)   # switched 模式输出采样率 400 kHz


def save_csv(name, res):
    path = os.path.join(DATA, name)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "i_g_A", "i_L_A", "v_dc_V", "v_c_V", "i_amp_A", "fs_Hz"])
        for i in range(len(res["t"])):
            w.writerow([f"{res['t'][i]:.9g}", f"{res['i_g'][i]:.6g}", f"{res['i_L'][i]:.6g}",
                        f"{res['v_dc'][i]:.6g}", f"{res['v_c'][i]:.6g}", f"{res['i_amp'][i]:.6g}",
                        f"{res['fs']:.9g}"])
    return path


def steady_metrics(res, t_skip=0.4):
    """取稳态段(跳过前t_skip)做统一口径分析"""
    t = res["t"]
    m = t >= t_skip
    return metrics.full_metrics(res["i_g"][m], res["fs"])


def _fixed_i_amp(P_W):
    """FIXED_I 模式电流幅值指令: I_amp = √2·P/U_g (方案5.3 对比实验模式, 排除MPPT扰动)"""
    return math.sqrt(2) * P_W / P["rating"]["U_g_Vrms"]


# ---------- S1: L 扫描 ----------
def s1():
    rows = []
    Ls = P["sweep"]["L_scan_H"]
    i_amp = _fixed_i_amp(P["rating"]["P_n_W"])   # 额定 200 W
    fig, axes = plt.subplots(1, len(Ls), figsize=(3.2 * len(Ls), 3), sharey=True)
    for idx, L in enumerate(Ls):
        sim = InverterSim("L", L=L, power_point=1.0, mode="switched")
        res = sim.run(t_end=0.8, mppt=False, fixed_i_amp=i_amp)   # FIXED_I 同工况对比
        save_csv(f"S1_L{L*1e3:.2f}mH.csv", res)
        m = steady_metrics(res)
        i_rms = float(np.sqrt(np.mean(res["i_g"][res["t"] >= 0.4] ** 2)))
        vdrop = 2 * math.pi * 50 * L * i_rms / P["rating"]["U_g_Vrms"]
        rows.append({"L_mH": L * 1e3, "thd_pct": m["thd_pct"], "ripple_pp_A": m["ripple_pp_A"],
                     "sw40k_pct_fund": m["sw40k_pct_fund"], "vdrop_50Hz_pct": 100 * vdrop})
        t, ig = res["t"], res["i_g"]
        sel = (t > 0.6) & (t < 0.61)
        axes[idx].plot(t[sel] * 1e3, ig[sel], lw=0.7)
        axes[idx].set_title(f"L={L*1e3} mH")
        axes[idx].set_xlabel("t (ms)"); axes[idx].grid(True, alpha=0.3)
    axes[0].set_ylabel("i_g (A)")
    plt.tight_layout()
    plt.savefig(os.path.join(FIG, "S1_L_sweep.png"), dpi=150)
    plt.close()
    return rows


# ---------- S2: LC 谐振频率表 + Bode(i_g/v_ab) ----------
def s2():
    L = P["plant"]["L_H"]
    rows = []
    for C in P["sweep"]["C_scan_F"]:
        for Lg in P["plant"]["L_g_options_H"]:
            f0 = 1 / (2 * math.pi * math.sqrt(L * C))
            f_res = 1 / (2 * math.pi) * math.sqrt((L + Lg) / (L * Lg * C))
            rows.append({"C_uF": C * 1e6, "Lg_mH": Lg * 1e3, "f0_kHz": f0 / 1e3,
                         "f_res_kHz": f_res / 1e3,
                         "natural_damping": f_res < P["resonance"]["f_s_over_6_Hz"]})
    # Bode i_g/v_ab: L 结构 vs LC 结构(3档R_d), u_g 短路小信号
    w = np.logspace(2, 5.2, 1200)
    s = 1j * w
    r = P["plant"]["R_parasitic_ohm"]
    Lg = P["plant"]["L_g_H"]
    C = P["plant"]["C_F"]
    G_L = 1.0 / ((L + Lg) * s + r)                       # i_g/v_ab (L结构)
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    ax[0].semilogx(w, 20 * np.log10(np.abs(G_L)), label="L", lw=1.5)
    ax[1].semilogx(w, np.angle(G_L, deg=True), label="L", lw=1.5)
    for Rd in P["sweep"]["R_d_scan_ohm"]:
        ps = PowerStage("LC", Rd=Rd)
        A, B = ps.Ad, ps.Bd   # 离散→用连续矩阵重算频响: Z(s)=C(sI-A)^-1B
        # 直接用连续 A,B 求频响
        Ac = np.zeros((3, 3))
        Ac[0] = [-r / L, 0, -1 / L]
        Ac[2] = [1 / C, -1 / C, (-1 / (Rd * C) if Rd > 0 else 0)]
        Ac[1] = [0, 0, 1 / Lg]
        Bc = np.zeros((3, 2)); Bc[0, 0] = 1 / L; Bc[1, 1] = -1 / Lg
        G = np.array([0.0, 1.0, 0.0])
        H = np.array([complex(np.dot(G, np.linalg.solve(wi * np.eye(3) - Ac, Bc[:, 0])))
                      for wi in w])
        lbl = f"LC, R_d={Rd} Ω"
        ax[0].semilogx(w, 20 * np.log10(np.abs(H)), label=lbl, lw=1.2)
        ax[1].semilogx(w, np.angle(H, deg=True), label=lbl, lw=1.2)
    f_res_sel = 1 / (2 * math.pi) * math.sqrt((L + Lg) / (L * Lg * C))
    for a, ttl in zip(ax, ["幅频 |i_g/v_ab|", "相频 ∠(i_g/v_ab)"]):
        a.axvline(f_res_sel, color="r", ls="--", lw=0.8)
        a.set_xlabel("ω (rad/s)"); a.set_title(f"{ttl} (f_res={f_res_sel/1e3:.2f} kHz)")
        a.grid(True, alpha=0.3); a.legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(os.path.join(FIG, "S2_bode_ig_vab.png"), dpi=150)
    plt.close()
    return rows


# ---------- S3: 稳定性 (开环Bode + 闭环极点, 含1.5拍延时) ----------
def s3():
    ctrl = P["control"]
    L = P["plant"]["L_H"]; r = P["plant"]["R_parasitic_ohm"]
    w = np.logspace(1, 5, 2000)
    s = 1j * w
    w0 = 2 * math.pi * 50; wc = ctrl["current_pr_wc_rad_s"]
    PR = ctrl["current_pr_kp"] + 2 * ctrl["current_pr_kr"] * wc * s / (s ** 2 + 2 * wc * s + w0 ** 2)
    plant = 1.0 / (L * s + r)
    delay = np.exp(-1.5 * Ts * s)          # 1.5 拍数字延时(精确)
    G = PR * plant * delay
    mag = np.abs(G); phase = np.angle(G, deg=True)
    gm_idx = int(np.argmin(np.abs(mag - 1.0)))
    pm = 180.0 + phase[gm_idx]

    # 闭环离散极点: PR(Tustin预畸变) + 被控对象ZOH + z^-2 (1.5拍保守近似)
    prc = PRController()
    a = math.exp(-r / L * Ts)
    b = (1 - a) / r if r > 0 else Ts / L
    # x = [y1 y2 e1 e2 i v1] ; e[k] = i_ref - i = -i (小信号i_ref=0)
    # y[k] = -a1a0 y1 - a2a0 y2 + b0a0 e[k] + b2a0 e[k-2]
    # v[k] = kp·e[k] + y[k]; i[k+1] = a·i[k] + b·v[k-2]
    A = np.zeros((6, 6))
    A[0] = [-prc.a1a0, -prc.a2a0, 0.0, prc.b2a0, -prc.b0a0, 0.0]      # y1[k+1] = y[k]
    A[1] = [1.0, 0, 0, 0, 0, 0]                                       # y2[k+1] = y[k-1]
    A[2] = [0, 0, 0, 0, -1.0, 0]                                      # e1[k+1] = e[k] = -i[k]
    A[3] = [0, 0, 1.0, 0, 0, 0]                                       # e2[k+1] = e[k-1]
    A[4] = [0, 0, 0, 0, a, b]                                         # i[k+1] = a i + b v[k-2] (=v1)
    A[5] = [-prc.a1a0, -prc.a2a0, 0.0, prc.b2a0, -prc.b0a0 - prc.kp, 0.0]  # v1[k+1] = v[k]
    ev = np.linalg.eigvals(A)
    stable = bool(np.all(np.abs(ev) < 1.0))
    max_pole = float(np.max(np.abs(ev)))

    fig, ax = plt.subplots(1, 2, figsize=(10, 4))
    ax[0].semilogx(w, 20 * np.log10(mag)); ax[0].axhline(0, color="k", lw=0.5)
    ax[0].set_xlabel("ω (rad/s)"); ax[0].set_ylabel("|G| (dB)")
    ax[0].set_title(f"电流环开环 Bode(含1.5拍延时) PM={pm:.1f}°")
    ax[0].grid(True, alpha=0.3)
    ax[1].plot(ev.real, ev.imag, "x")
    th = np.linspace(0, 2 * math.pi, 100)
    ax[1].plot(np.cos(th), np.sin(th), "k--", lw=0.8)
    ax[1].set_title(f"闭环离散极点 (稳定={stable})")
    ax[1].set_aspect("equal"); ax[1].grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(FIG, "S3_stability.png"), dpi=150)
    plt.close()
    return {"phase_margin_deg": round(pm, 2), "pm_ok": bool(pm >= P["metrics"]["phase_margin_min_deg"]),
            "closed_loop_stable": stable, "max_pole_abs": round(max_pole, 5)}


# ---------- S4: 3功率点 L vs LC 稳态对比 ----------
def s4():
    rows = []
    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    for idx, pp in enumerate(P["power_points"]):
        G = pp["irradiance"]
        i_amp = _fixed_i_amp(pp["P_W_approx"])
        for structure, tag in (("L", "L"), ("LC", "LC")):
            sim = InverterSim(structure, power_point=G, mode="switched",
                              Rd=P["plant"]["R_d_default_ohm"])
            res = sim.run(t_end=0.8, mppt=False, fixed_i_amp=i_amp)   # FIXED_I: 同工况对比
            save_csv(f"S4_{pp['id']}_{tag}.csv", res)
            m = steady_metrics(res)
            rows.append({"power_point": pp["id"], "irradiance": G, "structure": tag,
                         "P_W_approx": pp["P_W_approx"], **m})
            t, ig = res["t"], res["i_g"]
            sel = (t > 0.5) & (t < 0.51)
            axes[idx].plot(t[sel] * 1e3, ig[sel], lw=0.8, label=tag)
        axes[idx].set_ylabel("i_g (A)"); axes[idx].legend(); axes[idx].grid(True, alpha=0.3)
        axes[idx].set_title(f"{pp['id']} ({G*100:.0f}%辐照)")
    axes[2].set_xlabel("t (ms)")
    plt.tight_layout()
    plt.savefig(os.path.join(FIG, "S4_L_vs_LC_steady.png"), dpi=150)
    plt.close()
    # FFT 对比(65%功率点, 高频段放大)
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    for tag, color in (("L", "tab:blue"), ("LC", "tab:orange")):
        d = np.genfromtxt(os.path.join(DATA, f"S4_P65_{tag}.csv"), delimiter=",", names=True)
        fs_file = float(d["fs_Hz"][-1])
        n200 = int(0.2 * fs_file)
        ig = d["i_g_A"][-n200:]
        N = len(ig); win = np.hanning(N)
        spec = np.abs(np.fft.rfft(ig * win)) * 2 / win.sum()
        f = np.fft.rfftfreq(N, 1 / fs_file)
        sel = f < 3000
        ax[0].plot(f[sel], spec[sel], label=tag, color=color, lw=0.9)
        sel2 = (f > 30000) & (f < 50000)
        ax[1].plot(f[sel2], spec[sel2], label=tag, color=color, lw=1.2)
    ax[0].set_xlabel("f (Hz)"); ax[0].set_ylabel("幅值 (A)"); ax[0].set_title("i_g FFT 低频段 (P65)")
    ax[1].set_xlabel("f (Hz)"); ax[1].set_title("i_g FFT 40 kHz 纹波段 (P65)")
    for a in ax:
        a.legend(); a.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(FIG, "S4_FFT_compare.png"), dpi=150)
    plt.close()
    return rows


# ---------- S5: 动态 ----------
def _envelope(t, ig, t_step, fs):
    """20ms RMS 包络 → 超调% 与调节时间(最后进入±5%带的时间)"""
    win = max(int(0.02 * fs), 1)
    sq = np.convolve(ig ** 2, np.ones(win) / win, mode="same")
    rms = np.sqrt(sq)
    after = t >= t_step
    t_a, rms_a = t[after], rms[after]
    final = float(np.mean(rms_a[-max(int(0.1 * fs), 1):]))
    peak = float(np.max(rms_a))
    overshoot = 100.0 * (peak / final - 1.0) if final > 0 else float("nan")
    outside = np.abs(rms_a - final) > 0.05 * final
    t_settle = float(t_a[np.max(np.where(outside)[0])] - t_step) if outside.any() else 0.0
    return overshoot, float(t_settle)


def s5():
    rows = []
    fig, ax = plt.subplots(2, 2, figsize=(12, 7))
    for j, (structure, tag) in enumerate((("L", "L"), ("LC", "LC"))):
        sim = InverterSim(structure, power_point=0.35, mode="average")
        res = sim.run(t_end=1.5, g_step=(0.5, 0.9))      # 辐照 35%→90%
        save_csv(f"S5_irr_step_{tag}.csv", res)
        t, ig = res["t"], res["i_g"]
        os_, ts_ = _envelope(t, ig, 0.5, res["fs"])
        rows.append({"structure": tag, "step": "irr35to90", "overshoot_pct": os_, "t_settle_s": ts_})
        ax[0, j].plot(t, ig, lw=0.6)
        ax[0, j].axvline(0.5, color="r", ls="--")
        ax[0, j].set_title(f"{tag}: 辐照 35%→90% (超调{os_:.1f}%)")
        ax[0, j].set_ylabel("i_g (A)"); ax[0, j].grid(True, alpha=0.3)

        sim2 = InverterSim(structure, power_point=0.65, mode="average")
        res2 = sim2.run(t_end=1.5, ug_step=(0.5, 1.1))   # 电网 +10%
        save_csv(f"S5_ug_step_{tag}.csv", res2)
        os2, ts2 = _envelope(res2["t"], res2["i_g"], 0.5, res2["fs"])
        rows.append({"structure": tag, "step": "ug+10%", "overshoot_pct": os2, "t_settle_s": ts2})
        ax[1, j].plot(res2["t"], res2["i_g"], lw=0.6, color="tab:green")
        ax[1, j].axvline(0.5, color="r", ls="--")
        ax[1, j].set_title(f"{tag}: 电网+10% (超调{os2:.1f}%)")
        ax[1, j].set_xlabel("t (s)"); ax[1, j].set_ylabel("i_g (A)"); ax[1, j].grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(FIG, "S5_dynamic.png"), dpi=150)
    plt.close()
    return rows


# ---------- S6: MPPT 效率 ----------
def s6():
    rows = []
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    for G in (0.35, 0.65, 0.90):
        sim = InverterSim("L", power_point=G, mode="average")
        res = sim.run(t_end=4.0, mppt=True)
        t, vdc = res["t"], res["v_dc"]
        P_pv = np.array([v * sim.pv.current(v, G) for v in vdc])
        sel = t > 1.5
        pmpp = sim.pv.mpp(G)[2]
        eta = 100.0 * float(np.mean(P_pv[sel])) / pmpp
        ripple_p = float(np.ptp(P_pv[sel]))
        rows.append({"G": G, "P_mpp_W": round(pmpp, 1),
                     "P_pv_avg_W": round(float(np.mean(P_pv[sel])), 2),
                     "eta_mppt_pct": round(eta, 2), "P_pv_pp_W": round(ripple_p, 2)})
        ax[0].plot(t, P_pv, label=f"G={G}")
    ax[0].set_xlabel("t (s)"); ax[0].set_ylabel("P_pv (W)")
    ax[0].set_title("MPPT 跟踪 (P&O, 0.5V/100ms)"); ax[0].legend(); ax[0].grid(True, alpha=0.3)
    # 步长敏感性(65%功率点)
    for dV in (0.25, 0.5, 1.0):
        import control_algos as ca
        old = ca.P["control"]["mppt_dV_V"]
        ca.P["control"]["mppt_dV_V"] = dV
        sim = InverterSim("L", power_point=0.65, mode="average")
        res = sim.run(t_end=4.0, mppt=True)
        ca.P["control"]["mppt_dV_V"] = old
        t, vdc = res["t"], res["v_dc"]
        P_pv = np.array([v * sim.pv.current(v, 0.65) for v in vdc])
        ax[1].plot(t, P_pv, label=f"ΔV={dV} V")
    ax[1].set_xlabel("t (s)"); ax[1].set_ylabel("P_pv (W)")
    ax[1].set_title("P&O 步长敏感性 (G=65%)"); ax[1].legend(); ax[1].grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(FIG, "S6_mppt.png"), dpi=150)
    plt.close()
    return rows


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    out = {}
    print("S1: L 扫描仿真 ...")
    out["S1"] = s1()
    print("S2: LC 谐振频率表 + Bode ...")
    out["S2"] = s2()
    print("S3: 稳定性分析 ...")
    out["S3"] = s3()
    print("S4: 3 功率点 L vs LC 对比 ...")
    out["S4"] = s4()
    print("S5: 动态仿真 ...")
    out["S5"] = s5()
    print("S6: MPPT 效率仿真 ...")
    out["S6"] = s6()

    with open(os.path.join(TAB, "sim_summary.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["task", "key", "value"])
        for r in out["S1"]:
            w.writerow(["S1", f"L={r['L_mH']}mH", json.dumps(r, ensure_ascii=False)])
        for r in out["S2"]:
            w.writerow(["S2", f"C={r['C_uF']}uF,Lg={r['Lg_mH']}mH", json.dumps(r, ensure_ascii=False)])
        for k, v in out["S3"].items():
            w.writerow(["S3", k, v])
        for r in out["S4"]:
            w.writerow(["S4", f"{r['power_point']}/{r['structure']}", json.dumps(r, ensure_ascii=False)])
        for r in out["S5"]:
            w.writerow(["S5", f"{r['structure']}/{r['step']}", json.dumps(r, ensure_ascii=False)])
        for r in out["S6"]:
            w.writerow(["S6", f"G={r['G']}", json.dumps(r, ensure_ascii=False)])
    with open(os.path.join(TAB, "sim_summary.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)

    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    print("\n输出完成: data/sim_results/, results/tables/sim_summary.*, results/figures/S*.png")
