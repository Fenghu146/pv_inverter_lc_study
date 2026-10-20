# 基于 DSP 的光伏并网逆变器 L 与 LC 耦合结构研究 —— 工程底座

大创项目「基于DSP的光伏并网逆变器L与LC耦合结构对并网性能影响研究」的软件先行工程。
依据《技术需求文档》与《实现方案》《实施方案》搭建，参数统一取自 [params/params.json](params/params.json)。

## 当前状态（无硬件阶段已完成）

| 阶段 | 内容 | 状态 |
|---|---|---|
| 0 | 环境（Python 3.14 + scipy/matplotlib/control；MATLAB R2026b + Simulink + Simscape Electrical；Git；gcc） | ✅ |
| 1 | 参数设计 S1–S3（L 扫描、LC 谐振、稳定性判据） | ✅ |
| 2 | 仿真 S4–S6（三功率点对比、动态、MPPT） | ✅ |
| 3 | 数据分析工具链（THD/纹波/40kHz 统一口径，Python + MATLAB 双实现） | ✅ |
| 4 | DSP 算法层 C 代码 + PC 单元测试（gcc 编译全过） | ✅ |
| 5 | Simulink 模型构建脚本 | ✅ 框架 |
| 6 | 硬件联调与实验 E1–E10 | ⏳ 待硬件 |

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

## 目录结构

```
pv_inverter_lc_study/
├── params/params.json            # 参数单一数据源（与报告附录A一致）
├── python/
│   ├── design/param_design.py    # S1–S3 参数设计与理论计算
│   ├── sim/
│   │   ├── pv_model.py           # PV 单二极管模型(标定 Voc90/Isc2.9/Vmpp75)
│   │   ├── control_algos.py      # SOGI-PLL/PR/PI/P&O/保护/状态机(与C同参)
│   │   ├── inverter_sim.py       # 开关级(含死区)+平均模型时域仿真器
│   │   └── run_sim_tasks.py      # S1–S6 任务运行器
│   ├── analysis/metrics.py       # THD/纹波/40kHz 统一口径
│   └── tests/test_metrics.py     # 合成信号口径验证(7用例)
├── matlab/
│   ├── thd_metrics.m             # 同口径 MATLAB 实现(纯base MATLAB)
│   ├── process_scope_csv.m       # 实测/仿真 CSV 批处理
│   └── build_simulink_model.m    # Simulink 模型框架(R2026b ee_lib)
├── dsp/                          # C2000 硬件无关算法层(gcc 可编译)
│   ├── include/ src/ tests/
│   └── README.md                 # 移植说明
├── data/
│   ├── sim_results/              # 仿真CSV(不入库, 运行 run_sim_tasks.py 一键重生成)
│   └── experiments/              # 实测数据(待硬件, 命名 E{编号}_{L|LC}_{功率点}_{次数}_{日期}.csv)
├── results/
│   ├── figures/                  # 8 张图(S1–S6+参数设计)
│   └── tables/                   # 汇总表
└── docs/
    ├── 01_implementation_plan.md # 软件先行实施计划(阶段0–6)
    ├── 02_experiment_protocol.md # E1–E10 实验矩阵/公平性清单/记录表
    ├── 03_deliverables.md        # 交付物对照表
    ├── 04_risk_and_safety.md     # 风险与安全规程
    └── 05_acceptance_report.md   # 本次验收报告
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
