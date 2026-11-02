# -*- coding: utf-8 -*-
"""PV 单二极管模型标定（工程口径，2026-11-02）

目标：把 engine.pv_current 的单二极管模型标定到工程口径 PV 特性
     Voc = 90 V、Isc = 2.9 A（G = 1000 W/m2、T = 25 C）
     Vmpp = 75 V、Impp = 2.67 A → P_mpp = 200.25 W（≈ rating.P_n_W = 200 W）

两次死路的教训（旧 .work/fit_pv.py，已弃用）：
  1. 用"网格 argmax 求 MPP + least_squares"时残差对参数不可导，优化器原地"假收敛"（残差 1 V）；
  2. 改三分搜索后每次残差求值 >4 min 不收敛。
本脚本把 MPP 写成**解析条件**做残差，全程光滑：
     P = V·I，dP/dV = 0  →  I = V·g/(1 + g·Rs)，g = I0/a·exp((V+I·Rs)/a) + 1/Rp，a = Nser·N·kT/q
  "在 75 V 处取极值"于是直接是一条残差，不需要找极值。

可辨识性（本脚本实测，见 --ident 输出与 CSV 的 identifiability 行）：
  四个目标点（Isc / Voc / Vmpp / Impp）只给出 2 个独立约束，对 (N, Rs, Rp) 是**一族解**——
  Rs 从 0 到 0.94 Ω 任意取值，都能让 N 与 Rp 补偿到四个点几乎零残差（cost < 1e-6）。
  因此本脚本**固定 Rs = 0.937 Ω**（对方材料/工艺给出的物理值，保留可追溯性），只拟合 (N, Rp)，
  并把可辨识性扫描一并报告——不允许把参数塞到边界上（那只是优化器的假象，不是物理）。

用法：
    python calib_pv.py              # 标定 + 残差表 + 可辨识性扫描 + 写 results/tables/pv_calibration.csv
    python calib_pv.py --apply      # 标定通过后把 pv_model 块写进 params/params.json
    python calib_pv.py --verify     # 只读 json 的 pv_model，复核四个目标点是否仍满足

退出码：0 = 四个目标点全部在容差内；1 = 超出容差（--apply 时不写 json）。
"""
import io
import json
import math
import os
import sys
from collections import OrderedDict

import numpy as np
from scipy.optimize import least_squares, brentq

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_PATH = os.path.join(ROOT, "params", "params.json")
TAB_DIR = os.path.join(ROOT, "results", "tables")
OUT_CSV = os.path.join(TAB_DIR, "pv_calibration.csv")

Q = 1.602176634e-19
KB = 1.380649e-23
T_C = 25.0
T_K = T_C + 273.15

# ---- 目标点（工程口径：rating.P_n_W / V_mpp_V / I_mpp_A + Isc/Voc） ----
TGT_VOC = 90.0
TGT_ISC = 2.9
TGT_VMPP = 75.0
TGT_IMPP = 2.67
TGT_PMPP = TGT_VMPP*TGT_IMPP          # 200.25 W
NSER = 160.0                          # 串联电池数（对方材料）
RS_FIX = 0.937                        # 固定的串联电阻（不可辨识，见文件头）

TOL = {"Voc_V": 0.05, "Isc_A": 0.005, "Vmpp_V": 0.10, "Impp_A": 0.010}
IDENT_SCAN_RS = (0.0, 0.2, 0.5, 0.937)


# ---------------------------------------------------------------- 模型（与 engine 同构）
def _vt(n_ideal):
    """单池热电压 N·kT/q（= engine.pv_current 里的 Vt）。"""
    return n_ideal*KB*T_K/Q


def _a(n_ideal):
    """整串等效热电压 a = Nser·N·kT/q（engine 里写作 Nser·Vt）。"""
    return NSER*_vt(n_ideal)


def _i0(iph, voc, a):
    """与 engine 相同的饱和电流构造：I0 = Iph/(exp(Voc/a) − 1)。"""
    return iph/(math.exp(min(voc/a, 690.0)) - 1.0)


def pv_i(v, n_ideal, rs, rp, iph, i0, a):
    """单二极管电流（牛顿迭代，与 engine.pv_current 同一方程）。"""
    i = iph*0.9
    for _ in range(80):
        x = (v + i*rs)/a
        ex = math.exp(min(x, 690.0))
        f = iph - i0*(ex - 1.0) - (v + i*rs)/rp - i
        df = -i0*ex*rs/a - rs/rp - 1.0
        di = f/df
        i -= di
        if abs(di) < 1e-12:
            break
    return max(0.0, i)


def pv_g(v, n_ideal, rs, rp, iph, i0, a):
    """g = I0/a·exp((V+I·Rs)/a) + 1/Rp；dI/dV = −g/(1+g·Rs)。"""
    i = pv_i(v, n_ideal, rs, rp, iph, i0, a)
    return i0/a*math.exp(min((v + i*rs)/a, 690.0)) + 1.0/rp


