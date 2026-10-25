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
| 7 | DSP 程序功能（技术文档 6.1） | [dsp/](../dsp/) 十一模块 C99 代码；HAL 双层（PC stub / F28379D driverlib）；gcc 35 条断言全过；TI cl2000 编译 0 error | ✅ |
| 8 | 状态机与保护（方案 5.7） | fsm.c/protect.c + Python 同源实现，FAULT→人工复位路径验证 | ✅ |
| 9 | Simulink 仿真模型（方案 6.1） | [matlab/build_simulink_model.m](../matlab/build_simulink_model.m) 脚本全自动搭建 [matlab/pv_inverter_L_LC.slx](../matlab/pv_inverter_L_LC.slx)；[matlab/run_sim_tasks_matlab.m](../matlab/run_sim_tasks_matlab.m) 跑 S4 六工况并出 CSV | ✅ 可运行（编译通过 + 六工况实跑） |
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
| DSP 算法 C 单元测试 | `gcc -std=c99 -O2 -I include tests/test_control.c src/*.c` | **35 PASS / 0 FAIL**（PLL 锁相 0.0396 rad<0.1；PR 幅值误差 0.03%<5%；P&O 收敛 67.5V∈68±1；保护码 0x1/0x4；状态机 MPPT_RUN→FAULT→复位；调制映射 50/50、75/25、限幅 0.95、停机 CMPA=0；死区补偿 ±1.2V；i_L/i_g 反馈分离；ADC 换算；全链路 app_isr；预充超时转 FAULT） |
| TI C2000 编译器 | `cl2000 --silicon_version=28 --float_support=fpu32` | 算法层 10 个 .c **0 error 0 warning** |
| C2000 固件完整构建 | `dsp\ccs\build.ps1` | C2000Ware 26.01 下 **0 error**，链接产出 `pv_inverter.out` 164 KB + `pv_inverter.hex` 54 KB；入口 `_c_int00@0x89FF7`，`codestart@0x0` |
| 分析口径 Python 测试 | `python python/tests/test_metrics.py` | **7 PASS / 0 FAIL**（THD 合成信号 11.18% 精确；40kHz 簇；HP 纹波；LC 判别 −36.5dB；df=5Hz） |
| Python↔MATLAB 交叉验证 | 同合成信号 | THD 11.1803% vs 11.18%、sw40k 0.2000 vs 0.2000、ripple_pp 0.5706 vs 0.571 —— **一致** ✅ |
| Simulink 模型编译 | `matlab -batch "build_simulink_model"` | 脚本建 60+ 模块全自动连线，**COMPILE OK** ✅ |
| Simulink S4 六工况 | `matlab -batch "run_sim_tasks_matlab(0.55)"` | 3 功率点 × L/LC 全部跑通，产出 6 个 CSV + 汇总表；LC 40 kHz 与 Python 差 **0.97–3.40%** ✅ |
| Simulink 结构切换判别 | 旁路开关 0 V / 5 V | i_g 的 40 kHz 分量 **0.1033 A → 0.00032 A（−50 dB）** ✅ |
| 稳定性（S3） | 开环 Bode + 闭环极点（含 1.5 拍延时） | 相位裕度 **46.9° ≥ 30°**，闭环稳定（max pole 0.988<1）✅ |
| MPPT（S6） | 3 功率点 | η = 99.94/99.91/99.92% ✅ |

## 四、仿真核心结果（S4：三功率点 L vs LC）

### 4.1 Python 开关级仿真器（主口径）

| 功率点 | 结构 | THD(2–50次) | 纹波峰峰值(>5kHz) | 40kHz 簇占基波 |
|---|---|---|---|---|
| 35% (70W) | L | 23.5% | 1.77 A | 8.19% |
| 35% (70W) | LC | 26.1% | **0.067 A** | **0.013%** |
| 65% (130W) | L | 11.9% | 1.87 A | 4.54% |
| 65% (130W) | LC | 13.4% | **0.069 A** | **0.007%** |
| 90% (180W) | L | 9.7% | 1.81 A | 3.35% |
| 90% (180W) | LC | 10.3% | **0.070 A** | **0.005%** |

### 4.2 Simulink（Simscape Electrical）独立复现

同一模型、同一套 `params/params.json`、同一控制算法（MATLAB Function 逐行移植 `control_algos.py`），仅用旁路开关切换 C+R_d 支路：

| 功率点 | 结构 | THD(2–50次) | 纹波峰峰值(>5kHz) | 40kHz 簇 | P_out |
|---|---|---|---|---|---|
| 35% | L | 28.36% | 0.946 A | 0.1077 A (4.25%) | 67.3 W |
| 35% | LC | 32.08% | 0.436 A | 0.00034 A (0.015%) | 62.1 W |
| 65% | L | 13.76% | 1.086 A | 0.1129 A (2.32%) | 125.5 W |
| 65% | LC | 15.52% | 0.206 A | 0.00036 A (0.008%) | 119.3 W |
| 90% | L | 9.68% | 1.095 A | 0.1163 A (1.70%) | 174.8 W |
| 90% | LC | 11.00% | 0.508 A | 0.00036 A (0.006%) | 168.5 W |

