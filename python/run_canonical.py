# -*- coding: utf-8 -*-
"""A5 工程口径核心对比（唯一工程口径 = params/params.json /《实现方案》体系）

与 A0-A4 的分工（见 docs/12_参数口径与单一真源.md）：
  A0-A4 = 交叉验证口径（params_merged.py 默认 profile="reference"）：对方
          Desktop/仿真/PV_LC_project 的设计值（Vdc 80 V / L 2 mH / C 12 µF /
          Rd 1 Ω / Lg 1 mH / 死区 1 µs），用于与对方基线逐位对齐；
  A5    = 工程口径（profile="canonical"）：本项目硬件要搭的那套
          （Vdc 75 V / L 0.5 mH / C 20 µF / R_d 0/1/2.2 Ω / Lg 0.5 mH / 死区 400 ns）。
控制律结构仍沿用引擎实现（准 PR + T/4 延时 PLL + 平均功率级死区注入），
增益按 params.json 的 DSP 侧标称值换算（换算规则见 params_canonical.PROVENANCE）。

用法：python -u python/run_canonical.py
输出：results/tables/A5_analytic.csv, A5_core.csv, A5_rd_sweep.csv
      results/figures/A5_thd_comp.png
"""
import math
import os
import sys
import time

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, os.pardir))
sys.path.insert(0, _HERE)
try:                                   # Windows 控制台默认 GBK，避免 µ/· 打印报错
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import params_merged as PM

PROFILE = os.environ.get("LC_PROFILE", "canonical")
PM.use(PROFILE)

from params_merged import P, D          # noqa: E402  切换后取得的同一对象
import analytic                          # noqa: E402
import engine                            # noqa: E402
import metrics                           # noqa: E402

TAB = os.path.join(_ROOT, "results", "tables")
FIG = os.path.join(_ROOT, "results", "figures")
# LC_TAG：给产物加后缀（如 LC_TAG=lg0550 → A5_core_lg0550.csv），
# 用于 L_g 实测回填等"重跑但保留基准"的场景，默认不加后缀。
TAG = os.environ.get("LC_TAG", "").strip()


def _n(name):
    if not TAG:
        return name
    base, ext = os.path.splitext(name)
    return "%s_%s%s" % (base, TAG, ext)
os.makedirs(TAB, exist_ok=True)
os.makedirs(FIG, exist_ok=True)

COMPS = ("none", "sign", "sat")
PW = tuple(P["P_points"])      # 工程口径三功率点：70/130/180 W（35/65/90% 额定）


def save_csv(name, rows):
    path = os.path.join(TAB, _n(name))
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        f.write(",".join(rows[0].keys()) + "\n")
        for r in rows:
            f.write(",".join(str(r[k]) for k in rows[0].keys()) + "\n")
    return path


def _mpl():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    return plt


def case(structure, Pw, comp, Rd=None, t_end=0.8):
    """一个静态算例：固定功率指令 + 固定母线 + 指定 R_d"""
    old = P["Rd"]
    if Rd is not None:
        P["Rd"] = float(Rd)
    t0 = time.time()
    r = engine.run_case(structure, "fixed_i", fixed_P=Pw, t_end=t_end, comp=comp)
    iref = math.sqrt(2)*Pw/P["Ug_rms"]
    m = metrics.window_metrics(r["t"], r["i_g"], r["u_g"], iref, D["Im_rated_rms"])
    m.update({"structure": structure, "P_W": Pw, "Rd": P["Rd"], "comp": comp,
              "wall_s": round(time.time()-t0, 1)})
    P["Rd"] = old
    return m


def _atten_ratio(f, Lg=None, Rd=None):
    """|i_g/v_ab|_L ÷ |i_g/v_ab|_LC（阻抗模型与 analytic.hf_attenuation 相同；
    为不改动 A0 既有数值，此处独立实现）"""
    L, C = P["L"], P["C"]
    Lg = P["Lg"] if Lg is None else Lg
    Rd = P["Rd"] if Rd is None else Rd
    w = 2*math.pi*f
    g_L = 1.0/abs(P["Rf"] + P["Rg"] + 1j*w*(L + Lg))
    Zc = Rd + 1.0/(1j*w*C)
    Zp = (Zc*(P["Rf"] + 1j*w*L))/(Zc + P["Rf"] + 1j*w*L)
    Zt = Zp + P["Rg"] + 1j*w*Lg
    g_LC = abs(1.0/Zt)*abs(Zp/(P["Rf"] + 1j*w*L))
    return abs(g_L/g_LC)


