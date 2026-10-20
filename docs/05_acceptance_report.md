# 验收报告 —— 软件先行阶段（无硬件）

日期：2026-10-20　范围：工程底座 + 仿真 + 分析工具链 + DSP 算法层
依据：《技术需求文档》（技术文件2.docx）、《实现方案》、《实施方案》三份文档

## 一、要求-证据对照

| # | 要求（来源） | 证据 | 结论 |
|---|---|---|---|
| 1 | 制定计划（任务书） | [docs/01_implementation_plan.md](../docs/01_implementation_plan.md)：阶段0–6、S1–S6、E1–E10、验收标准 | ✅ |
| 2 | 新建工程文件夹、清晰文件结构（任务书） | `pv_inverter_lc_study/` 八个顶层分区（params/python/matlab/dsp/data/results/docs），README.md 有目录说明 | ✅ |
| 3 | 参数与报告严格一致（附录A参数速查表） | [params/params.json](../params/params.json) 单一数据源；计算值逐项吻合（见下表二） | ✅ |
| 4 | 耦合参数设计（方案 4.1/4.2/5.1/5.2） | [python/design/param_design.py](../python/design/param_design.py) → `results/tables/param_design.txt` + 图 | ✅ |
| 5 | 仿真任务 S1–S6（方案 6.2） | [python/sim/run_sim_tasks.py](../python/sim/run_sim_tasks.py) → 15 个 CSV + 8 张图 + sim_summary | ✅ |
| 6 | THD/纹波/40kHz 统一口径（方案 6.3/7.4） | [python/analysis/metrics.py](../python/analysis/metrics.py) + [matlab/thd_metrics.m](../matlab/thd_metrics.m) 双实现交叉验证一致 | ✅ |
| 7 | DSP 程序功能（技术文档 6.1） | [dsp/](../dsp/) 七模块 C99 代码（ADC/PWM 接口留移植层），gcc 编译 13 用例全过 | ✅ |
| 8 | 状态机与保护（方案 5.7） | fsm.c/protect.c + Python 同源实现，FAULT→人工复位路径验证 | ✅ |
| 9 | Simulink 仿真模型（方案 6.1） | [matlab/build_simulink_model.m](../matlab/build_simulink_model.m)（R2026b ee_lib 框架+参数配置） | ⚠️ 框架就绪，ee_lib 连线需 GUI 微调 |
| 10 | 实验方案/公平性/记录表（方案 7.1–7.4） | [docs/02_experiment_protocol.md](../docs/02_experiment_protocol.md) E1–E10 + 8 项清单 + 记录表 | ✅ |
| 11 | 交付物对照（技术文档 十一） | [docs/03_deliverables.md](../docs/03_deliverables.md) 12 项逐项状态 | ✅ |
| 12 | 安全规程（技术文档 十） | [docs/04_risk_and_safety.md](../docs/04_risk_and_safety.md) | ✅ |
| 13 | 样机/实验数据/演示视频（技术文档 十一） | 需硬件，属阶段6 | ⏳ 待硬件（非本阶段范围） |

## 二、参数计算与报告值逐项核对

| 参数 | 报告值 | 计算/仿真值 | 偏差 |
|---|---|---|---|
| f₀（不含 L_g） | 1590 Hz | 1591.5 Hz | +0.09% ✅ |
| Z₀ = √(L/C) | 5 Ω | 5.00 Ω | 0 ✅ |
| f_res（L_g=0.5mH） | 2.25 kHz | 2.251 kHz | +0.04% ✅ |
| f_res（L_g=0.1mH） | 3.9 kHz | 3.898 kHz | −0.05% ✅ |
| ΔI_pp,max（L=0.5mH） | ≈0.94 A | 0.938 A | ✅ |
| LC 40kHz 衰减 | "−25 dB 以上" | −28.6 dB（仿真 L vs LC 峰峰值 1.81→0.069 A） | ✅ |
| PV 标定 | Voc90/Isc2.9/Vmpp75/Impp2.7 | 90/2.90/75.7/2.72 | ✅ |
| 三功率点 | ≈70/130/180 W | 67.2/130.2/184.2 W（0.35/0.65/0.90 辐照） | ✅ |
| I_amp*（额定） | 7.86 A | 7.86 A | ✅ |