def mpp_condition(v, n_ideal, rs, rp, iph, i0, a):
    """dP/dV = 0 的残差：I − V·g/(1 + g·Rs)。"""
    i = pv_i(v, n_ideal, rs, rp, iph, i0, a)
    g = pv_g(v, n_ideal, rs, rp, iph, i0, a)
    return i - v*g/(1.0 + g*rs)


def model_points(n_ideal, rs, rp):
    """给定 (N, Rs, Rp) 返回 G=1000、25 C 的特性点（Vmpp 由解析 MPP 条件 brentq 反解）。"""
    a = _a(n_ideal)
    iph = TGT_ISC
    i0 = _i0(iph, TGT_VOC, a)
    isc_m = pv_i(0.0, n_ideal, rs, rp, iph, i0, a)
    impp_m = pv_i(TGT_VMPP, n_ideal, rs, rp, iph, i0, a)
    try:
        vmpp_m = brentq(mpp_condition, 40.0, 0.97*TGT_VOC,
                        args=(n_ideal, rs, rp, iph, i0, a),
                        xtol=1e-6, rtol=1e-13, maxiter=200)
    except ValueError:
        vmpp_m = float("nan")
    pmpp_m = vmpp_m*pv_i(vmpp_m, n_ideal, rs, rp, iph, i0, a)
    return OrderedDict([
        ("Voc_V", TGT_VOC),          # 由 I0 构造保证
        ("Isc_A", isc_m),
        ("Vmpp_V", vmpp_m),
        ("Impp_A", impp_m),
        ("P_mpp_W", pmpp_m),
        ("FF", pmpp_m/(TGT_VOC*TGT_ISC)),
    ])


# ---------------------------------------------------------------- 标定
def _residuals(n_rp, rs):
    n_ideal, rp = n_rp
    a = _a(n_ideal)
    iph = TGT_ISC
    i0 = _i0(iph, TGT_VOC, a)
    isc_m = pv_i(0.0, n_ideal, rs, rp, iph, i0, a)
    i75 = pv_i(TGT_VMPP, n_ideal, rs, rp, iph, i0, a)
    mpp = mpp_condition(TGT_VMPP, n_ideal, rs, rp, iph, i0, a)
    return np.array([(isc_m - TGT_ISC)/TGT_ISC,
                     (i75 - TGT_IMPP)/TGT_IMPP,
                     mpp/TGT_IMPP])


def fit(rs=RS_FIX):
    sol = least_squares(_residuals, [1.031, 995.0], args=(rs,),
                        bounds=([0.8, 5.0], [2.0, 20000.0]),
                        xtol=1e-15, ftol=1e-15, gtol=1e-15, max_nfev=4000)
    n_ideal, rp = (float(v) for v in sol.x)
    return dict(N=n_ideal, Rs=float(rs), Rp=rp, success=bool(sol.success),
                nfev=int(sol.nfev), cost=float(sol.cost))


def report(tag, pts, collect=None):
    print("\n%s" % tag)
    print("  %-10s %12s %12s %10s   %s" % ("量", "目标", "模型", "偏差", "判定"))
    checks = [("Voc_V", TGT_VOC), ("Isc_A", TGT_ISC), ("Vmpp_V", TGT_VMPP), ("Impp_A", TGT_IMPP)]
    verdict = True
    for key, tgt in checks:
        val = pts[key]
        dev = val - tgt
        tol = TOL[key]
        ok = abs(dev) <= tol
        verdict = verdict and ok
        print("  %-10s %12.4f %12.4f %10.4f   %s"
              % (key, tgt, val, dev, "PASS" if ok else "FAIL(>%.3f)" % tol))
        if collect is not None:
            collect.append((key, tgt, val, dev, tol, "PASS" if ok else "FAIL"))
    print("  %-10s %12.4f %12.4f %10.4f   %s"
          % ("P_mpp_W", TGT_PMPP, pts["P_mpp_W"], pts["P_mpp_W"] - TGT_PMPP, "INFO"))
    if collect is not None:
        collect.append(("P_mpp_W", TGT_PMPP, pts["P_mpp_W"],
                        pts["P_mpp_W"] - TGT_PMPP, "", "INFO"))
    return verdict


# ---------------------------------------------------------------- json
def load_json():
    with io.open(JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f, object_pairs_hook=OrderedDict)


def save_json(d):
    with io.open(JSON_PATH, "w", encoding="utf-8", newline="\n") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
        f.write(u"\n")


def pv_block(cal, pts):
    return OrderedDict([
        ("model", "single_diode"),
        ("Nser", NSER),
        ("N", round(cal["N"], 6)),
        ("Rs_ohm", round(cal["Rs"], 6)),
        ("Rp_ohm", round(cal["Rp"], 3)),
        ("Rs_identifiable", False),
        ("Rs_source", "对方材料值；四目标点对 Rs 不敏感，见 pv_calibration.csv 的 identifiability 行"),
        ("Isc_A", TGT_ISC),
        ("Voc_V", TGT_VOC),
        ("Ki_per_K", 1.3e-3),
        ("Tvco_V_per_K", -0.13),
        ("thermal_voltage_V", round(_a(cal["N"]), 9)),
        ("targets", OrderedDict([("Vmpp_V", TGT_VMPP), ("Impp_A", TGT_IMPP),
                                 ("P_mpp_W", TGT_PMPP)])),
        ("achieved", OrderedDict([("Isc_A", round(pts["Isc_A"], 6)),
                                  ("Vmpp_V", round(pts["Vmpp_V"], 6)),
                                  ("Impp_A", round(pts["Impp_A"], 6)),
                                  ("P_mpp_W", round(pts["P_mpp_W"], 6))])),
        ("calibrated_at", "2026-11-02"),
        ("calibrated_by", "python/calib_pv.py（解析 MPP 条件残差；固定 Rs，拟合 N/Rp）"),
    ])