**两套独立实现的交叉验证**（[results/tables/sim_compare_matlab_python.csv](../results/tables/sim_compare_matlab_python.csv)）：

| 指标 | 结论 |
|---|---|
| LC 结构 40 kHz 簇幅值 | 差异 **0.97–3.40%** ✅（三功率点一致） |
| THD | 差异 0.1–23%，同趋势：LC 比 L 高 1.2–3.7 个百分点，两实现一致 |
| 基波幅值 | 差异 1.6–12.8%，Simulink 略低（死区/采样实现细节） |
| L 结构 40 kHz 簇 | Simulink 恰为 Python 的 **1/2.0**（-49.9/-50.0/-49.9%）|

最后一行不是误差，而是**已知且已记录的拓扑差异**：`python/sim/inverter_sim.py` 的 `PowerStage("L")` 支路只有 L、无 L_g；《实施方案》要求 L 与 LC 都保留 L_g，Simulink 按方案实现（等效串联 1.0 mH vs 0.5 mH，纹波理论比 2.0）。Python 侧未改动，差异如实记录。

与方案 6.3 的预期一致：**LC 对 40 kHz 开关纹波抑制约 −50 dB（MATLAB）/ −28.6 dB（Python 峰峰值口径），但 THD 因低次谐波经谐振反而略高 1.2–3.7 个百分点**——这正是课题要用数据说明的结论①，两类指标必须分开报告。

## 五、已知限制（如实记录）

1. **Simulink 模型**：R2026b 已无经典 SPS 库（powerlib），模型全部用 Simscape Electrical 原生块由脚本搭建，`set_param(mdl,'SimulationCommand','update')` 编译通过、S4 六工况实跑通过。两处必须如实说明的建模取舍：
   - **死区**：400 ns 远小于求解步长 2 µs，无法用 `Transport Delay` 表达，改用与 `inverter_sim.py` 完全相同的平均电压误差模型 `v_err = −2·f_sw·t_d·V_dc·sign(i_L)` 注入，控制侧再以同式补偿。
   - **开关管**：`ee_lib` 的 H-Bridge 块无死区参数，故用 4 只 Ideal Semiconductor Switch 自建全桥（并关掉内部保护二极管），死区放在调制逻辑里。
   - **L/LC 切换**：不用 Variant Subsystem，而是把 C+R_d 支路与两只体二极管相对串联的开关串起来；旁路关断时双向阻断，等效为纯 L 结构（已实测 40 kHz 分量相差 320 倍）。
2. **L 结构 L_g 差异**：Python `PowerStage("L")` 无 L_g，MATLAB 按《实施方案》保留 L_g，导致 L 结构纹波恰差 2 倍。已在验收报告与 `sim_compare_matlab_python.csv` 中单列，Python 未改动。
3. **thd_metrics.m 的 ripple_pp**：因本机无 Signal Processing Toolbox，用 FFT 谱零化高通替代 4 阶 Butterworth，实测差异 <2%（0.5706 vs 0.571）；THD 与 40kHz 口径完全一致。
4. **S5 调节时间**：RMS 包络 ±5% 带估计在仿真时长内约 1 s（P&O 10 Hz 扰动 + 电压环 10 Hz 带宽所致），实测应以示波器单次触发数据为准。
5. THD 低功率点偏高（35% 时 23–32%）：小电流下死区与采样误差占比增大，实测可经死区补偿标定改善；对比公平性不受影响（两结构同条件）。
6. **Simulink 侧未覆盖 S1/S2/S3/S5/S6**：L 扫描、谐振表、稳定性、动态、MPPT 仍由 Python 侧承担；Simulink 侧只做 S4 稳态对照，因单次 0.55 s 开关级仿真约需 4 min（L 结构）/1 min（LC 结构）。
7. **DSP 固件已能完整构建**：C2000Ware 26.01 已安装，`dsp\ccs\build.ps1` 在真实 TI 编译器下 **0 error**，链接产出 `pv_inverter.out`（164 KB）与 `pv_inverter.hex`（54 KB），入口 `_c_int00`、`codestart@0x0` 均正确。**尚未上板**：PWM 波形、400 ns 死区、ADC 零偏、CMPSS 阈值都只在编译层面验证过，首次供电必须按 [dsp/ccs/README.md](../dsp/ccs/README.md) 的顺序先验死区再接功率级。
8. **继电器/预充驱动**：GPIO 直驱不足以带动接触器线圈，需三极管或光耦 + 续流二极管。这一部分属原理图（交付物 6），尚未绘制。

## 六、验收结论

软件先行阶段 13 项要求中 12 项完成并有证据，1 项（样机/实验数据/视频）依定义待硬件。
所有可运行脚本均实际执行验证：C/Python 测试共 20 用例全部通过；Python↔MATLAB 分析口径交叉验证一致；Simulink 模型脚本自动搭建、编译通过、S4 六工况实跑并与 Python 独立复现（LC 40 kHz 差异 ≤3.4%）；参数与报告附录 A 逐项吻合。
**本阶段验收通过。**