def a5_analytic():
    """工程口径解析层：f0、含 Lg 的 f_res（解析 vs 数值振铃）、40 kHz 衰减比、最小母线电压"""
    print("== A5 解析层（工程口径 L=%.2f mH, C=%.0f µF, Lg=%.2f mH）"
          % (P["L"]*1e3, P["C"]*1e6, P["Lg"]*1e3))
    f0 = 1.0/(2*math.pi*math.sqrt(P["L"]*P["C"]))
    rows = []
    for Rd in (0.0, 1.0, 2.2):
        old = P["Rd"]
        P["Rd"] = Rd
        f_num, f_ana = analytic._ring_freq(P["L"], P["Lg"], P["C"], Rd, P["Rf"], P["Rg"])
        att = _atten_ratio(40000.0, Rd=Rd)
        P["Rd"] = old
        rows.append({"quantity": "f_res(LCL,含Lg)", "Rd_ohm": Rd,
                     "analytic": f_ana, "numeric": f_num,
                     "err_pct": (f_num-f_ana)/f_ana*100.0, "unit": "Hz"})
        rows.append({"quantity": "40kHz 衰减比", "Rd_ohm": Rd,
                     "analytic": "", "numeric": att, "err_pct": "", "unit": "x"})
    rows.append({"quantity": "f0(仅LC,不含Lg)", "Rd_ohm": 0.0,
                 "analytic": f0, "numeric": "", "err_pct": "", "unit": "Hz"})
    att_mean = analytic.hf_attenuation(Lg=P["Lg"])["atten_mean"]
    rows.append({"quantity": "15-25kHz 衰减比 mean", "Rd_ohm": P["Rd"],
                 "analytic": att_mean, "numeric": "", "err_pct": "", "unit": "x"})
    vm = analytic.vdc_min_rated()
    rows.append({"quantity": "额定最小母线电压", "Rd_ohm": "", "analytic": vm["vdc_min_V"],
                 "numeric": vm["fund_drop_pct"], "err_pct": "", "unit": "V/%(基波压降)"})
    save_csv("A5_analytic.csv", rows)
    print("  f0(仅LC)=%.1f Hz  f_res(含 Lg=%.2fmH, Rd=0)=%.1f Hz（解析 %.1f）"
          % (f0, P["Lg"]*1e3, rows[0]["numeric"], rows[0]["analytic"]))
    print("  15-25 kHz 衰减比 mean=%.1fx  40kHz(Rd=0)=%.1fx  额定最小母线电压=%.2f V（压降 %.2f%%）"
          % (att_mean, rows[1]["numeric"], vm["vdc_min_V"], vm["fund_drop_pct"]))
    return rows


def a5_core():
    print("== A5 核心对比（工程口径，Rd=%.1f Ω）" % P["Rd"])
    rows = []
    for struct in ("L", "LC"):
        for Pw in PW:
            for comp in COMPS:
                m = case(struct, Pw, comp)
                rows.append(m)
                print("  %-2s %3.0fW %-4s THD=%.3f%% TDD=%.3f%% HF=%.3f%% Idc=%+.2e A (%.0fs)"
                      % (struct, Pw, comp, m["THD_pct"], m["TDD_pct"], m["HF_pct"],
                         m["Idc_A"], m["wall_s"]))
    save_csv("A5_core.csv", rows)
    return rows


def a5_rd_sweep():
    print("== A5 LC 阻尼档扫描（工程口径 R_d = 0/1/2.2 Ω, comp=sat）")
    rows = []
    for Pw in (130.0, PW[-1]):
        for Rd in (0.0, 1.0, 2.2):
            if Rd == 0.0 and Pw == PW[-1]:
                continue          # 已在 core 中
            m = case("LC", Pw, "sat", Rd=Rd)
            rows.append(m)
            print("  LC %3.0fW Rd=%.1f THD=%.3f%% HF=%.3f%% Idc=%+.2e A (%.0fs)"
                  % (Pw, Rd, m["THD_pct"], m["HF_pct"], m["Idc_A"], m["wall_s"]))
    save_csv("A5_rd_sweep.csv", rows)
    return rows


def a5_fig(core_rows):
    plt = _mpl()
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    for ax, struct in zip(axes, ("L", "LC")):
        xs = np.arange(3)
        w = 0.25
        for i, Pw in enumerate(PW):
            ys = [next(r["THD_pct"] for r in core_rows
                       if r["structure"] == struct and r["P_W"] == Pw
                       and r["comp"] == c) for c in COMPS]
            ax.bar(xs + (i-1)*w, ys, w, label="%.0f W" % Pw)
        ax.set_xticks(xs)
        ax.set_xticklabels(["无补偿", "sign", "sat"])
        ax.set_title("%s 结构（工程口径）" % struct)
        ax.grid(alpha=.3, axis="y")
    axes[0].set_ylabel("THD(2-50) %")
    axes[0].legend(fontsize=8)
    fig.suptitle("A5 工程口径死区补偿对比（Vdc 75 V / L 0.5 mH / C 20 µF / 死区 1.2 V）")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, _n("A5_thd_comp.png")), dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    t0 = time.time()
    print("口径 profile = %s (%s)" % (P.get("profile"), P.get("profile_name")))
    a5_analytic()
    core = a5_core()
    a5_rd_sweep()
    a5_fig(core)
    print("== A5 完成，总耗时 %.0f s" % (time.time()-t0))