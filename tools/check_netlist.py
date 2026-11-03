#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""check_netlist.py — 校验 results/tables/netlist_canonical.csv（docs/16 的网表草稿）

检查项：
  1. UTF-8 无 BOM、可被 csv 解析、表头恰为 net,node_ref,node_pin,signal_type,source_ref
  2. 每行 5 字段、字段非空、signal_type 属于 {功率,驱动,采样,保护,电源,通信}
  3. 行数 >= 60
  4. source_ref 形如 `路径:行号` 或 `路径:行号-行号`，且该文件存在、行号不超出文件行数
  5. 统计：域分布、TBD 引脚数、单节点网络（悬空嫌疑）清单

退出码：0 = 无硬错误（可有警告），1 = 有硬错误。
用法：python tools/check_netlist.py
"""
import csv
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(ROOT, "results", "tables", "netlist_canonical.csv")
HEADER = ["net", "node_ref", "node_pin", "signal_type", "source_ref"]
DOMAINS = ["功率", "驱动", "采样", "保护", "电源", "通信"]
MIN_ROWS = 60

# 设计上就只有一个节点的网络（不是漏画），降级为 INFO 并写清原因。
# 新增条目必须给出原因；不在此表中的单节点网络仍然报 WARN。
ALLOWED_SINGLE = {
    "JTAG_TCK": "JTAG 排针位号未定（TBD，docs/16 §8 待定 5），U1 侧仅连一端；排针落位后补第二节点",
    "JTAG_TMS": "同上：JTAG 排针未落位，暂为单节点",
    "JTAG_TDI": "同上：JTAG 排针未落位，暂为单节点",
    "JTAG_TDO": "同上：JTAG 排针未落位，暂为单节点",
    "AGND": "模拟地单点汇合，网表按 docs/14:68 只登记控制板一端，整机装配时于单点与 PGND 汇合",
    "PGND": "功率地单点汇合，同上：按 docs/14:68 只登记一端，装配时与 AGND 单点相连",
}

errors = []
warnings = []
infos = []


def _lines_of(path):
    full = os.path.join(ROOT, path)
    if not os.path.isfile(full):
        return None
    with io.open(full, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read().count("\n") + 1


def _resolve(path):
    """source_ref 里允许写文档别名 docs/NN（如 docs/14），解析到 docs/NN_*.md。

    返回 (真实路径 或 None, 是否命中别名)。
    """
    if os.path.isfile(os.path.join(ROOT, path)):
        return path, False
    head, _, tail = path.rpartition("/")
    if head == "docs" and tail.isdigit():
        for name in sorted(os.listdir(os.path.join(ROOT, "docs"))):
            if name.startswith("%s_" % tail) and name.endswith(".md"):
                return "docs/%s" % name, True
    return None, False


def main():
    if not os.path.isfile(CSV_PATH):
        print("FAIL: 找不到 %s" % CSV_PATH)
        return 1

    with open(CSV_PATH, "rb") as fh:
        raw = fh.read()
    if raw.startswith(b"\xef\xbb\xbf"):
        errors.append("文件带 UTF-8 BOM")

    text = raw.decode("utf-8")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        print("FAIL: 文件为空")
        return 1
    if rows[0] != HEADER:
        errors.append("表头不符：%r（应为 %r）" % (rows[0], HEADER))

    body = rows[1:]
    domains = {d: 0 for d in DOMAINS}
    nets = {}
    tbd = []
    aliases = {}
    line_no = 1
    for r in body:
        line_no += 1
        if not r or all(c == "" for c in r):
            errors.append("第 %d 行为空行" % line_no)
            continue
        if len(r) != 5:
            errors.append("第 %d 行字段数 %d != 5：%r" % (line_no, len(r), r))
            continue
        net, ref, pin, sig, src = [c.strip() for c in r]
        for name, val in (("net", net), ("node_ref", ref), ("node_pin", pin),
                          ("signal_type", sig), ("source_ref", src)):
            if not val:
                errors.append("第 %d 行 %s 为空" % (line_no, name))
        if sig and sig not in DOMAINS:
            errors.append("第 %d 行 signal_type=%r 不在 %r" % (line_no, sig, DOMAINS))
        domains[sig] = domains.get(sig, 0) + 1
        nets.setdefault(net, []).append((ref, pin))
        if pin == "TBD":
            tbd.append((line_no, net, ref))

        # source_ref: 路径:行号[-行号]
        if src:
            path, _, lineno = src.rpartition(":")
            if not path or not lineno:
                errors.append("第 %d 行 source_ref 格式不符：%r" % (line_no, src))
            else:
                real, aliased = _resolve(path)
                n = _lines_of(real) if real else None
                if n is None:
                    errors.append("第 %d 行 source_ref 无法定位文件：%s" % (line_no, src))
                else:
                    if aliased:
                        aliases[path] = real
                    hi = lineno.split("-")[-1]
                    if hi.isdigit() and int(hi) > n:
                        errors.append("第 %d 行 source_ref 行号 %s 超出 %s 的 %d 行"
                                      % (line_no, hi, real, n))

    n_rows = len([r for r in body if len(r) == 5])
    if n_rows < MIN_ROWS:
        errors.append("行数 %d < %d" % (n_rows, MIN_ROWS))

    singles = sorted(k for k, v in nets.items() if len(v) == 1)
    for s in singles:
        if s in ALLOWED_SINGLE:
            infos.append("单节点（已确认豁免）：%s —— %s" % (s, ALLOWED_SINGLE[s]))
        else:
            warnings.append("单节点网络（悬空嫌疑）：%s 现只有 %r" % (s, nets[s][0]))

    print("== netlist_canonical.csv 校验 ==")
    print("文件：%s" % os.path.relpath(CSV_PATH, ROOT))
    print("字节：%d  行数（不含表头）：%d  网络数：%d  器件/模块位号数：%d"
          % (len(raw), n_rows, len(nets), len({r[1] for r in rows[1:] if len(r) == 5})))
    print("域分布：" + "  ".join("%s %d" % (d, domains.get(d, 0)) for d in DOMAINS))
    print("TBD 引脚：%d 处" % len(tbd))
    for ln, net, ref in tbd:
        print("  - 第 %d 行 %s / %s" % (ln, net, ref))
    if aliases:
        print("文档别名解析：" + "  ".join("%s → %s" % (k, v) for k, v in sorted(aliases.items())))
    print("单节点网络：%d 个（其中已确认豁免 %d 个）"
          % (len(singles), len([s for s in singles if s in ALLOWED_SINGLE])))
    for w in warnings:
        print("  ! " + w)
    for i in infos:
        print("  i " + i)

    if errors:
        print("\n硬错误 %d 条：" % len(errors))
        for e in errors:
            print("  x " + e)
        print("\nRESULT: FAIL")
        return 1
    print("\nRESULT: PASS（硬错误 0；警告 %d；豁免单节点 %d）" % (len(warnings), len(infos)))
    return 0


if __name__ == "__main__":
    sys.exit(main())