## 三、测试与验证结果

| 测试 | 命令 | 结果 |
|---|---|---|
| DSP 算法 C 单元测试 | `gcc -std=c99 -O2 -I include tests/test_control.c src/*.c` | **13 PASS / 0 FAIL**（PLL 锁相 0.0396 rad<0.1；PR 幅值误差 0.03%<5%；P&O 收敛 67.5V∈68±1；保护码 0x1/0x4；状态机 MPPT_RUN→FAULT→复位） |
| 分析口径 Python 测试 | `python python/tests/test_metrics.py` | **7 PASS / 0 FAIL**（THD 合成信号 11.18% 精确；40kHz 簇；HP 纹波；LC 判别 −36.5dB；df=5Hz） |
| Python↔MATLAB 交叉验证 | 同合成信号 | THD 11.1803% vs 11.18%、sw40k 0.2000 vs 0.2000、ripple_pp 0.5706 vs 0.571 —— **一致** ✅ |
| 稳定性（S3） | 开环 Bode + 闭环极点（含 1.5 拍延时） | 相位裕度 **46.9° ≥ 30°**，闭环稳定（max pole 0.988<1）✅ |
| MPPT（S6） | 3 功率点 | η = 99.94/99.91/99.92% ✅ |

## 四、仿真核心结果（S4：三功率点 L vs LC）

| 功率点 | 结构 | THD(2–50次) | 纹波峰峰值(>5kHz) | 40kHz 簇占基波 |
|---|---|---|---|---|
| 35% (70W) | L | 23.5% | 1.77 A | 8.19% |
| 35% (70W) | LC | 26.1% | **0.067 A** | **0.013%** |
| 65% (130W) | L | 11.9% | 1.87 A | 4.54% |
| 65% (130W) | LC | 13.4% | **0.069 A** | **0.007%** |
| 90% (180W) | L | 9.7% | 1.81 A | 3.35% |
| 90% (180W) | LC | 10.3% | **0.070 A** | **0.005%** |

与方案 6.3 的预期完全一致：**LC 对 40 kHz 开关纹波抑制约 −28.6 dB，但 THD 因低次谐波经谐振反而略高 0.6–2.6 个百分点**——这正是课题要用数据说明的结论①，两类指标必须分开报告。

## 五、已知限制（如实记录）

1. **Simulink 模型**：已生成框架与参数配置；R2026b 取消经典 SPS 库（powerlib），需用 ee_lib 原生库在 GUI 中完成连线（脚本内已附逐步注释）；FFT 分析走 thd_metrics.m 脚本口径（R2026b 无 powergui）。
2. **thd_metrics.m 的 ripple_pp**：因本机无 Signal Processing Toolbox，用 FFT 谱零化高通替代 4 阶 Butterworth，实测差异 <2%（0.5706 vs 0.571）；THD 与 40kHz 口径完全一致。
3. **S5 调节时间**：RMS 包络 ±5% 带估计在仿真时长内约 1 s（P&O 10 Hz 扰动 + 电压环 10 Hz 带宽所致），实测应以示波器单次触发数据为准。
4. THD 低功率点偏高（35% 时 23%）：小电流下死区与采样误差占比增大，实测可经死区补偿标定改善；对比公平性不受影响（两结构同条件）。

## 六、验收结论

软件先行阶段 13 项要求中 11 项完成并有证据、1 项（Simulink 模型）框架就绪待 GUI 连线、1 项（样机/实验数据/视频）依定义待硬件。
所有可运行脚本均实际执行验证，C/Python 测试共 20 用例全部通过，Python↔MATLAB 口径交叉验证一致，参数与报告附录 A 逐项吻合。
**本阶段验收通过。**
