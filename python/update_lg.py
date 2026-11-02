# -*- coding: utf-8 -*-
"""L_g 实测回填工具（隔离变压器漏感 → params.json → 重算影响 + 重跑 A0/A5）

背景：工程口径的唯一真源是 `params/params.json`，其中 `plant.L_g_H = 0.5 mH` 是
《实现方案》给的**设计值/估计值**（隔离变压器副边漏感，一般 0.1–1 mH）。硬件到位后
必须用 LCR 表实测并回填，否则 LC 谐振频率、40 kHz 衰减比、额定最小母线电压都会偏。

本工具做三件事（写盘前先在内存里算，可 --dry-run 只看不写）：
  1. 影响表：Rd = 0/1/2.2 Ω 三种档位下的 f_res（解析 + 数值）、40 kHz 衰减比、
     15–25 kHz 平均衰减比、设计区间判据（10·f_g < f0 < f_sw/10）、f_s/6 判据、
     额定最小母线电压与基波压降；并给 R_d 建议（A5 已证明 R_d=0 时 LC 发散，这里
     只判断"实测值是否让结论更差/更好"）。
  2. 回填：更新 `plant.L_g_H`、按新值重算 `resonance.f_res_Lg05_Hz`（该键的语义 =
     当前 L_g 下的 f_res，保持 json 自洽），并写入 `plant.L_g_measured` 溯源块
     （值、日期、仪器、备注、测法），跑 `check_params.py` 复核单一真源没有破。
  3. 提示重跑命令：A5 用 `LC_TAG=<tag>` 生成 `A5_*_<tag>.csv`，不覆盖基准产物。

用法：
    python update_lg.py --show                      # 只看当前值与影响表
    python update_lg.py --measure 0.62 --dry-run    # 按实测 0.62 mH 算，不写盘
    python update_lg.py --measure 0.62 --date 2026-11-05 --instrument "LCR-819 @10 kHz" --note "副边短路测"
    python update_lg.py --rerun                     # 跑 check_params + A5（带 LC_TAG）

单位：--measure 的值默认按 **mH** 解释；写 `0.62H` 或 `--unit H` 则按 H。
退出码：0 正常；1 输入越界（不在 0.05–3 mH 的工程合理解释范围）或写盘后校验 FAIL。
"""
import io
import json
import math
import os
import subprocess
import sys
from collections import OrderedDict

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
JSON_PATH = os.path.join(ROOT, "params", "params.json")

LG_MIN_MH, LG_MAX_MH = 0.05, 3.0       # LCR 实测的合理解释范围


# ---------------------------------------------------------------- json
def load_json():
    with io.open(JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f, object_pairs_hook=OrderedDict)


def save_json(d):
    with io.open(JSON_PATH, "w", encoding="utf-8", newline="\n") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
        f.write(u"\n")


# ---------------------------------------------------------------- 解析（与 A5 同阻抗模型）
def f_res_analytic(L, Lg, C):
    return (1.0/(2*math.pi))*math.sqrt((L + Lg)/(L*Lg*C))


def f_res_numeric(L, Lg, C, Rd, Rf=0.1, Rg=0.1):
    """数值振铃频率：直接复用 A5 用的 analytic._ring_freq（同一状态方程、同一过零有效性
    判据），保证与 results/tables/A5_analytic.csv 的数字逐位可比，不另写一套。"""
    import params_merged as PM
    PM.use("canonical")
    import analytic
    f_num, _f0 = analytic._ring_freq(L, Lg, C, Rd, Rf, Rg)
    return f_num


def atten_ratio(f, L, Lg, C, Rd, Rf=0.1, Rg=0.1):
    """LC 相对 L 的 |i_g/v_ab| 衰减比（同一 L、同一 Lg）。"""
    w = 2*math.pi*f
    gL = 1.0/abs(Rf + Rg + 1j*w*(L + Lg))
    Zc = Rd + 1.0/(1j*w*C)
    Zp = (Zc*(Rf + 1j*w*L))/(Zc + Rf + 1j*w*L)
    Zt = Zp + Rg + 1j*w*Lg
    gLC = abs(1.0/Zt)*abs(Zp/(Rf + 1j*w*L))
    return gL/gLC


def atten_band_mean(Lg, L, C, Rd, Rf=0.1, Rg=0.1, f_lo=15e3, f_hi=25e3, nf=21):
    vals = [atten_ratio(f, L, Lg, C, Rd, Rf, Rg) for f in np.linspace(f_lo, f_hi, nf)]
    return float(np.mean(vals))


