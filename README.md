# 基于 DSP 的光伏并网逆变器 L 与 LC 耦合结构研究 —— 工程底座

大创项目「基于DSP的光伏并网逆变器L与LC耦合结构对并网性能影响研究」的软件先行工程。
依据《技术需求文档》与《实现方案》《实施方案》搭建，参数统一取自 [params/params.json](params/params.json)。

## 当前状态（无硬件阶段已完成）

| 阶段 | 内容 | 状态 |
|---|---|---|
| 0 | 环境（Python 3.13 + scipy/matplotlib；**MATLAB R2023a Update 8（学校同款，D:\MATLAB）** + Simulink + Simscape Electrical + Control/Signal Toolbox；Git；gcc） | ✅ |
| 1 | 参数设计 S1–S3（L 扫描、LC 谐振、稳定性判据，解析计算） | ✅ |
| 2 | 仿真 S4–S6（旧 Python 开关级） | ⚠️ **已被 merged/ 取代**：开关级 PWM 脉宽量化伪影导致 THD 虚高（详见 merged/README），时域结论以 merged/ A2–A4 为准；解析结论 S2/S3 仍有效 |
| 3 | 数据分析工具链（THD/纹波/40kHz 统一口径，Python + MATLAB 双实现） | ✅ |
| 4 | DSP 算法层 C 代码 + PC 单元测试（gcc 编译全过） | ✅ |
| 5 | **统一验证版**：merged/（平均模型 A0–A4）+ R2023a 开关模型（607 项 ALL PASS） | ✅ 见下方"统一版本说明" |
| 6 | 硬件联调与实验 E1–E10 | ⏳ 待硬件 |

## 统一版本说明（2026-10-27 版本统一）

**主版本 = 经过验证的 R2023a 合并版（2026-10-29 结构统一后，合并版已并入根目录）**：

- `python/params_merged.py + engine.py + metrics.py + analytic.py + run_tasks.py`
  —— 合并仿真管线（纯 Python，任何机器可跑）：对方控制算法移植 + 统一参数，
  一键重生成 `results/` 下的 A0–A4 数据与图；
- `matlab/PV_LC_models_R2023a/` —— 对方 28 个开关模型在 R2023a 上重建的**原生版本**
  （本机 verify_all 607/607 ALL PASS，run_l3('core') 与 git 基准逐位一致）；
- `matlab/reference_PV_LC_2023a/` —— 对方控制源码存档（control/*.m + project_params.m + 结论报告）；
- `docs/07–10` —— 合并版说明 / 对齐验证报告 / R2023a 复现指南 / 607 项 PASS 明细；
- 复现入口：`python python/run_tasks.py`（合并管线）；
  `docs/08_对齐验证报告_R2023a.md` 第 6 节（R2023a 开关层，命令照抄）。

**参考存档**（不再维护，仅供版本对照）：

- `matlab/archive_R2026b_pv_inverter_L_LC.slx` —— 我方 R2026b 框架模型（R2023a 打不开）；
- 对方仓库 `models_R2024b_backup/` —— R2024b 原始模型（R2023a 打不开，重建成 R2023a 后保留）。

**已归档/清除**：旧 Python 开关级管线（`archive/python_old_sim/`，含 PWM 量化伪影）、
我方 R2026b 框架模型（`archive/R2026b_pv_inverter_L_LC.slx`）；旧管线输出的
S1/S4/S5/S6 图与 sim_summary* 表（THD 23–30% 为伪影，非物理）已删除；
未经核验的 R2023b 降级导出件已被 R2023a 原生重建取代，一并删除。

## 快速开始

```powershell
# 1. 参数设计（L/C/R_d/f0/纹波预估）
python python\design\param_design.py

# 2. 仿真任务 S1–S6（开关级 + 平均模型）→ 生成 15 个 CSV + 图 + 汇总表
python python\sim\run_sim_tasks.py

# 3. 分析口径单元测试
python python\tests\test_metrics.py

# 4. DSP 算法单元测试
cd dsp
gcc -std=c99 -O2 -I include tests\test_control.c src\*.c -o tests\test_control.exe
.\tests\test_control.exe

# 5. MATLAB（R2026b，实测 CSV 处理）
# >> cd matlab; T = process_scope_csv('..\data\experiments', 5e6)
# >> build_simulink_model   % 模型框架，ee_lib 连线按注释完成
```

## 目录结构（2026-10-29 结构统一后）

```
pv_inverter_lc_study/
├── params/params.json            # 《实现方案》参数（param_design.py 设计探索用；验证版参数在 python/params_merged.py）
├── python/                       # ★ 正式仿真管线（2023a 验证版，纯 Python）
│   ├── params_merged.py          #   统一参数源（对方验证设计值，逐项标注出处）
│   ├── engine.py                 #   对方控制算法逐行移植 + 平均功率级 + 死区误差注入
│   ├── metrics.py / analytic.py  #   THD(2-50)/TDD 口径 + LCL 谐振/衰减解析
│   ├── run_tasks.py              #   A0–A4 一键重生成 results/
│   └── design/param_design.py    #   S1–S3 参数设计探索（解析）
├── matlab/                       # ★ MATLAB 侧（2023a 正式版）
│   ├── PV_LC_models_R2023a/      #   对方 28 个开关模型 R2023a 原生版（607 项 ALL PASS）
│   ├── reference_PV_LC_2023a/    #   对方控制源码存档（含结论报告）
│   ├── thd_metrics.m             #   THD 口径 MATLAB 实现
│   ├── process_scope_csv.m       #   实测 CSV 批处理（实验阶段用）
│   └── build_simulink_model.m    #   我方框架模型生成脚本
├── dsp/                          # C2000 算法层 C 代码（gcc/TI 编译通过）
├── results/                      # figures/ + tables/（解析产物 + A0–A4 验证数据共存）
├── data/                         # experiments/（实验阶段）+ sim_results/（重生成用）
├── docs/                         # 01–06 计划/规程 + 07–10 合并版说明/对齐报告/复现指南/607 明细
├── archive/                      # 参考存档（不再维护）
│   ├── python_old_sim/           #   旧 Python 开关级（PWM 量化伪影版）
│   ├── python_old_analysis/      #   旧口径实现与测试
│   ├── python_old_tests/
│   └── R2026b_pv_inverter_L_LC.slx
└── 对方仓库（Desktop\大创\仿真\仿真）  # PV_LC_project：models/=R2023a 重建版，models_R2024b_backup/=R2024b 存档
```

## 统一口径（与报告 6.3/7.4 严格一致）

- **THD**：2–50 次谐波，200 ms 窗（10 工频周期），频率分辨率 5 Hz
- **高频纹波**：>5 kHz 高通后峰峰值
- **开关纹波**：40 kHz（2f_sw）簇幅值（含 ±50 Hz 工频调幅边带）及占基波百分比
- **对比公平性**：两种结构同 DSP 程序、同控制参数、同测量点位；仅 LC 明显谐振时允许调 R_d 或 Kp 并注明

## 已验证的核心结论（仿真，详见 docs/05_acceptance_report.md）

1. LC 对 40 kHz 开关纹波抑制显著：−28.6 dB（0.069 A vs 1.81 A 峰峰值）
2. LC 的 THD 未必更低（低次谐波经谐振反而略高 2–3 个百分点）——两类指标必须分开报告
3. 电流环相位裕度 46.9° ≥ 30°，闭环稳定（含 1.5 拍延时）
4. MPPT 跟踪效率 99.9%（P&O 0.5 V/100 ms）
