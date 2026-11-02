# -*- coding: utf-8 -*-
"""独立的 SVG 版式验收：解析 docs/schematic_system.svg，
1) 每个色块内文字（标题+说明行）的估算宽度必须放得下，且纵向不越界；
2) 各色块之间不得重叠；
3) 统计色块/箭头数量与域覆盖。
估算字宽：CJK/全角 = 字号 × 1.0，其余 = 字号 × 0.55（保守）。
"""
import io, os, re, sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SVG = os.path.join(ROOT, "docs", "schematic_system.svg")
NS = "{http://www.w3.org/2000/svg}"

BOX_FILLS = {"#fdecea", "#fef5e7", "#eaf2fb", "#eafaf1", "#f4ecf7", "#fdf2e9"}
tree = ET.parse(SVG)
root = tree.getroot()

rects, texts = [], []
for el in root.iter():
    tag = el.tag.replace(NS, "")
    if tag == "rect":
        rects.append((float(el.get("x")), float(el.get("y")), float(el.get("width")),
                      float(el.get("height")), (el.get("fill") or "").lower()))
    elif tag == "text":
        texts.append((float(el.get("x")), float(el.get("y")), float(el.get("font-size")),
                      el.get("font-weight") or "400", el.get("text-anchor") or "start",
                      u"".join(el.itertext())))

boxes = [r for r in rects if r[4] in BOX_FILLS]
lines_ = [r for r in rects if r[4] not in BOX_FILLS and r[2] < 40]
arrows = 0
for el in root.iter():
    if el.tag.replace(NS, "") == "line":
        arrows += 1
        lines_.append(None)

def est_width(s, size):
    w = 0.0
    for ch in s:
        w += size * (1.0 if ord(ch) > 0x2E80 else 0.55)
    return w

fails = []
print("色块 %d 个，文字 %d 条，线段/箭头 %d 条" % (len(boxes), len(texts), arrows))

# 1) 文字放得下
inside = 0
for tx, ty, size, weight, anchor, s in texts:
    if anchor != "middle":
        continue
    host = None
    for bx, by, bw, bh, fill in boxes:
        if bx <= tx <= bx + bw and by <= ty <= by + bh:
            host = (bx, by, bw, bh)
            break
    if host is None:
        continue  # 箭头标注等自由文字
    inside += 1
    bx, by, bw, bh = host
    w = est_width(s, size)
    if w > bw - 10:
        fails.append(u"文字超出宽度：%r 估宽 %.0f > 块宽 %.0f-10（块 %.0f,%.0f）" % (s, w, bw, bx, by))
    if ty > by + bh - 5:
        fails.append(u"文字纵向越界：%r y=%.0f > 块底 %.0f（块 %.0f,%.0f）" % (s, ty, by + bh - 5, bx, by))
print("落在色块内的文字 %d 条（应等于各块标题+说明行总数）" % inside)

# 2) 色块不重叠
for i in range(len(boxes)):
    for j in range(i + 1, len(boxes)):
        ax, ay, aw, ah, _ = boxes[i]
        bx, by, bw, bh, _ = boxes[j]
        if ax < bx + bw - 1 and bx < ax + aw - 1 and ay < by + bh - 1 and by < ay + ah - 1:
            fails.append(u"色块重叠：(%0.f,%0.f,%0.f,%0.f) 与 (%0.f,%0.f,%0.f,%0.f)" % (ax, ay, aw, ah, bx, by, bw, bh))

# 3) 域覆盖
kinds = {}
for bx, by, bw, bh, fill in boxes:
    kinds[fill] = kinds.get(fill, 0) + 1
print("各域色块数：", ", ".join(sorted("%s×%d" % (k, v) for k, v in kinds.items())))

# 4) 空白校验：SVG 文本不能含未替换占位符
raw = io.open(SVG, encoding="utf-8").read()
for bad in [u"TODO", u"???", u"XXXX", u"${"]:
    if bad in raw:
        fails.append(u"SVG 中含未替换占位符 %s" % bad)

if fails:
    print(u"\nFAIL %d 项：" % len(fails))
    for f in fails:
        print(u"  - " + f)
    sys.exit(1)
print(u"\n版式验收 PASS：%d 块、%d 条块内文字全部放得下且不越界，色块无重叠。" % (len(boxes), inside))