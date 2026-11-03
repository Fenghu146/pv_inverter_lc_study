#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""verify_all.py — 一键验收（提交前门禁）

把散落在四条命令里的机器校验收成一个入口，任何一项 FAIL 就整体失败。

检查项（按依赖顺序，前者失败不影响后者执行）：
  V1  DSP 算法单元测试          gcc 编译 dsp/tests/test_control.c + src/*.c 后运行
  V2  参数唯一真源一致性        python/check_params.py（要求 PASS 且 FAIL=0）
  V3  网表一致性                tools/check_netlist.py（硬错误必须为 0）
  V4  系统框图版式              tools/check_svg_layout.py
  V5  参数设计复算              python/design/param_design.py（重算并覆写 results/tables/param_design.txt）
  V6  关键产物存在性            交付给结论的 CSV/PNG 是否齐全（不校验数值，只防丢文件）
  V7  SITL 闭环冒烟             编出 sitl.dll 后跑 0.8 s，要求状态机走到 MPPT_RUN、出稳态指标且无故障

用法：
  python tools/verify_all.py            # 全量（V1–V6）
  python tools/verify_all.py --quick    # 跳过 V1（需要 gcc）与 V5（会覆写产物）
  python tools/verify_all.py --list     # 只列出检查项

退出码：0 = 全通过；1 = 有 FAIL。
"""
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable or "python"

# V6：结论所依赖的产物（相对 ROOT）。缺任何一个都说明管线没跑完或被删。
ARTIFACTS = [
    "results/tables/params_check.csv",
    "results/tables/param_design.txt",
    "results/tables/A0_hf_atten.csv",
    "results/tables/A1_lscan.csv",
    "results/tables/A2_core.csv",
    "results/tables/A3_step.csv",
    "results/tables/A4_mppt.csv",
    "results/tables/A5_core.csv",
    "results/tables/A5_rd_sweep.csv",
    "results/tables/BOM_canonical.csv",
    "results/tables/netlist_canonical.csv",
    "results/tables/pv_calibration.csv",
    "results/tables/SITL_core.csv",
    "results/figures/A5_thd_comp.png",
    "results/figures/param_design.png",
    "docs/schematic_system.svg",
]


def _run(cmd, cwd, env_extra=None):
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    if env_extra:
        env.update(env_extra)
    t0 = time.time()
    p = subprocess.run(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                       errors="replace")
    return p.returncode, p.stdout or "", time.time() - t0


def v1_dsp_tests():
    dsp = os.path.join(ROOT, "dsp")
    exe = os.path.join(dsp, "tests", "test_control.exe")
    srcs = []
    for d in ("src",):
        full = os.path.join(dsp, d)
        srcs += [os.path.join(full, f) for f in sorted(os.listdir(full)) if f.endswith(".c")]
    cmd = ["gcc", "-std=c99", "-O2", "-I", "include",
           os.path.join("tests", "test_control.c")] + \
          [os.path.relpath(s, dsp) for s in srcs] + ["-o", os.path.relpath(exe, dsp)]
    rc, out, dt = _run(cmd, dsp)
    if rc != 0:
        return False, "gcc 编译失败：\n" + out.strip()[-800:], dt
    rc, out, dt2 = _run([exe], dsp)
    ok = rc == 0 and "SUMMARY PASS" in out
    tail = [ln for ln in out.strip().splitlines() if ln.strip()][-1:]
    return ok, (tail[0] if tail else "无输出"), dt + dt2


def v2_params():
    rc, out, dt = _run([PY, "-u", "check_params.py"], os.path.join(ROOT, "python"))
    line = [ln for ln in out.splitlines() if ln.startswith("合计：")]
    ok = rc == 0 and "FAIL 0" in out
    return ok, (line[-1].strip() if line else out.strip()[-300:]), dt


def v3_netlist():
    rc, out, dt = _run([PY, "tools/check_netlist.py"], ROOT)
    line = [ln for ln in out.splitlines() if "RESULT:" in ln]
    ok = rc == 0 and any("PASS" in ln for ln in line)
    return ok, (line[-1].strip() if line else out.strip()[-300:]), dt


def v4_svg():
    rc, out, dt = _run([PY, "tools/check_svg_layout.py"], ROOT)
    line = [ln for ln in out.splitlines() if "版式验收" in ln]
    ok = rc == 0 and any("PASS" in ln for ln in line)
    return ok, (line[-1].strip() if line else out.strip()[-300:]), dt


def v5_design():
    rc, out, dt = _run([PY, "-u", "design/param_design.py"], os.path.join(ROOT, "python"))
    idx = [i for i, ln in enumerate(out.splitlines()) if ln.strip().startswith("f_res(")]
    ok = rc == 0
    msg = out.splitlines()[idx[-1]].strip() if idx else "已重算"
    return ok, msg, dt


def v6_artifacts():
    t0 = time.time()
    missing = [p for p in ARTIFACTS if not os.path.isfile(os.path.join(ROOT, p))]
    if missing:
        return False, "缺少 %d 个产物：%s" % (len(missing), ", ".join(missing[:4])), time.time() - t0
    return True, "%d 个产物齐全" % len(ARTIFACTS), time.time() - t0


def v7_sitl():
    t0 = time.time()
    rc, out, dt = _run([PY, "tools/sitl_build.py"], ROOT)
    if rc != 0:
        return False, "编译 SITL 库失败：" + out.strip()[-400:], time.time() - t0
    rc, out, dt2 = _run([PY, "python/sitl.py", "--struct", "L", "--mode", "avg",
                         "--dur", "0.8"], ROOT)
    if rc != 0:
        return False, "SITL 运行失败：" + out.strip()[-400:], time.time() - t0
    reached = "MPPT_RUN" in out
    fault = "故障码" in out
    if not reached:
        return False, "状态机未走到 MPPT_RUN", time.time() - t0
    if fault:
        return False, "闭环中出现故障：" + [ln for ln in out.splitlines() if "故障码" in ln][-1], time.time() - t0
    line = [ln for ln in out.splitlines() if "末窗" in ln or "末拍" in ln]
    return True, (line[-1].strip() if line else "闭环正常"), time.time() - t0


CHECKS = [
    ("V1", "DSP 算法单元测试", v1_dsp_tests, True),
    ("V2", "参数唯一真源一致性", v2_params, True),
    ("V3", "网表一致性", v3_netlist, True),
    ("V4", "系统框图版式", v4_svg, True),
    ("V5", "参数设计复算", v5_design, True),
    ("V6", "关键产物存在性", v6_artifacts, True),
    ("V7", "SITL 闭环冒烟", v7_sitl, True),
]


def main(argv):
    quick = "--quick" in argv
    if "--list" in argv:
        for cid, name, _fn, heavy in CHECKS:
            print("%s  %s%s" % (cid, name, "（--quick 跳过）" if quick and heavy else ""))
        return 0

    skip = {"V1", "V5", "V7"} if quick else set()
    results = []
    print("一键验收  root=%s%s" % (ROOT, "  [--quick]" if quick else ""))
    print("-" * 78)
    for cid, name, fn, heavy in CHECKS:
        if cid in skip:
            results.append((cid, name, None, "已跳过", 0.0))
            print("%-3s %-22s SKIP   %s" % (cid, name, "（--quick）"))
            continue
        try:
            ok, msg, dt = fn()
        except Exception as exc:                                  # noqa: BLE001
            ok, msg, dt = False, "异常：%s" % exc, 0.0
        results.append((cid, name, ok, msg, dt))
        print("%-3s %-22s %-6s %5.1fs  %s" % (cid, name, "PASS" if ok else "FAIL", dt, msg))

    failed = [r for r in results if r[2] is False]
    skipped = [r for r in results if r[2] is None]
    total = sum(r[4] for r in results)
    print("-" * 78)
    print("汇总：PASS %d / FAIL %d / SKIP %d，总耗时 %.1fs"
          % (len(results) - len(failed) - len(skipped), len(failed), len(skipped), total))
    if failed:
        print("失败项：" + "、".join("%s %s" % (r[0], r[1]) for r in failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
