# 交付物对照表（软件先行阶段，2026-11-03 更新）

> 出处：对应《技术需求文档》第十一章交付物逐项列表。本文只列该章明确给出的交付物，不编造未定稿项。
>
> 平台与口径：TI C2000（F28379D）；PV 75 V / 2.7 A / 200 W → 单相 H 桥（20 kHz 单极性倍频，纹波 40 kHz）→ L 或 LC 耦合网络 → PCC 36 V / 50 Hz（隔离变压器侧）。
> 参数唯一真源 = [`params/params.json`](../params/params.json)：`f_sw=20 kHz`、`L=0.5 mH`、`C=20 µF`、`R_d=0/1/2.2 Ω`、`L_g=0.5 mH`、`C_dc=4.5 mF`、死区 400 ns。
> 测量口径：THD 按 2–50 次、窗 200 ms、分辨率 5 Hz；THD 不含 40 kHz 开关纹波，另设高通纹波峰峰值与 40 kHz 分量占基波百分比。
>
> 本文旧版（2026-10-20）仍按"阶段 1–6"叙述、证据列多为"—"，与仓库现状脱节，故整表重写为按**实际文件**指证。

## 1. 完成度总览

| 分类 | 数量 | 说明 |
| --- | --- | --- |
| ✅ 已交付（可独立验收） | 4 | 交付物 4、5、7 + 交付物 6 的系统级部分 |
| 🔵 软件部分完成、待硬件补齐 | 1 | 交付物 11 结题报告（初稿已成，实验章留空） |
| ⏳ 待硬件 | 7 | 交付物 1、2、3、8、9、10、12 |
| ⚠️ 仍未做的软件项 | 1 | 交付物 6 的 EDA 工程图纸（任务书与网表已备） |

## 2. 逐项对照

| # | 交付物 | 状态 | 证据（相对仓库根） | 验收方式 |
| --- | --- | --- | --- | --- |
| 1 | 样机 1 套 | ⏳ 待硬件 | 采购与接线依据：[`docs/14`](14_原理图与BOM.md) §4–§5、[`BOM_canonical.csv`](../results/tables/BOM_canonical.csv) 18 项 | 硬件到位后按 [`docs/02`](02_experiment_protocol.md) E9 启动并网验收 |
| 2 | L 耦合模块 1 套 | ⏳ 待硬件 | 模块规范 [`docs/14`](14_原理图与BOM.md) §4.2（4 位端子 a/b/PCC_L/PCC_N，与 LC 共用同一只 0.5 mH 电感） | 上电后 LCR 表实测贴签 |
| 3 | LC 耦合模块 1 套 | ⏳ 待硬件 | 同上；**R_d 必装**（A5 实测 R_d=0 三功率点全发散），BOM 第 9 项 1 Ω / 2.2 Ω 各一只 | E7 定 R_d 最终值 |
| 4 | DSP 完整工程代码 | ✅ 已交付（PC 可编译可测） | [`dsp/`](../dsp) 35 文件 3318 行：11 头文件 + 11 源文件 + [`tests/test_control.c`](../dsp/tests/test_control.c)（11 组单测）+ [`ccs/`](../dsp/ccs) CCS 工程（含 `pv_inverter.syscfg`、链接脚本、`build/` 编译产物） | `python tools/verify_all.py` 的 V1 项：`SUMMARY PASS (0 failed)` |
| 5 | Simulink 模型（含 L 与 LC） | ✅ 已交付 | [`matlab/PV_LC_models_R2023a/`](../matlab/PV_LC_models_R2023a) 29 个 `.slx`（R2023a 原生重建）+ [`build_simulink_model.m`](../matlab/build_simulink_model.m)、[`run_sim_tasks_matlab.m`](../matlab/run_sim_tasks_matlab.m) | [`docs/10`](10_verify_all_2023a明细.txt) 607 项 ALL PASS；[`docs/08`](08_对齐验证报告_R2023a.md) 对齐报告 |
| 6 | 原理图及关键参数表 | 🔵 系统级已交付，EDA 图纸未画 | 已交付：[`docs/14`](14_原理图与BOM.md)（四功能域 + §2 参数校核 8 项 + §3 采样标定表 + §5 BOM）、[`docs/schematic_system.svg`](schematic_system.svg)（1240×900）、[`netlist_canonical.csv`](../results/tables/netlist_canonical.csv)（147 行/61 网络/49 位号）。未交付：[`docs/16`](16_EDA原理图任务书.md) 要求的 KiCad/Altium 工程图纸与 ERC 报告 | 已交付部分：`check_svg_layout.py`、`check_netlist.py` 双 PASS；图纸部分按 docs/16 §1 六条验收 |
| 7 | LC 谐振频率计算与参数选择说明 | ✅ 已交付 | [`docs/12`](12_参数口径与单一真源.md) §6（A5 解析层 + 时域 + 阻尼扫描 + 六条结论）、[`python/params_canonical.py`](../python/params_canonical.py)、[`A5_analytic.csv`](../results/tables/A5_analytic.csv) | `check_params.py` 冻结口径 15 项 + A5 产物复算 |
| 8 | L 结构 ≥3 功率点实验数据 | ⏳ 待硬件 | 协议 [`docs/02`](02_experiment_protocol.md) E1–E3（35/65/90 %）；数据目录 `data/experiments/`（当前仅 `.gitkeep`）；命名规则见 [`docs/13`](13_编号映射.md) | 原始 CSV 完整 + `process_scope_csv.m` 汇总 |
| 9 | LC 结构 ≥3 功率点实验数据 | ⏳ 待硬件 | 同上 E4–E6；E7 追加 R_d 对比 | 同上 |
| 10 | ≥3 组核心对比图 | ⏳ 待硬件 | 仿真侧已有可代打的图：`results/figures/A5_thd_comp.png` 等 7 张（**报告中须标明是仿真**）；实测图待 E1–E7 数据 | THD 与 40 kHz 纹波分开成图 |
| 11 | 结题报告 | 🔵 初稿已成 | [`docs/15`](15_结题报告初稿.md)（212 行 / 10 章）；§六 实验方案与 §七 交付物清单留待实测回填 | 实验章回填后按 docs/15 §7 核对 |
| 12 | 5–10 分钟演示视频 | ⏳ 待硬件 | 脚本骨架见 docs/15 §9（覆盖 E8 阶跃、E9 启动、核心对比图） | 实物演示 + 字幕 |

