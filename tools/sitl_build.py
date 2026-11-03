# -*- coding: utf-8 -*-
"""sitl_build.py — 把 dsp/ 的固件编成 SITL 动态库（给 python/sitl.py 用）

只做一件事：用 gcc 把 dsp/src/*.c + dsp/sim/sitl_bridge.c 编成共享库。
Windows 出 sitl.dll，Linux 出 sitl.so，python/sitl.py 会自动找。

用法：
  python tools/sitl_build.py            # 编译
  python tools/sitl_build.py --check    # 只检查是否已存在、是否比源码新
"""
import argparse
import glob
import os
import subprocess
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
SRC = sorted(glob.glob(os.path.join(ROOT, "dsp", "src", "*.c")))
BRIDGE = os.path.join(ROOT, "dsp", "sim", "sitl_bridge.c")
INC = [os.path.join(ROOT, "dsp", "include"), os.path.join(ROOT, "dsp", "sim")]
OUT_DIR = os.path.join(ROOT, "dsp", "sim", "build")


def lib_path():
    ext = ".dll" if os.name == "nt" else ".so"
    return os.path.join(OUT_DIR, "sitl" + ext)


def sources():
    return SRC + [BRIDGE]


def is_stale():
    out = lib_path()
    if not os.path.isfile(out):
        return True, "库还不存在"
    t_out = os.path.getmtime(out)
    for f in sources():
        if os.path.getmtime(f) > t_out:
            return True, "%s 比库新" % os.path.relpath(f, ROOT)
    hdrs = glob.glob(os.path.join(ROOT, "dsp", "include", "*.h")) + \
        glob.glob(os.path.join(ROOT, "dsp", "sim", "*.h"))
    for f in hdrs:
        if os.path.getmtime(f) > t_out:
            return True, "%s 比库新" % os.path.relpath(f, ROOT)
    return False, "已是最新"


def build(verbose=True):
    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR)
    cmd = ["gcc", "-std=c99", "-O2", "-Wall", "-Wextra"]
    for d in INC:
        cmd += ["-I", d]
    cmd += sources()
    cmd += ["-shared", "-o", lib_path(), "-lm"]
    if verbose:
        print(" ".join(os.path.relpath(c, ROOT) if c.startswith(ROOT) else c for c in cmd))
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if r.stdout.strip():
        print(r.stdout.strip())
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
        return False
    warn = [ln for ln in r.stderr.splitlines() if ln.strip()]
    for ln in warn:
        print("gcc: " + ln)
    print("已生成 %s（%d 字节）"
          % (os.path.relpath(lib_path(), ROOT), os.path.getsize(lib_path())))
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只检查是否过期，不编译")
    args = ap.parse_args()
    stale, why = is_stale()
    if args.check:
        print("SITL 库：%s（%s）" % (os.path.relpath(lib_path(), ROOT), why))
        return 0 if not stale else 2
    if not stale:
        print("SITL 库已是最新，跳过编译")
        return 0
    return 0 if build() else 1


if __name__ == "__main__":
    sys.exit(main())
