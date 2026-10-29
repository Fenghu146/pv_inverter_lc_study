# -*- coding: utf-8 -*-
"""合并版重跑任务：A0 解析 / A1 L 扫描 / A2 核心对比 / A3 峰值阶跃 / A4 MPPT

输出：results/tables/*.csv + results/figures/*.png
运行：python merged/run_tasks.py   （在仓库根目录执行）
"""
import csv
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from params_merged import P, D
from engine import run_case, pv_mpp, pv_current
from metrics import window_metrics
import analytic

TAB = os.path.join(HERE, "..", "results", "tables")
FIG = os.path.join(HERE, "..", "results", "figures")
os.makedirs(TAB, exist_ok=True)
os.makedirs(FIG, exist_ok=True)


def save_csv(name, rows, fields=None):
    path = os.path.join(TAB, name)
    if not rows:
        print(f"  (空) {name}")
        return path
    if fields is None:
        seen = []
        for r in rows:
            for k in r.keys():
                if k not in seen:
                    seen.append(k)
        fields = seen
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"  -> tables/{name}  ({len(rows)} 行)")
    return path


def _mpl():
    """matplotlib + 中文字体（Windows 微软雅黑）"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    return plt


# ---------------------------------------------------------------- A0 解析层
def a0():
    print("== A0 解析层：谐振振铃 15 工况 + 高频衰减 + 最小母线电压")
    res = analytic.resonance_table()
    save_csv("A0_resonance.csv", res)
    att = analytic.hf_attenuation(Lg=1.0e-3)
    att05 = analytic.hf_attenuation(Lg=0.5e-3)
    att20 = analytic.hf_attenuation(Lg=2.0e-3)
    vmin = analytic.vdc_min_rated()
    rows = [{**att, "case": "Lg=1mH(默认)"},
            {**att05, "case": "Lg=0.5mH"},
            {**att20, "case": "Lg=2mH"}]
    save_csv("A0_hf_atten.csv", rows)
    print(f"  15-25 kHz 衰减比: Lg=1mH {att['atten_mean']:.1f}x | "
          f"Lg=0.5mH {att05['atten_mean']:.1f}x | Lg=2mH {att20['atten_mean']:.1f}x")
    print(f"  额定最小母线电压(基波口径): {vmin['vdc_min_V']:.2f} V "
          f"(50Hz 压降 {vmin['fund_drop_pct']:.1f}%)")
    err = max(abs(r["err_pct"]) for r in res)
    print(f"  谐振频率数值 vs 解析最大误差: {err:.2f}%")
    # 图
    plt = _mpl()
    fig, ax = plt.subplots(figsize=(6, 4))
    for Lg in (0.5, 1.0, 2.0):
        rs = [r for r in res if r["Lg_mH"] == Lg]
        ax.plot([r["L_mH"] for r in rs], [r["f_res_analytic_Hz"] for r in rs],
                "o--", label=f"解析 Lg={Lg}mH")
        ax.plot([r["L_mH"] for r in rs], [r["f_res_sim_Hz"] for r in rs],
                "s", label=f"数值 Lg={Lg}mH")
    ax.set_xlabel("L (mH)"); ax.set_ylabel("LC 谐振频率 (Hz)")
    ax.grid(alpha=.3); ax.legend(fontsize=8)
    ax.set_title("A0 线性网络谐振：数值 vs 解析")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "A0_resonance.png"), dpi=150)
    plt.close(fig)
    return res, att, vmin


# ---------------------------------------------------------------- A1 L 扫描
def a1():
    print("== A1 L 扫描（L 结构, 200 W, 无死区补偿, 峰值 0.5s 起）")
    rows = []
    for L_mH in (0.5, 1.0, 2.0, 3.0, 4.0):
        t0 = time.time()
        r = run_case("L", "fixed_i", fixed_P=200.0, t_end=0.5,
                     comp="none", L=L_mH*1e-3)
        mtr = window_metrics(r["t"], r["i_g"], r["u_g"],
                             math.sqrt(2)*200/P["Ug_rms"], D["Im_rated_rms"])
        drop = D["wg"]*(L_mH*1e-3 + P["Lg"])*D["Im_rated"]/D["Ug_pk"]*100
        rows.append({"L_mH": L_mH, **mtr, "fund_drop50_pct": drop,
                     "wall_s": round(time.time()-t0, 1)})
        print(f"  L={L_mH} mH: THD={mtr['THD_pct']:.2f}%  Idc={mtr['Idc_A']*1e3:+.2f} mA  "
              f"压降={drop:.1f}%  ({rows[-1]['wall_s']}s)")
    save_csv("A1_lscan.csv", rows)
    return rows


# ---------------------------------------------------------------- A2 核心对比
def a2():
    print("== A2 核心对比: {L,LC} x {70,130,200W} x {无补偿, sign, sat} + 20mA 零偏")
    rows = []
    for struct in ("L", "LC"):
        for Pw in (70.0, 130.0, 200.0):
            for comp in ("none", "sign", "sat"):
                t0 = time.time()
                r = run_case(struct, "fixed_i", fixed_P=Pw, t_end=0.8, comp=comp)
                mtr = window_metrics(r["t"], r["i_g"], r["u_g"],
                                     math.sqrt(2)*Pw/P["Ug_rms"], D["Im_rated_rms"])
                rows.append({"structure": struct, "P_W": Pw, "comp": comp,
                             "bias": 0, **mtr, "wall_s": round(time.time()-t0, 1)})
                print(f"  {struct} {Pw:.0f}W {comp:>5}: THD={mtr['THD_pct']:5.2f}%  "
                      f"TDD={mtr['TDD_pct']:4.2f}%  Idc={mtr['Idc_A']*1e3:+6.2f} mA  "
                      f"amp_err={mtr['amp_err_pct']:+.2f}%  ({rows[-1]['wall_s']}s)")
    for struct in ("L", "LC"):  # 传感器零偏敏感性（对方 run_bias 口径）
        r = run_case(struct, "fixed_i", fixed_P=200.0, t_end=0.8,
                     comp="sat", bias_i=0.02)
        mtr = window_metrics(r["t"], r["i_g"], r["u_g"],
                             math.sqrt(2)*200/P["Ug_rms"], D["Im_rated_rms"])
        rows.append({"structure": struct, "P_W": 200.0, "comp": "sat",
                     "bias": 20, **mtr, "wall_s": 0})
        print(f"  {struct} 200W sat+bias20mA: Idc={mtr['Idc_A']*1e3:+.2f} mA")
    save_csv("A2_core.csv", rows)
    return rows


# ---------------------------------------------------------------- A3 峰值阶跃
def a3():
    print("== A3 功率阶跃 70->200->70 W（电流峰值处 0.505/1.005 s，对方 A7 口径）")
    Im70 = math.sqrt(2)*70/P["Ug_rms"]
    Im200 = math.sqrt(2)*200/P["Ug_rms"]
    dIm = Im200 - Im70
    rows = []
    fig_data = {}
    for struct in ("L", "LC"):
        r = run_case(struct, "fixed_i", fixed_P=70.0, t_end=1.4,
                     comp="sat", P_sched=[(0.505, 200.0), (1.005, 70.0)])
        t, ig, iref = r["t"], r["i_g"], r["i_ref"]
        row = {"structure": struct}
        fig_data[struct] = (t, ig - iref)
        for tag, t0 in (("up", 0.505), ("down", 1.005)):
            m1 = (t >= t0) & (t < t0 + 2e-3)
            err = np.abs(ig - iref)
            row[f"{tag}_peak_err_pct_dIm"] = float(np.max(err[m1]))/dIm*100
            # 5 ms 后残差（衰减比）
            m2 = (t >= t0 + 5e-3) & (t < t0 + 15e-3)
            row[f"{tag}_err_5ms_pct_dIm"] = float(np.sqrt(np.mean(err[m2]**2)))/dIm*100
            # 1.4-2.2 kHz 带通振铃（仅 LC 有意义；L 记 NaN，对方 F5 口径）
            if struct == "LC":
                from scipy.signal import butter, filtfilt
                seg = (ig - iref)[(t >= t0) & (t < t0 + 30e-3)]
                dt = t[1] - t[0]
                b, a = butter(2, [1400.0, 2200.0], btype="band", fs=1.0/dt)
                sig_bp = filtfilt(b, a, seg)
                zc = int(np.sum((sig_bp[:-1] < 0) & (sig_bp[1:] >= 0)))
                # 每个振铃周期一个上升过零：f = 上升过零数 / 时长
                row[f"{tag}_ring_Hz"] = float(zc/30e-3) if zc >= 4 else float("nan")
            else:
                row[f"{tag}_ring_Hz"] = float("nan")
        rows.append(row)
        print(f"  {struct}: 上阶跃峰值误差 {row['up_peak_err_pct_dIm']:.0f}%ΔIm, "
              f"5ms残差 {row['up_err_5ms_pct_dIm']:.1f}%ΔIm, "
              f"振铃 {row['up_ring_Hz'] if not math.isnan(row['up_ring_Hz']) else 'NaN'} Hz")
    save_csv("A3_step.csv", rows)
    # 图
    plt = _mpl()
    fig, axes = plt.subplots(2, 1, figsize=(9, 6), sharex=True)
    for ax, (struct, (t, e)) in zip(axes, fig_data.items()):
        ax.plot(t, e, lw=.6)
        ax.axvline(0.505, color="r", ls="--", lw=.8)
        ax.axvline(1.005, color="r", ls="--", lw=.8)
        ax.set_ylabel(f"{struct} i_g-i_ref (A)")
        ax.grid(alpha=.3)
    axes[1].set_xlabel("t (s)")
    fig.suptitle("A3 电流峰值处功率阶跃（70→200→70 W, 饱和补偿）")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "A3_step.png"), dpi=150)
    plt.close(fig)
    return rows


# ---------------------------------------------------------------- A4 MPPT
def a4():
    print("== A4 MPPT: 三档光照稳态 + 远起点 62/90 V")
    rows = []
    traj = {}
    for G in (400.0, 700.0, 1000.0):
        t0 = time.time()
        r = run_case("L", "mppt", t_end=6.0, G_sched=[(0.0, G)])
        Pmpp, Vmpp, _ = pv_mpp(G)
        m = r["t"] >= 4.0
        # 窗口平均 PV 功率：用 vdc 与电流指令重构不精确，直接以稳态 vdc 计算工作点
        vdc_ss = float(np.mean(r["v_dc"][m]))
        P_pv = vdc_ss*pv_current(vdc_ss, G)
        eta = P_pv/Pmpp*100
        rows.append({"case": f"G={G:.0f}", "V0": P["mppt_V0"],
                     "vdc_ss_V": vdc_ss, "Vmpp_V": Vmpp,
                     "P_pv_W": P_pv, "P_mpp_W": Pmpp, "eta_pct": eta,
                     "wall_s": round(time.time()-t0, 1)})
        traj[f"G{G:.0f}"] = (r["t"], r["v_dc"])
        print(f"  G={G:.0f}: vdc={vdc_ss:.2f} V (Vmpp {Vmpp:.2f})  "
              f"P={P_pv:.2f}/{Pmpp:.2f} W  eta={eta:.2f}%  ({rows[-1]['wall_s']}s)")
    for V0 in (62.0, 90.0):
        t0 = time.time()
        r = run_case("L", "mppt", t_end=14.0, V0=V0, G_sched=[(0.0, 1000.0)])
        Pmpp, Vmpp, _ = pv_mpp(1000.0)
        t, vdc = r["t"], r["v_dc"]
        Ppv = vdc*np.array([pv_current(v, 1000.0) for v in vdc])
        frac = Ppv/Pmpp
        # 收敛口径：100 ms 滑动平均功率比首次持续 0.5 s >= 99.68%
        #（母线可能从 MPP 电压起步且 P&O 抖动会瞬时跌破，单点判据不稳健）
        Wm = int(round(0.1/(t[1]-t[0])))
        fr = np.convolve(frac, np.ones(Wm)/Wm, "valid")
        th = 0.9968
        W2 = int(round(0.5/(t[1]-t[0])))
        ok = fr >= th
        run = np.convolve(ok.astype(int), np.ones(W2, dtype=int), "valid")
        hit = np.where(run >= W2)[0]
        t_conv = float(t[hit[0]]) if hit.size else float("nan")
        rows.append({"case": f"远起点 V0={V0:.0f}", "V0": V0,
                     "vdc_ss_V": float(np.mean(vdc[t >= 12.0])), "Vmpp_V": Vmpp,
                     "P_pv_W": float(np.mean(Ppv[t >= 12.0])), "P_mpp_W": Pmpp,
                     "eta_pct": float(np.mean(frac[t >= 12.0]))*100,
                     "t_conv_s": t_conv,
                     "wall_s": round(time.time()-t0, 1)})
        traj[f"V0={V0:.0f}"] = (t, vdc)
        print(f"  远起点 V0={V0:.0f}: 收敛到 99.68%MPP 用时 {t_conv:.2f} s "
              f"({rows[-1]['wall_s']}s)")
    save_csv("A4_mppt.csv", rows)
    # 图
    plt = _mpl()
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for k, (tt, vv) in traj.items():
        ax.plot(tt, vv, lw=.8, label=k)
    ax.set_xlabel("t (s)"); ax.set_ylabel("v_dc (V)")
    ax.grid(alpha=.3); ax.legend(fontsize=8)
    ax.set_title("A4 MPPT 母线电压轨迹（P&O 1V/0.5s + 电压环）")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "A4_mppt.png"), dpi=150)
    plt.close(fig)
    return rows


# ---------------------------------------------------------------- A2 图
def a2_fig(rows):
    plt = _mpl()
    comps = ("none", "sign", "sat")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    for ax, struct in zip(axes, ("L", "LC")):
        xs = np.arange(3)
        w = 0.25
        for i, Pw in enumerate((70.0, 130.0, 200.0)):
            ys = [next(r["THD_pct"] for r in rows
                       if r["structure"] == struct and r["P_W"] == Pw
                       and r["comp"] == c) for c in comps]
            ax.bar(xs + (i-1)*w, ys, w, label=f"{Pw:.0f} W")
        ax.set_xticks(xs); ax.set_xticklabels(["无补偿", "sign", "sat"])
        ax.set_title(f"{struct} 结构"); ax.grid(alpha=.3, axis="y")
    axes[0].set_ylabel("THD(2-50) %")
    axes[0].legend(fontsize=8)
    fig.suptitle("A2 死区补偿对比（平均模型 + 功率级 3.2 V 死区误差）")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "A2_thd_comp.png"), dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------- 主流程
if __name__ == "__main__":
    t_all = time.time()
    a0()
    a1_rows = a1()
    a2_rows = a2()
    a2_fig(a2_rows)
    a3()
    a4()
    print(f"== 全部完成，总耗时 {time.time()-t_all:.0f} s")