## 3. 未做项与依赖顺序

1. **EDA 工程图纸**（交付物 6 的剩余部分）：任务书 [`docs/16`](16_EDA原理图任务书.md) + 网表已就位，画图 3–5 个工作日，须在"采购到货后、硬件调试前"窗口完成；其中 6 条待定项已列在 docs/16 §8。
2. **实验数据与对比图**（8/9/10）：完全依赖硬件；先按 [`docs/02`](02_experiment_protocol.md) 走 E1–E3 → E4–E6 → E7，示波器 CSV 用 [`process_scope_csv.m`](../matlab/process_scope_csv.m) 一键汇总（该脚本已于 2026-11-03 用合成数据空跑验证，见下文 §4）。
3. **结题报告定稿**（11）：只需在报告 §六/§七 回填 E1–E10 实测数据与三组对比图，其余章节已定稿。
4. **演示视频**（12）：硬件整机稳定运行后录制，素材清单见 docs/15 §9。

## 4. 复现与门禁

```sh
python tools/verify_all.py        # 全量 6 项（DSP 单测 / 参数 / 网表 / 版式 / 参数设计 / 产物齐全）
python tools/verify_all.py --quick  # 跳过需要 gcc 与会覆写产物的两项
```

2026-11-03 实测：`PASS 6 / FAIL 0 / SKIP 0，总耗时 4.4 s`（V1 DSP 单测 `SUMMARY PASS (0 failed)`；V2 `PASS 103 / FAIL 0`；V3 网表 `硬错误 0`；V4 版式 23 块 68 条文字；V6 15 个产物齐全）。

示波器 CSV 管线空跑（2026-11-03 实测通过）：`python tools/make_synthetic_scope.py` 生成 3 个合成波形（`data/experiments/_synthetic/`，fs=500 kHz、0.25 s、各 4.35 MB，**不入库**），再由
`matlab -batch "cd('matlab'); process_scope_csv('../data/experiments/_synthetic', 500000)"` 汇总。回读值与设定值一致，证明列名／单位／采样率／200 ms 窗口／2–50 次 THD／40 kHz 簇口径全对：

| 合成文件 | 设定 THD | 回读 THD | 设定 40 kHz 纹波峰峰 | 回读 RIP | 回读 SW40（占基波） | 基波峰值 |
| --- | --- | --- | --- | --- | --- | --- |
| SYNTH_L_35 | 5.0 % | **4.9998 %** | 0.90 A | 0.90059 | 9.8182 % | 2.75 A |
| SYNTH_L_65 | 3.0 % | **2.9998 %** | 0.90 A | 0.90282 | 5.2837 % | 5.11 A |
| SYNTH_LC_65_Rd1 | 0.8 % | **0.79982 %** | 0.06 A | 0.065479 | 0.35223 % | 5.11 A |

汇总表落在 `results/tables/thd_ripple_summary.csv`（合成数据产物，演练后移到 `.work/scope_dryrun/` 不入库）；接真机后同一命令直接出汇总。
