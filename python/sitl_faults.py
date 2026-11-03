# -*- coding: utf-8 -*-
"""sitl_faults.py — 故障注入：过流 / 掉电 / PLL 失锁 / 硬件 Trip / 预充超时

A0–A5 全是"正常工况"的对比仿真，从来没有回答过两个现场问题：
  1) 故障发生时，保护多久动作、动作是否到位（PWM 封锁、继电器断开）；
  2) 故障消失后能不能安全恢复（复位路径、防"按着复位键闯故障"）。

本脚本用 SITL（dsp/src 真代码 + Python 主电路）跑场景矩阵，每个场景
都是"正常并网 → 注入故障 → 保持 → 恢复条件 → 请求复位 → 观察重启"。
默认功率级用 avg 模型（保护/状态机是拍级行为，avg 足够且快）。

用法：
  python python/sitl_faults.py                 # 全套（约 1 分钟）
  python python/sitl_faults.py --only F1,F3    # 只跑指定场景
  python python/sitl_faults.py --struct LC --rd 1
"""
import argparse
import csv
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sitl  # noqa: E402

TS = sitl.TS
ROOT = sitl.ROOT
OUT_CSV = os.path.join(ROOT, "results", "tables", "SITL_faults.csv")
TRACE_DIR = os.path.join(ROOT, ".work", "fault_traces")

# 故障位（param.h FAULT_*）
FAULT_NAMES = [
    (1, "OC_SOFT"), (2, "OC_HARD"), (4, "VDC_OV"), (8, "VDC_UV"),
    (16, "VAC_RANGE"), (32, "FREQ"), (64, "PLL_UNLOCK"), (128, "PRECHARGE"),
]


def fault_text(code):
    code = int(code)
    if code == 0:
        return "-"
    return "+".join(n for bit, n in FAULT_NAMES if code & bit) or str(code)


def _schedule_phase_jumps(t_inject, dur, jump_deg=60.0, period=0.025):
    """返回一组相位跳变时刻（用于制造持续的 PLL 失锁）。"""
    out = []
    t = t_inject
    while t < t_inject + dur:
        out.append(t)
        t += period
    return out, math.radians(jump_deg)


SCENARIOS = [
    {
        "id": "F1_OC_SIGNAL", "name": "过流（信号级注入 14 A）",
        "t_inject": 0.80, "t_restore": 0.86, "t_clear": 1.05, "t_end": 2.20,
        "action": "oc", "desc": "6 ms 14 A 故障电流：越过 OC_SOFT 10 A 与 OC_HARD 12 A",
    },
    {
        "id": "F9_GRID_INV", "name": "电网相位反相（母线过压）",
        "t_inject": 0.80, "t_restore": 0.86, "t_clear": 1.60, "t_end": 3.20,
        "action": "inv", "desc": "相位跳 180° 持续 60 ms：功率倒灌把母线顶到 95 V（靠泄放电阻等电压落回来）",
    },
    {
        "id": "F2_PCC_SHORT", "name": "PCC 对地短路",
        "t_inject": 0.80, "t_restore": 0.95, "t_clear": 1.10, "t_end": 2.30,
        "action": "short", "desc": "并网点短路 150 ms：交流电压塌陷 + 电流冲击",
    },
    {
        "id": "F3_PV_LOSS", "name": "PV 掉电（母线欠压）",
        "t_inject": 0.80, "t_restore": 1.30, "t_clear": 1.45, "t_end": 2.60,
        "action": "pv0", "desc": "辐照度掉到 0：C_dc 只放电，母线跌破 58 V",
    },
    {
        "id": "F4_VAC_SAG", "name": "电网电压跌落 50%",
        "t_inject": 0.80, "t_restore": 1.10, "t_clear": 1.25, "t_end": 2.40,
        "action": "sag", "desc": "36 V → 18 V（低于 VAC_RMS_MIN_V 30 V）",
    },
    {
        "id": "F5_FREQ_STEP", "name": "电网频率 50 → 55 Hz",
        "t_inject": 0.80, "t_restore": 1.10, "t_clear": 1.30, "t_end": 4.00,
        "action": "freq", "desc": "频率跳变越限（FREQ_MAX_HZ 51 Hz）",
    },
    {
        "id": "F6_PLL_JUMPS", "name": "相位连续跳变（PLL 失锁）",
        "t_inject": 0.80, "t_restore": 1.25, "t_clear": 1.40, "t_end": 3.50,
        "action": "phase", "desc": "每 25 ms 跳 60°：幅值/频率都正常，只有 PLL 失锁",
    },
    {
        "id": "F7_HW_TRIP", "name": "硬件 CMPSS 过流 Trip",
        "t_inject": 0.80, "t_restore": 0.95, "t_clear": 1.10, "t_end": 2.20,
        "action": "trip", "desc": "模拟比较器跳闸锁存：PWM 必须当拍封锁",
    },
    {
        "id": "F8_PRECHARGE_TO", "name": "预充超时",
        "t_inject": 0.00, "t_restore": 3.30, "t_clear": 3.40, "t_end": 4.60,
        "action": "pre_break", "desc": "预充回路断开：母线 3 s 内建不起来",
    },
]