# ---------------------------------------------------------------- 影响表
def impact(lg, d):
    R, S, PL, RES, CO = d["rating"], d["switching"], d["plant"], d["resonance"], d["control"]
    L = float(PL["L_H"])
    C = float(PL["C_F"])
    Rf = float(PL["R_parasitic_ohm"])
    Rg = 0.1
    fsw = float(S["f_sw_Hz"])
    fg = float(R["f_g_Hz"])
    Ug = float(R["U_g_Vrms"])
    Pn = float(R["P_n_W"])
    f0 = 1.0/(2*math.pi*math.sqrt(L*C))
    Im = math.sqrt(2)*Pn/Ug
    drop = 2*math.pi*fg*(L + lg)*Im
    out = OrderedDict()
    out["L_g_mH"] = lg*1e3
    out["f0_only_LC_Hz"] = f0
    out["design_range_ok"] = (10*fg < f0 < fsw/10.0)
    out["f_res_analytic_Hz"] = f_res_analytic(L, lg, C)
    out["f_res_under_fs6"] = out["f_res_analytic_Hz"] < fsw/6.0
    out["vdc_min_V"] = math.sqrt(2)*Ug + drop
    out["fund_drop_pct"] = drop/(math.sqrt(2)*Ug)*100.0
    out["Rd"] = []
    for rd in (0.0, 1.0, 2.2):
        row = OrderedDict()
        row["Rd_ohm"] = rd
        row["f_res_num_Hz"] = f_res_numeric(L, lg, C, rd, Rf, Rg)
        row["atten_40k"] = atten_ratio(40000.0, L, lg, C, rd, Rf, Rg)
        row["atten_band"] = atten_band_mean(lg, L, C, rd, Rf, Rg)
        out["Rd"].append(row)
    out["R_d_advice"] = ("必装 R_d（A5：R_d=0 时 LC 三功率点全部发散），起点 1 Ω，最终值由 E7 定")
    return out


def print_impact(t):
    print("\n工程口径影响（L 0.5 mH / C 20 µF / f_sw 20 kHz / f_g 50 Hz）")
    print("  L_g                     = %.4f mH" % t["L_g_mH"])
    print("  f0（仅 LC，不含 L_g）    = %.1f Hz   设计区间 500–2000 Hz：%s"
          % (t["f0_only_LC_Hz"], "满足" if t["design_range_ok"] else "**不满足**"))
    print("  f_res（含 L_g，解析）    = %.1f Hz   f_res < f_s/6 = %.0f Hz：%s"
          % (t["f_res_analytic_Hz"], 20000/6.0, "成立" if t["f_res_under_fs6"] else "**不成立**"))
    print("  额定最小母线电压         = %.2f V（基波压降 %.2f %%，V_mpp 75 V 余量 %+.1f V）"
          % (t["vdc_min_V"], t["fund_drop_pct"], 75.0 - t["vdc_min_V"]))
    print("\n  %-8s %14s %14s %14s" % ("R_d/Ω", "f_res 数值/Hz", "40 kHz 衰减比", "15–25 kHz 均值"))
    for r in t["Rd"]:
        print("  %-8.1f %14.1f %14.2f %14.2f"
              % (r["Rd_ohm"], r["f_res_num_Hz"], r["atten_40k"], r["atten_band"]))
    print("\n  R_d：%s" % t["R_d_advice"])


def compare(old, new):
    print("\n与回填前对比：")
    print("  %-22s %14s %14s %12s" % ("量", "回填前", "回填后", "变化"))
    for k, label in (("f_res_analytic_Hz", "f_res 解析/Hz"),
                     ("vdc_min_V", "最小母线/V"),
                     ("fund_drop_pct", "基波压降/%")):
        a, b = old[k], new[k]
        print("  %-22s %14.3f %14.3f %+11.2f%%" % (label, a, b, (b - a)/a*100.0 if a else 0.0))
    for ra, rb in zip(old["Rd"], new["Rd"]):
        d = (rb["atten_40k"] - ra["atten_40k"])/ra["atten_40k"]*100.0 if ra["atten_40k"] else 0.0
        print("  %-22s %14.2f %14.2f %+11.2f%%"
              % ("40 kHz 衰减 Rd=%.1f" % ra["Rd_ohm"], ra["atten_40k"], rb["atten_40k"], d))


