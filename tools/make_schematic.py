# -*- coding: utf-8 -*-
"""生成 docs/schematic_system.svg（系统级原理框图，工程口径）并导出 BOM CSV。"""
import io, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H = 1240, 900
OUT = os.path.join(ROOT, "docs", "schematic_system.svg")

DOMAIN = {
    "power":   ("#fdecea", "#c0392b", "#7b241c"),
    "module":  ("#fef5e7", "#b9770e", "#7e5109"),
    "drive":   ("#eaf2fb", "#2471a3", "#154360"),
    "sense":   ("#eafaf1", "#1e8449", "#14532d"),
    "control": ("#f4ecf7", "#7d3c98", "#4a235a"),
    "protect": ("#fdf2e9", "#ca6f1e", "#7e5109"),
}

def esc(s):
    return (s.replace(u"&", u"&amp;").replace(u"<", u"&lt;").replace(u">", u"&gt;"))

def box(x, y, w, h, title, lines=(), kind="power", dashed=False):
    bg, stroke, ink = DOMAIN[kind]
    out = []
    out.append(u'<rect x="%d" y="%d" width="%d" height="%d" rx="8" fill="%s" stroke="%s" stroke-width="2"%s/>'
               % (x, y, w, h, bg, stroke, u' stroke-dasharray="6,4"' if dashed else u""))
    out.append(u'<text x="%d" y="%d" font-family="Microsoft YaHei,Segoe UI" font-size="14" font-weight="700" fill="%s" text-anchor="middle">%s</text>'
               % (x + w // 2, y + 21, ink, esc(title)))
    ty = y + 39
    for ln in lines:
        out.append(u'<text x="%d" y="%d" font-family="Microsoft YaHei,Segoe UI" font-size="11" fill="#333" text-anchor="middle">%s</text>'
                   % (x + w // 2, ty, esc(ln)))
        ty += 15
    return u"\n".join(out)

def arrow(x1, y1, x2, y2, label=u"", color="#555", dashed=False, lx=None, ly=None):
    out = [u'<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s" stroke-width="2" marker-end="url(#ah)"%s/>'
           % (x1, y1, x2, y2, color, u' stroke-dasharray="5,4"' if dashed else u"")]
    if label:
        mx = lx if lx is not None else (x1 + x2) // 2
        my = ly if ly is not None else (y1 + y2) // 2 - 6
        out.append(u'<text x="%d" y="%d" font-family="Microsoft YaHei,Segoe UI" font-size="11" fill="%s" text-anchor="middle">%s</text>'
                   % (mx, my, color, esc(label)))
    return u"\n".join(out)

def text(x, y, s, size=12, weight="400", color="#222", anchor="start"):
    return (u'<text x="%d" y="%d" font-family="Microsoft YaHei,Segoe UI" font-size="%d" font-weight="%s" fill="%s" text-anchor="%s">%s</text>'
            % (x, y, size, weight, color, anchor, esc(s)))

p = []
p.append(u'<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">' % (W, H, W, H))
p.append(u'<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
         u'<path d="M0,0 L10,5 L0,10 z" fill="#555"/></marker></defs>')
p.append(u'<rect x="0" y="0" width="%d" height="%d" fill="#ffffff"/>' % (W, H))
p.append(text(24, 32, u"光伏并网逆变器 L / LC 耦合结构对比 —— 系统级原理框图（工程口径）", 19, "700"))
p.append(text(24, 53, u"口径：params/params.json（200 W · 36 Vrms/50 Hz · f_sw 20 kHz · L 0.5 mH · C 20 µF · R_d 0/1/2.2 Ω · L_g 0.5 mH · C_dc 4.5 mF · 死区 400 ns）", 11, "400", "#555"))
p.append(u'<line x1="20" y1="66" x2="%d" y2="66" stroke="#ddd" stroke-width="2"/>' % (W - 20))

# ---------- 主功率通路 ----------
p.append(text(24, 92, u"① 主功率通路（低压隔离，禁止直接接 220 V 市电）", 13, "700", "#c0392b"))
y = 110
h = 96
p.append(box(30, y, 158, h, u"光伏模拟电源", [u"Voc 90 V / Vmpp 75 V", u"Isc 2.9 A / Impp 2.67 A", u"200 W；按辐照 35/65/90 %"], "power"))
p.append(box(224, y, 140, h, u"预充 + 直流接触器", [u"100 Ω / 25 W 预充电阻", u"τ = 0.45 s，90 % 短接", u"启动限流 ≤3 A"], "power"))
p.append(box(400, y, 150, h, u"C_dc 4.5 mF", [u"2×2200 µF/100 V 电解", u"22 µF/100 V 薄膜去耦", u"母线纹波 <2 %"], "power"))
p.append(box(586, y, 168, h, u"H 桥（单极性倍频）", [u"4× MOSFET 100 V/40 A", u"R_ds(on) ≤ 25 mΩ", u"f_sw 20 kHz，死区 400 ns"], "power"))
p.append(box(790, y, 168, h, u"L / LC 耦合模块", [u"L：0.5 mH / 10 A", u"LC：并 20 µF + R_d 插座", u"跳线切换，共用同一 L"], "module"))
p.append(box(994, y, 216, h, u"隔离变压器 + PCC", [u"副边漏感 L_g ≈ 0.5 mH", u"空气开关/保险丝 10 A", u"交流接触器 25 A/250 V（DSP 控制）"], "power"))

p.append(arrow(188, y + h // 2, 222, y + h // 2))
p.append(arrow(364, y + h // 2, 398, y + h // 2))
p.append(arrow(550, y + h // 2, 584, y + h // 2, u"直流母线 75 V"))
p.append(arrow(754, y + h // 2, 788, y + h // 2, u"u_ab"))
p.append(arrow(958, y + h // 2, 992, y + h // 2, u"i_g"))

# ---------- 驱动 ----------
p.append(text(24, 250, u"② 驱动与辅助电源（隔离栅驱）", 13, "700", "#2471a3"))
y2 = 266
p.append(box(400, y2, 190, 86, u"隔离栅极驱动 ×2", [u"UCC21520（或 IR2110 + 自举）", u"自举二极管/电容、栅极电阻 10 Ω", u"驱动侧 +12 V，与 DSP 侧隔离"], "drive"))
p.append(box(614, y2, 190, 86, u"辅助电源", [u"+12 V（驱动/继电器）", u"+5 V、+3.3 V（ADC 参考 3.0 V）", u"AMC1311/AMC1301 隔离侧电源"], "drive"))
p.append(box(30, y2, 340, 86, u"功率级开关（H 桥四管）", [u"高/低边互补 + 死区 400 ns（ePWM 硬件死区）", u"栅极回路 10 Ω + 下拉，负压无关断", u"导热绝缘 + 母线吸收电容"], "drive"))
p.append(arrow(400, y2 + 43, 372, y2 + 43, u"PWM 6 路", color="#2471a3", lx=386, ly=y2 + 36))
p.append(arrow(670, y2 - 6, 668, y + h + 6, u"+12 V", color="#2471a3", lx=700, ly=y2 - 16))

# ---------- 采样调理 ----------
p.append(text(24, 392, u"③ 采样调理（5 路 → ADC，上电零偏自动校准）", 13, "700", "#1e8449"))
y3 = 408
p.append(box(30, y3, 210, 96, u"U_PV 直流电压", [u"分压比 100 : 3（100 V → 3.0 V）", u"RC 抗混叠 100 Ω + 1–2.2 nF", u"BAT54S 钳位 3.3 V，无偏置"], "sense"))
p.append(box(258, y3, 210, 96, u"u_g 交流电压", [u"分压比 60 : 1.5，中点偏置 1.5 V", u"RC 抗混叠 + 钳位", u"36 Vrms → 幅值 1.27 V"], "sense"))
p.append(box(486, y3, 246, 96, u"I_PV / i_g / i_L 电流", [u"5 mΩ 四线分流 + INA240A1（×20）", u"链路增益 0.1 V/A（=10 A/V），零点 1.5 V", u"±1.5 V → ±15 A，覆盖 10/12 A 保护点"], "sense"))
p.append(box(750, y3, 246, 96, u"抗混叠 + 保护通道", [u"每路 RC 100 Ω/1–2.2 nF 二阶", u"TLV3201 比较器：硬件过流阈值 12 A", u"输出 → ePWM TripZone（硬件封锁）"], "sense"))
p.append(arrow(240, y3 + 48, 258 + 0, y3 + 48))
p.append(arrow(468, y3 + 48, 486, y3 + 48))
p.append(arrow(732, y3 + 48, 750, y3 + 48))

# ---------- 控制与保护 ----------
p.append(text(24, 542, u"④ 控制、保护与联锁（TI C2000 F28379D）", 13, "700", "#7d3c98"))
y4 = 558
p.append(box(30, y4, 246, 112, u"F28379D LaunchPad", [u"ADC：5 路 + 零偏校准（1024 点平均）", u"ePWM：20 kHz 单极性倍频 + 硬件死区", u"TZ 硬件封锁；GPIO：接触器/继电器/急停"], "control"))
p.append(box(300, y4, 232, 112, u"软件保护（param.h 阈值）", [u"OC_SOFT 10 A / OC_HARD 12 A", u"V_dc 过压 95 V / 欠压 58 V", u"U_g 30–42 V、f_g 49–51 Hz、PLL 解锁"], "protect"))
p.append(box(558, y4, 232, 112, u"继电器/接触器驱动", [u"GPIO 直驱不足 → ULN2003 或 2N7002", u"线圈 12 V + 1N4148 续流", u"预充/接触器/急停三路联锁"], "protect"))
p.append(box(816, y4, 180, 112, u"急停 + 人工联锁", [u"常闭急停按钮直接断驱动", u"断电后待母线 <10 V", u"更换模块必须放电"], "protect"))
p.append(arrow(276, y4 + 56, 300, y4 + 56, u"采样/保护位", color="#7d3c98", lx=288, ly=y4 + 48))
p.append(arrow(532, y4 + 56, 558, y4 + 56, u"控制", color="#7d3c98", lx=545, ly=y4 + 48))
p.append(arrow(168, y4 - 6, 168, y3 + 102, u"ADC", dashed=True, color="#1e8449", lx=190, ly=y4 - 14))
p.append(arrow(276, y2 + 90, 300, y4 + 20, u"PWM/TZ", dashed=True, color="#2471a3", lx=352, ly=y2 + 100))

# ---------- 图例 ----------
p.append(u'<rect x="30" y="700" width="1180" height="176" rx="8" fill="#fbfbfb" stroke="#ddd"/>')
p.append(text(48, 726, u"图例与安全红线", 14, "700"))
lx = 48
for name, kind in [(u"主功率", "power"), (u"耦合模块", "module"), (u"驱动/电源", "drive"), (u"采样调理", "sense"), (u"控制", "control"), (u"保护/联锁", "protect")]:
    bg, stroke, ink = DOMAIN[kind]
    p.append(u'<rect x="%d" y="742" width="22" height="14" rx="3" fill="%s" stroke="%s"/>' % (lx, bg, stroke))
    p.append(text(lx + 28, 754, name, 11))
    lx += 132
p.append(text(48, 790, u"1) 全程低压小功率：直流侧 ≤100 V 用光伏模拟电源，交流侧经隔离变压器/电网模拟端；未经指导教师确认严禁直接接入 220 V 市电并网。", 12, "700", "#c0392b"))
p.append(text(48, 812, u"2) 上电顺序：辅助电源 → DSP 确认 PWM 封锁 → 直流源（限流 ≤3 A，经预充）→ 交流侧；硬件过流（12 A）经 TZ 硬件封锁，不依赖软件响应。", 12, "700", "#c0392b"))
p.append(text(48, 834, u"3) 首次上电：限流 → 空载 → 阻性负载 → 交流侧耦合；换模块必须断电并确认母线放电；硬件调试至少两人在场，接线经指导教师/实验室人员确认。", 12, "700", "#c0392b"))
p.append(text(48, 858, u"4) 两结构公平性：共用同一只 0.5 mH 电感、同一 DSP 程序与控制参数、同一测量点位；仅当 LC 明显谐振时允许加 R_d 或微调 Kp，并在报告中注明。", 12, "700", "#7e5109"))
p.append(u'</svg>')

with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
    f.write(u"\n".join(p))
print(u"written %s (%d bytes)" % (OUT, os.path.getsize(OUT)))

# ---------- BOM ----------
BOM = [
 (u"1", u"主控", u"TI C2000 F28379D LaunchPad（或 F28335 最小系统）", u"1", u"200 MHz，12 bit ADC，ePWM ×12 + TZ，工程口径 20 kHz/400 ns", u"《实现方案》§5"),
 (u"2", u"功率开关", u"N 沟道 MOSFET 100 V / 40 A，R_ds(on) ≤ 25 mΩ（IRF3710 / IRF3205 / IPP110N10 等同级）", u"4", u"H 桥四管；校核 8.3 A 峰值 ×1.3 余量", u"《实施方案》§4"),
 (u"3", u"栅极驱动", u"UCC21520（隔离，推荐）或 IR2110 + 自举网络（1N4148 + 10 µF/25 V）", u"2", u"高低边各一片；栅极电阻 10 Ω + 10 kΩ 下拉", u"《实现方案》§4/§5"),
 (u"4", u"辅助电源", u"+12 V/1 A、+5 V/1 A、+3.3 V/0.5 A；隔离 DCDC 为驱动与隔离放大供电", u"1 套", u"3.3 V 数字地与功率地单点连接", u"设计新增"),
 (u"5", u"直流母线电容", u"电解 2200 µF / 100 V ×2（合计 4.4 mF，容差内；如需 4.5 mF 并联 100 µF 薄膜）", u"2+1", u"母线纹波 <2 %；就近加 22 µF/100 V 薄膜", u"params.json C_dc 4.5 mF"),
 (u"6", u"预充与限流", u"100 Ω / 25 W 线绕或水泥电阻（建议 2 × 50 Ω/25 W 串联留余量）+ 直流接触器（或继电器）", u"1+1", u"τ = 0.45 s，母线 90 % 约 1.0 s；峰值 56 W@75 V / 81 W@90 V、单次能量 12.7–18.2 J，须按脉冲耐量选型；启动限流 ≤3 A", u"docs/14 §2 复算"),
 (u"7", u"耦合电感 L", u"铁硅铝环形磁芯（Kool Mµ 77439 / CS468125）绕制 0.5 mH / 10 A，或现成 0.5 mH/10 A 功率电感", u"1", u"3–4 股 0.6 mm 并绕，4–5 A/mm²；LCR 表 10 kHz 测值，0–10 A 偏置复测", u"params.json L 0.5 mH"),
 (u"8", u"滤波电容 C", u"CBB 薄膜 10 µF / 100 V ×2（或 20 µF / 250 VAC 薄膜）", u"2", u"低 ESR；两结构必须用同一只（同一批次）", u"params.json C 20 µF"),
 (u"9", u"阻尼电阻 R_d", u"无感线绕 1.0 Ω / ≥10 W、2.2 Ω / ≥10 W 各 1 只（插座可换；0 Ω 直通档仅作对照）", u"各 1", u"**必装**：A5 实测 R_d=0 时 LC 三个功率点全部发散（THD 95–379 %），起点 1 Ω；1 Ω 与 2.2 Ω 各一只供 E7 定最终值；与 C 串联、插拔式", u"params.json R_d 0/1/2.2 Ω；docs/12 §6"),
 (u"10", u"电流采样", u"5 mΩ / 5 W 四线分流电阻 + INA240A1（增益 20）", u"3", u"链路增益 0.1 V/A（=10 A/V）、零点 1.5 V，与 param.h 一致", u"param.h SENSE_I_GAIN 10"),
 (u"11", u"电压采样", u"分压网络 100 : 3（直流）、60 : 1.5 + 1.5 V 偏置（交流）+ 隔离放大 AMC1311/AMC1301（交流侧）", u"2 套", u"RC 抗混叠 100 Ω/1–2.2 nF，BAT54S 钳位 3.3 V", u"param.h SENSE_V_DIV / VAC_DIV"),
 (u"12", u"硬件过流保护", u"TLV3201 比较器 + 阈值网络（12 A → 2.7 V，含 1.5 V 偏置）", u"1", u"输出接 ePWM TZ，硬件封锁 PWM", u"param.h OC_HARD_A 12"),
 (u"13", u"继电器驱动", u"ULN2003 或 2N7002 + 1N4148 续流", u"3 路", u"预充/接触器/故障指示；GPIO 直驱不足", u"docs/05 已知限制 8"),
 (u"14", u"交流侧保护", u"空气开关或保险丝 10 A、交流接触器 25 A/250 V（DSP 控制）", u"各 1", u"动手前先断开交流接触器", u"《实现方案》§3"),
 (u"15", u"隔离与并网侧", u"隔离变压器（副边漏感即 L_g，实测约 0.5 mH）或可编程交流源/电网模拟端", u"1", u"副边短路用 LCR 表实测 L_g 并回填 params.json", u"params.json L_g 0.5 mH"),
 (u"16", u"耦合模块结构", u"L / LC 同尺寸小板 + 4 位端子（a, b, PCC_L, PCC_N）+ 跳线/拨动开关，贴实测参数标签", u"2 套", u"更推荐一块板 + 跳线共用同一电感", u"《实现方案》§4.3"),
 (u"17", u"测量仪器", u"示波器（≥1 Mpts、≥5 MS/s）+ 差分电压探头 + 隔离电流探头（或电流钳）+ LCR 表", u"1 套", u"示波器带宽限制 20 MHz；单次捕获 200 ms", u"docs/02 测量配置"),
 (u"18", u"光伏侧电源", u"光伏模拟电源（Voc 90 V / Isc 2.9 A / Vmpp 75 V / Impp 2.67 A，200 W）或 PV 组件 + 太阳能模拟器", u"1", u"按 35/65/90 % 改辐照得三功率点；Impp 取标定值（params.json pv_model、results/tables/pv_calibration.csv）", u"《实现方案》§3；python/calib_pv.py"),
]
CSV = os.path.join(ROOT, "results", "tables", "BOM_canonical.csv")
rows = [u"#,category,item,spec,qty,note,source"]
for r in BOM:
    rows.append(u"," .join([u'"%s"' % c.replace(u'"', u"'") for c in r]))
with io.open(CSV, "w", encoding="utf-8", newline="\n") as f:
    f.write(u"\n".join(rows) + u"\n")
print(u"written %s (%d rows)" % (CSV, len(BOM)))