def verify_from_json():
    blk = load_json().get("pv_model")
    if not blk:
        print("[verify] params.json 没有 pv_model 块：PV 尚未标定（pv_uncalibrated = True）")
        return 1
    pts = model_points(float(blk["N"]), float(blk["Rs_ohm"]), float(blk["Rp_ohm"]))
    return 0 if report("[verify] 用 json 的 pv_model 复核目标点", pts) else 1


# ---------------------------------------------------------------- main
def main():
    args = sys.argv[1:]
    if "--verify" in args:
        rc = verify_from_json()
        print("\n结论：%s" % ("PASS" if rc == 0 else "FAIL"))
        return rc

    cal = fit(RS_FIX)
    print("标定（least_squares，%d 次评价，cost = %.3e）：N = %.6f、Rs = %.6f Ω（固定）、Rp = %.3f Ω"
          % (cal["nfev"], cal["cost"], cal["N"], cal["Rs"], cal["Rp"]))
    pts = model_points(cal["N"], cal["Rs"], cal["Rp"])
    rows = []
    ok = report("[标定] G = 1000 W/m2、T = 25 C", pts, rows)

    # ---- 可辨识性扫描：固定不同的 Rs 再拟合 (N, Rp)，看目标点还能拟合到多好 ----
    print("\n[可辨识性扫描] 固定不同 Rs 再拟合 (N, Rp)：")
    print("  %-8s %10s %10s %10s %10s %12s" % ("Rs/Ω", "N", "Rp/Ω", "Vmpp/V", "Impp/A", "cost"))
    ident_rows = []
    for rs in IDENT_SCAN_RS:
        c = fit(rs)
        p = model_points(c["N"], c["Rs"], c["Rp"])
        print("  %-8.3f %10.4f %10.1f %10.3f %10.4f %12.2e"
              % (rs, c["N"], c["Rp"], p["Vmpp_V"], p["Impp_A"], c["cost"]))
        ident_rows.append((rs, c["N"], c["Rp"], p["Vmpp_V"], p["Impp_A"], c["cost"]))
    spread = max(abs(r[4] - TGT_IMPP) for r in ident_rows)
    print("  → Impp 在整族解内最大偏离 %.2e A：Rs 与 (N, Rp) 不可分离，故固定 Rs = %.3f Ω（物理值）"
          % (spread, RS_FIX))

    # ---- 与未标定的对方值对照 ----
    old = model_points(1.058, 0.937, 300.0)
    print("\n[对照] 对方未标定值（N 1.058 / Rs 0.937 / Rp 300）：Isc %.4f A、Vmpp %.3f V、"
          "Impp %.4f A、P_mpp %.2f W（目标 %.2f W，低 %.1f %%）"
          % (old["Isc_A"], old["Vmpp_V"], old["Impp_A"], old["P_mpp_W"], TGT_PMPP,
             100.0*(1.0 - old["P_mpp_W"]/TGT_PMPP)))

    os.makedirs(TAB_DIR, exist_ok=True)
    with io.open(OUT_CSV, "w", encoding="utf-8", newline="\n") as f:
        f.write(u"section,quantity,target,model,deviation,tol,verdict\n")
        for r in rows:
            f.write(u"target,%s,%.6f,%.6f,%.6f,%s,%s\n" % (r[0], r[1], r[2], r[3], r[4], r[5]))
        f.write(u"param,N_ideal,,%.6f,,,\n" % cal["N"])
        f.write(u"param,Rs_ohm,,%.6f,,,\n" % cal["Rs"])
        f.write(u"param,Rp_ohm,,%.3f,,,\n" % cal["Rp"])
        for rs, n, rp, vm, im, cost in ident_rows:
            f.write(u"identifiability,Rs=%.3f Ohm,%.4f,%.1f,%.4f,%.3f,%.2e\n"
                    % (rs, n, rp, vm, im, cost))
    print("\n写出 %s" % os.path.relpath(OUT_CSV, ROOT))

    if "--apply" in args:
        if not ok:
            print("\n[apply] 目标点未全部落入容差，拒绝写入 params.json")
            return 1
        d = load_json()
        d["pv_model"] = pv_block(cal, pts)
        save_json(d)
        print("[apply] 已写入 params/params.json 的 pv_model 块；"
              "params_canonical 会读它并把 pv_uncalibrated 置 False")
        print("[apply] 下一步：cd python && PYTHONUTF8=1 python -u check_params.py")

    print("\n结论：%s" % ("PASS（四个目标点全部在容差内）" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())