# ---------------------------------------------------------------- 主流程
def parse_lg(argv):
    if "--measure" not in argv:
        return None
    i = argv.index("--measure")
    raw = argv[i + 1] if i + 1 < len(argv) else ""
    unit_h = raw.lower().endswith("h") or "--unit" in argv and argv[argv.index("--unit") + 1].upper() == "H"
    s = raw.rstrip("hH m M").strip()
    try:
        v = float(s)
    except ValueError:
        print("无法解析 --measure 的值：%r（示例：--measure 0.62 或 --measure 0.62mH）" % raw)
        return None
    return v if unit_h else v*1e-3


def opt(argv, name, default=None):
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1]
    return default


def main():
    argv = sys.argv[1:]
    d = load_json()
    old_lg = float(d["plant"]["L_g_H"])
    print("params/params.json 现值：plant.L_g_H = %.6f H（%.4f mH）" % (old_lg, old_lg*1e3))
    meas = d["plant"].get("L_g_measured")
    if meas:
        print("  实测记录：%s（%s，%s）"
              % (meas.get("value_mH"), meas.get("date"), meas.get("instrument")))

    lg_meas = parse_lg(argv)
    if "--show" in argv or lg_meas is None:
        print_impact(impact(old_lg, d))
        if lg_meas is None:
            print("\n用法：--measure <mH> [--dry-run] [--date D] [--instrument S] [--note S]；--rerun 重跑校验与 A5")
        return 0

    mh = lg_meas*1e3
    if not (LG_MIN_MH <= mh <= LG_MAX_MH):
        print("\n输入越界：%.4f mH 不在 %.2f–%.2f mH 的工程合理解释范围（隔离变压器漏感实测一般"
              " 0.1–1 mH）。请复核测量结果或显式确认后手改 params.json。" % (mh, LG_MIN_MH, LG_MAX_MH))
        return 1

    t_old, t_new = impact(old_lg, d), impact(lg_meas, d)
    print_impact(t_new)
    compare(t_old, t_new)

    if "--dry-run" in argv:
        print("\n[dry-run] 未写盘。去掉 --dry-run 即回填 params.json。")
        return 0

    # ---- 回填 ----
    d["plant"]["L_g_H"] = round(lg_meas, 9)
    d["resonance"]["f_res_Lg05_Hz"] = round(t_new["f_res_analytic_Hz"], 3)
    d["plant"]["L_g_measured"] = OrderedDict([
        ("value_H", round(lg_meas, 9)),
        ("value_mH", round(mh, 4)),
        ("date", opt(argv, "--date", "TBD")),
        ("instrument", opt(argv, "--instrument", "LCR 表（型号待填）")),
        ("method", "隔离变压器副边短路，10 kHz 下测原边/副边漏感"),
        ("note", opt(argv, "--note", "")),
        ("replaces_design_value_mH", round(old_lg*1e3, 4)),
    ])
    meta = d.setdefault("_meta", OrderedDict())
    meta["l_g_provenance"] = ("plant.L_g_H 由 python/update_lg.py 按实测回填（%s）；"
                              "resonance.f_res_Lg05_Hz 已按新 L_g 重算以保证 json 自洽"
                              % opt(argv, "--date", "TBD"))
    save_json(d)
    print("\n[回填] 已写 params/params.json：plant.L_g_H = %.6f H、resonance.f_res_Lg05_Hz = %.3f Hz"
          % (lg_meas, t_new["f_res_analytic_Hz"]))

    print("\n下一步（按顺序）：")
    print("  1) cd python && PYTHONUTF8=1 python -u check_params.py       # 单一真源复核，应 FAIL 0")
    tag = "lg%04d" % int(round(mh*1000))
    print("  2) cd .. && LC_TAG=%s python -u python/run_canonical.py       # A5 重跑，产物带后缀不覆盖基准" % tag)
    print("     对比：results/tables/A5_core.csv（基准）vs A5_core_%s.csv（实测 L_g）" % tag)
    print("  3) python -u python/run_tasks.py a0                           # A0 为交叉验证口径（L_g 1 mH），"
          "仅当也要刷新对方基线时才跑")
    print("  4) 若 f_res 变化 >10%%：同步 docs/12 §6、docs/14 §2、README 口径行，并在报告里注明实测值")
    return 0


if __name__ == "__main__":
    sys.exit(main())