class Scenario(object):
    def __init__(self, sc, struct="L", rd=0.0, mode="avg", nsub=40):
        self.sc = sc
        self.br = sitl.Bridge()
        self.br.reset(90.0)
        self.pl = sitl.Plant(struct=struct, rd=rd, mode=mode, nsub=nsub)
        self.struct = struct
        self.mode = mode
        self.trace = []
        self.jumps, self.jump_rad = _schedule_phase_jumps(
            sc["t_inject"], sc.get("jump_dur", 0.45)) if sc["action"] == "phase" else ([], 0.0)

    # ---- 注入/恢复 ----
    def apply(self, t):
        sc = self.sc
        a = sc["action"]
        on = sc["t_inject"] <= t < sc["t_restore"]
        if a == "oc":
            self.pl.i_inject = 14.0 if on else 0.0
        elif a == "short":
            self.pl.grid_short = on
        elif a == "pv0":
            self.pl.pv_scale = 0.0 if on else 1.0
        elif a == "sag":
            self.pl.grid_scale = 0.5 if on else 1.0
        elif a == "freq":
            self.pl.grid_freq = 55.0 if on else sitl.F_G
        elif a == "inv":
            if sc["t_inject"] <= t < sc["t_inject"] + TS:
                self.pl.ph_extra += math.pi
            elif sc["t_restore"] <= t < sc["t_restore"] + TS:
                self.pl.ph_extra -= math.pi
        elif a == "phase":
            for tj in self.jumps:
                if tj <= t < tj + TS:
                    self.pl.ph_extra += self.jump_rad
        elif a == "trip":
            if sc["t_inject"] <= t < sc["t_inject"] + TS:
                self.br.set_trip(1)
        elif a == "pre_break":
            self.pl.pre_break = on

    def run(self):
        sc = self.sc
        pl = self.pl
        br = self.br
        n = int(round(sc["t_end"] / TS))
        t = 0.0
        pre = relay = False
        cp = (0.0, 0.0)
        cleared = False
        self.trace = []
        for _ in range(n):
            self.apply(t)
            # 复位按钮：从 t_clear 起每 200 ms 试一次，直到真的恢复。
            # 故障条件还在时 protect_try_clear 会拒绝（防"按着复位键闯故障"），
            # 所以真实操作也是这样反复按到条件消失为止。
            if t >= sc["t_clear"] and (t - sc["t_clear"]) % 0.2 < TS:
                br.lib.sitl_request(0, 1)
                cleared = True
            si = pl.measure(t, pre, relay)
            out = br.step(si)
            pre = bool(out[15])
            relay = bool(out[10]) and not bool(out[16])
            pl.integrate(t, out[0], out[1], pre, relay, cmpa_prev=cp)
            cp = (float(out[0]), float(out[1]))
            st_now = int(out[11])
            if st_now in (4, 5, 6, 9):
                pl.contactor = True
            elif st_now == 7:
                pl.contactor = False
            self.trace.append((t, int(out[11]), int(out[12]), int(out[14]),
                               int(out[10]), int(out[16]), si[5], si[2],
                               si[3], si[4], out[8] / (2.0 * math.pi)))
            t += TS
        return self.metrics()

    def metrics(self):
        sc = self.sc
        tr = self.trace
        t_inj = sc["t_inject"]
        t_fault = None
        code = 0
        lat = float("nan")
        for row in tr:
            t, st, flt = row[0], row[1], row[2]
            if st == 7 and t >= t_inj - 1e-9:
                t_fault = t
                code = flt
                break
        # 保护动作延迟：注入后第一次 PWM 封锁（或进 FAULT）
        for row in tr:
            t, st, pwm = row[0], row[1], row[3]
            if t >= t_inj - 1e-9 and (pwm == 0 or st == 7):
                lat = (t - t_inj) * 1000.0
                break
        trip_seen = max((x[5] for x in tr), default=0)
        win = [x for x in tr if t_inj <= x[0] <= t_inj + 0.10]
        peak_ig = max((abs(x[6]) for x in win), default=0.0)
        vdc_min = min((x[7] for x in tr if t_inj <= x[0] <= sc["t_restore"] + 0.2),
                      default=float("nan"))
        # 恢复：clear 之后第一次回到 MPPT_RUN
        t_rec = None
        for row in tr:
            t, st = row[0], row[1]
            if t >= sc["t_clear"] - 1e-9 and st == 6:
                t_rec = t
                break
        st_end, flt_end = tr[-1][1], tr[-1][2]
        return {
            "scenario": sc["id"],
            "name": sc["name"],
            "struct": self.struct,
            "mode": self.mode,
            "desc": sc["desc"],
            "t_inject_s": round(t_inj, 3),
            "t_fault_s": round(t_fault, 4) if t_fault is not None else "",
            "latency_ms": round(lat, 2) if lat == lat else "",
            "fault_code": code,
            "fault_bits": fault_text(code),
            "hw_trip": trip_seen,
            "peak_i_g_A": round(peak_ig, 2),
            "vdc_min_V": round(vdc_min, 2) if vdc_min == vdc_min else "",
            "t_clear_s": round(sc["t_clear"], 3),
            "t_recover_s": round(t_rec, 4) if t_rec is not None else "",
            "recovered": 1 if t_rec is not None else 0,
            "final_state": sitl.R_NAME.get(st_end, st_end),
            "final_fault": flt_end,
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--struct", default="L")
    ap.add_argument("--rd", type=float, default=0.0)
    ap.add_argument("--mode", default="avg", choices=["avg", "sw"])
    ap.add_argument("--nsub", type=int, default=40)
    ap.add_argument("--only", default="")
    ap.add_argument("--out", default=OUT_CSV)
    args = ap.parse_args()

    only = [s.strip().upper() for s in args.only.split(",") if s.strip()]
    rows = []
    for sc in SCENARIOS:
        if only and not any(o in sc["id"].upper() for o in only):
            continue
        s = Scenario(sc, struct=args.struct.upper(), rd=args.rd, mode=args.mode,
                     nsub=args.nsub)
        r = s.run()
        rows.append(r)
        print("%-18s 注入 %5.2f s → FAULT %5.3f s（超时 %5.1f ms）%s"
              % (r["scenario"], r["t_inject_s"],
                 float(r["t_fault_s"]) if r["t_fault_s"] != "" else float("nan"),
                 float(r["latency_ms"]) if r["latency_ms"] != "" else float("nan"),
                 "  故障=" + r["fault_bits"]))
        print("                   峰值电流 %6.2f A  母线最低 %6.2f V  "
              "恢复=%s%s  末状态=%s"
              % (r["peak_i_g_A"], r["vdc_min_V"] if r["vdc_min_V"] != "" else float("nan"),
                 "是" if r["recovered"] else "否",
                 (" @ %.3f s" % r["t_recover_s"]) if r["recovered"] else "",
                 r["final_state"]))
        if not os.path.isdir(TRACE_DIR):
            os.makedirs(TRACE_DIR)
        fn = os.path.join(TRACE_DIR, "%s.csv" % r["scenario"])
        with open(fn, "w", newline="", encoding="utf-8") as f:
            f.write("t_s,state,fault,pwm_on,relay,trip,i_g,vdc,v_grid\n")
            for row in s.trace:
                f.write(",".join(str(round(v, 6)) if isinstance(v, float) else str(v)
                                 for v in row) + "\n")

    if rows:
        d = os.path.dirname(args.out)
        if d and not os.path.isdir(d):
            os.makedirs(d)
        keys = list(rows[0].keys())
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            for r in rows:
                w.writerow(r)
        print("\n已写 %s（%d 个场景）" % (os.path.relpath(args.out, ROOT), len(rows)))
        bad = [r["scenario"] for r in rows if not r["recovered"]]
        if bad:
            print("!! 未能恢复的场景：%s" % ", ".join(bad))
    return 0


if __name__ == "__main__":
    sys.exit(main())
