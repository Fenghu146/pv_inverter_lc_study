# 17 SITL 软件在环（固件 + 主电路闭环）

> 目标：在**没有硬件**的阶段，验证「`dsp/src` 里的固件代码 + 主电路模型」能不能从冷启动一路走到并网稳态，
> 并把 A0–A5（算法移植仿真）与真实固件之间的差距暴露出来。本文记录方法、命令、实测结果与已发现的问题。
>
> 更新：2026-11-03

## 1. 与 A0–A5 的分工

| 层 | 跑的是什么 | 用途 |
| --- | --- | --- |
| A0–A5（`python/run_tasks.py`、`python/run_canonical.py`） | Python 重写的算法与主电路 | 参数研究、扫描、与对方基线逐位对齐 |
| **SITL（本文）** | **`dsp/src/*.c` 原样编成动态库，逐拍调用真 `app_isr`** | 验证状态机、保护、零偏标定、PWM、PR 环、MPPT 是否真的能闭环 |
| Simulink（`matlab/PV_LC_models_R2023a`） | 开关级电路模型 | 器件级波形、谐振、纹波 |

SITL 的意义：A 系列只能证明「算法写得对」，SITL 才能证明「**固件跑起来没错**」。两者差分就是移植风险。

## 2. 结构

```
python/sitl.py ──ctypes──▶ dsp/sim/build/sitl.dll ──▶ dsp/src/*.c（app_isr）
      │                            ▲
      │  si[6] 物理量               │ 反算 12 位 ADC 码灌 hal_stub_set_raw()
      ▼                            │
  Plant（主电路）             ADC → SI → 零偏 → ctrl_isr → pwm_mod → CMPA
```

- 桥接层 `dsp/sim/sitl_bridge.c`：`sitl_reset(voc)` / `sitl_step(si[6], out[20])` / `sitl_request(debug_req, clear_fault)` / `sitl_tbprd()`。
  `si[6] = [v_pv, i_pv, v_dc, v_grid, i_L, i_g]`，输出含 CMPA_A/CMPA_B、状态机状态、故障字、PWM/继电器/预充使能、控制内部量。
  因为走的是真 `hal_read_adc_raw → hal_raw_to_si`，**采样量化、单位换算、零偏标定全在环内**。
- 主电路 `python/sitl.py:Plant`：PV（单二极管，`params.json` 的 `pv_model`）— C_dc — H 桥 — L —（LC 时并 C 串 R_d）— PCC — L_g — 电网；
  接线状态由固件输出的 `relay` / `precharge` 决定：**预充未使能且继电器未合 → PV 侧与母线完全断开**（这是物理事实，也是零偏标定成立的前提）。
- 两种功率级模型：
  - `--mode avg`：一拍内取平均 `v_ab = m·V_dc`，便宜，用于状态机/MPPT/保护闭环；
  - `--mode sw`：一拍再分 `--nsub` 个子步，用三角载波（周期 `2·TBPRD`）与 CMPA 比较得 ±V_dc，**能看到真实开关纹波**。
- 两个必须建模、否则结论会骗人的东西：
  - **死区电压误差** `v_err = −2·fsw·td·V_dc·sign(i_L)`（`2·fsw·td = 0.016`，即 75 V 下 1.2 V）。固件在 `control_isr.c:152` 用 `v_cmd = v_star + 0.016·V_dc·sign(i_L)` 反补；功率级不施加这一项，"补偿有没有用"在环里根本看不出来。
  - **指令延迟 1.5 拍**（1 拍计算 + 0.5 拍 PWM 装载），与 `engine.py` 的 `ctrl_delay_beats` 同口径。对 LC 谐振点的相位裕度影响很大，不能省（早期版本零延迟，`--delay-beats 0` 可复现）。

## 3. 怎么跑

```bash
python tools/sitl_build.py            # gcc 编出 dsp/sim/build/sitl.dll（源码变了会自动重编）
python python/sitl.py --struct L --mode avg --dur 2.0        # 单跑，看状态机与稳态
python python/sitl.py --struct LC --rd 1 --mode sw --nsub 40 --dur 1.2 --log-sub
python tools/sitl_matrix.py           # 四工况矩阵 → results/tables/SITL_core.csv
```

要点：

- SITL 会加载外部 DLL，**必须在可执行外部库的权限下运行**（沙箱内加载 DLL 会被拒）。
- `--log-sub`：按子步记录连续电流，用它算 THD/纹波。20 kHz 的采样点**分辨不出 20 kHz 开关纹波**（正好在奈奎斯特），不记连续波形就只能看到混叠后的假象。
- `--dt-scale N`：把「真实」死区误差放大 N 倍而不动固件补偿系数，用于验证补偿的有效性。
- `--delay-beats`、`--no-dt`、`--out`：延迟、关死区、落轨迹 CSV（23 列）。

## 4. 实测结果

### 4.1 冷启动到稳态（L，avg，2 s）

| 时刻 | 状态 | 说明 |
| --- | --- | --- |
| 0.000 s | OFFSET_CAL | 采样零偏标定（PV 与电网均已隔离） |
| 0.050 s | WAIT_GRID | 等电网电压/频率判据 |
| 0.090 s | PRECHARGE | 经 100 Ω/25 W 给 C_dc 充电，91 ms 到 58 V |
| 0.181 s | SYNC | PLL 锁相 |
| 0.221 s | CONNECT | 合继电器 |
| 0.241 s | MPPT_RUN | 进入并网稳态 |

末拍：`vdc = 74.55 V` 跟踪 `vdc_ref = 74.50 V`，`i_amp = 7.716 A`；末窗 200 ms：`I1 = 7.7116 A`、`amp_err = −0.05 %`、`phase = 2.81°`、`THD = 1.611 %`、`Idc = 0.0037 A`。
（avg 模式没有开关纹波，THD 只反映低频与死区项，不能当验收值。）

### 4.2 死区补偿有效性（L，avg，2 s，只改功率级的「真实」死区误差）

| `--dt-scale` | 含义 | THD |
| --- | --- | --- |
| 0 | 功率级无死区（理想） | 1.611 % |
| **1** | 与固件补偿系数一致（**完全补偿**） | **1.287 %** |
| 2 | 误差是补偿能力的两倍（只补一半） | 2.685 % |
| 3 | 只补三分之一 | 4.216 % |

结论：固件的死区补偿在闭环里**确实有效**——补偿系数与实际死区一致时 THD 比「无死区」还低（补偿顺带抵消了一部分其他不对称）；
一旦实际死区是假设值的 2 倍，THD 立刻翻倍。这条给 `DEADTIME_NS` 的选型留了余量判据：**td 估小了比不补更糟**。

### 4.3 L vs LC（开关级 + 连续波形，1.2 s，≈200 W，`results/tables/SITL_core.csv`）

| 结构 | R_d | I1 (A) | THD | HF(>2 kHz) | 40 kHz 簇 | 40 kHz 衰减比 |
| --- | --- | --- | --- | --- | --- | --- |
| L | — | 7.5800 | 3.731 % | 1.709 % | 0.09934 A | 1×（基准） |
| LC | 0 Ω | 7.5957 | 3.929 % | 1.207 % | 0.00082 A | **121.1×** |
| LC | 1 Ω | 7.5839 | 4.216 % | 0.952 % | 0.00175 A | **56.8×** |
| LC | 2.2 Ω | 7.5774 | 5.181 % | 0.928 % | 0.00359 A | **27.7×** |

与 A5 解析层的 40 kHz 衰减比对照（`results/tables/A5_core.csv`：314.8× / 61.4× / 28.4×）：

- R_d > 0 时**独立复现**得很好：56.8× vs 61.4×、27.7× vs 28.4×（差 8 % 与 2.5 %），两条完全不同的路径（解析阻抗模型 / 闭环开关模型）互证；
- R_d = 0 时 SITL 只测到 121×，低于解析的 315×——因为无阻尼时 40 kHz 分量已经掉到 0.0008 A，接近其他残余内容的量级，**不再是指数压制区**，这一格应以解析值为准。
- THD 反过来：LC 的 THD 比 L 高，且**随 R_d 增大而变差**（3.73 % → 3.93 % → 4.22 % → 5.18 %）。R_d 在压纹波与抬 THD 之间是明确的取舍，E7 定最终值时必须两栏一起看，不能只看纹波。
- HF（>2 kHz）则单调变好（1.709 % → 1.207 % → 0.952 % → 0.928 %），与「LC 抑制高频」一致。

这三条和 README 的结论 1、2 一致：**纹波与 THD 必须分开报告**，只报 THD 会得出「LC 更差」的错误结论。

## 5. SITL 发现的问题

### 5.1 固件缺陷（已修）：启动阶段被 VDC 欠压保护打死

`protect.c` 无条件判 `v_dc < VDC_UV_V (58 V)`，而母线从 0 V 起步 → **上电第一拍就进 FAULT(VDC_UV=8)**，预充永远走不完。

修法：`protect.h` 的 `ProtectIn` 增加 `int uv_mask`（0 = 正常检查，保持单元测试默认语义），`protect.c` 改为 `if (!in->uv_mask && over_for(...))`，
`control_isr.c` 在 `protect_step` 前设 `pin.uv_mask = (state == ST_INIT || ST_OFFSET_CAL || ST_WAIT_GRID || ST_PRECHARGE)`。
改后 `dsp/tests/test_control.exe` 仍 `SUMMARY PASS (0 failed)`。

> 这条只有把真固件跑起来才会暴露：A 系列仿真里母线初值直接给 80 V，永远碰不到。

### 5.2 建模要求（已落实到 plant）：零偏标定期间 PV 必须真的断开

`hal_calibrate_offset()` 标定的是 `i_pv`（raw[1]）与 `i_g`（raw[5]）的零偏。早期 plant 让 PV 一直挂在母线上，`OFFSET_CAL` 期间 i_pv ≈ 2.9 A 被当成零偏吸收（`g_off → 1.79 V`），之后 i_L 读数整体偏 −2.9 A，并网瞬间电流发散到 117 A。

物理上：预充未使能、继电器未合时，PV 侧没有电流通路。plant 已按 `relay`/`precharge` 状态门控 PV 通路。**对硬件的启示**（写进 E 系列检查项）：零偏标定前必须确认预充旁路与主接触器都断开、PV 侧无漏流，并用示波器确认 `i_pv` 通道确实是 0，否则零偏会被光伏电流污染。

### 5.3 与 A5 的结论冲突（待硬件裁决）：LC 在 R_d = 0 时是否发散

- A5（`results/tables/A5_core.csv`）报：LC、R_d = 0、三个功率点全部发散（THD 95–379 %）。
- SITL（本文 4.3）在同一参数口径下：**LC、R_d = 0 不发散**，THD 3.93 %，40 kHz 衰减 121×。
- 复跑 A5 引擎（`engine.run_case("LC", fixed_P=130, comp="sat")`）看到的是一条**2.45–2.65 kHz、峰值 16 A 的极限环**（f_res ≈ 2.25 kHz），不是数值发散。

差异来源：两者跑的不是同一个控制器。A5 引擎的 PR 是「归一化到调制域的 `Kp_pr=0.0785 / Kr=4.0`」，且带电容电流前馈；固件的 PR 是 `params.json` 的 `current_pr_kp=4.7 / kr=300 / wc=5`（伏特域）。同一台 LC 无阻尼装置，前者在谐振点越过稳定边界，后者没有。

处理：**不急着改结论，也不删 R_d**。
1. BOM 保留 R_d 插座与 1 Ω / 2.2 Ω 两只（成本几元，插拔可换），措辞从「必装」调整为「默认装 1 Ω」；
2. E7 就是为这件事设计的实验（R_d = 0 vs 1 Ω 对比），**用实测裁决**；
3. 若 E7 证明 R_d = 0 确实稳定，仍建议保留 1 Ω：它把 HF 从 1.207 % 压到 0.952 %，代价是 THD +0.29 pp，属可接受的工程折中。

### 5.4 固件缺陷（已修）：故障一旦锁存就永远清不掉

`protect_clear()` 全仓只有 `protect_init()` 调用一次，`ProtectState.latched` 是只锁存位、没有清除路径。
`fsm` 收到 `clear_fault` 后确实把状态机打回 `ST_INIT`，但下一拍 `in.fault_code = prot.active` 仍是旧值，
状态机立刻又被 `take_fault()` 打回 `ST_FAULT` —— 现场表现就是**按复位没反应**。硬件侧同样：
`hal_clear_trip()` 从未被调用，CMPSS 的 Trip 锁存会让 `pwm_ok = pwm_enable && !trip` 恒为 0。

修复（2026-11-03）：

| 文件 | 改动 |
| --- | --- |
| `dsp/include/protect.h` | `ProtectState` 增 `uint32_t current`（本拍仍存在的条件，**不带确认时间、不锁存**）；声明 `int protect_try_clear(ProtectState *)` |
| `dsp/src/protect.c` | `protect_step()` 结尾先记 `p->current = now` 再 `p->latched \|= now`；`protect_try_clear()`：条件仍在（`current != FAULT_NONE`）返回 0 拒绝复位，否则 `protect_clear()` 并返回 1 |
| `dsp/src/control_isr.c` | `fsm_step()` 前后捕获状态：FAULT → INIT 时调 `protect_try_clear()`，**被拒绝就把状态机推回 FAULT**（防止"按着复位键硬闯故障"）；另把 `uv_mask` 加上 `ST_FAULT`，否则 FAULT 期间母线被放掉、欠压条件恒真，掉电故障永远清不掉 |
| `dsp/src/app.c` | FAULT → INIT 时调 `hal_clear_trip()`，同步释放硬件 Trip 锁存 |

单测 `dsp/tests/test_control.c` 新增 `test_fault_recovery`（[l]）固化三条语义：条件仍在拒绝复位、
条件消失允许复位并清锁存、复位后能从 INIT 重新走完启动序列到 `MPPT_RUN`。

### 5.5 固件缺陷（已修）：SOGI-PLL 环路阻尼只有 0.05

故障注入把电网频率阶跃 50 → 55 Hz 时，PLL 不仅捕获不到，电网回到 50 Hz 后频率估计**在 4.5 s 内
始终在 49.4–50.5 Hz 之间摆动、永不收敛**，于是 `WAIT_GRID ↔ SYNC` 反复重启，估计值还会漂到
51.4 Hz 越过 `FREQ_MAX` 而反复触发 FREQ 保护 —— 表现为"电网恢复了，逆变器自己也回不来"。

根因是整定：`pll->omega = w0 + pi_step(&pi, vq_pu)`，取 `vq_pu ≈ 0.5·Δθ` 线性化后

```
ωn = sqrt(0.5 · Ki) = 3.32 rad/s        ζ = 0.5 · Kp / (2·ωn) = 0.05
```

ζ = 0.05 意味着整定时间 4/(ζωn) ≈ 24 s。用探针 `.work/probe_pll_tune.py`（直接灌 si，不经主电路）
扫了三组：

| Kp / Ki | ωn (rad/s) | ζ | 电网回 50 Hz 后稳定时间 |
| --- | --- | --- | --- |
| 0.67 / 22（原） | 3.32 | 0.05 | **不收敛**（>4.5 s） |
| 9.3 / 22 | 3.32 | 0.70 | 1.10 s |
| 4.0 / 22 | 3.32 | 0.30 | 1.44 s |
| **6.0 / 6.0（采用）** | **1.73** | **0.87** | **0.63 s** |

已落盘：`dsp/include/param.h` 的 `PLL_KP 6.0 / PLL_KI 6.0`、`params/params.json` 的
`control.pll_pi_kp / pll_pi_ki`、`docs/12` §1 与 §8，`check_params.py` 回到 PASS 103。
`Kp 9.3` 那档虽然按 ζ=0.7 设计，但带宽高（噪声敏感）且实测并不更快；`6.0/6.0` 带宽降到 0.28 Hz、
阻尼够，兼顾电网畸变下的频率平滑。

## 6. 故障注入（保护与恢复）

`python/sitl_faults.py` 一个场景一套剧本：「正常运行 → 注入 → 保持 → 恢复条件 → 每 200 ms 试一次复位
→ 看能不能自己回到 `MPPT_RUN`」。注入都在**主电路侧**（Plant 的可编程量），不是直接改状态机，
所以测的是"电网/母线真出事了，固件怎么反应"。复位按真实操作反复试：条件还在时 `protect_try_clear()`
会拒绝，这正是要验证的行为。

```bash
python python/sitl_faults.py                 # 全部 9 个场景 → results/tables/SITL_faults.csv
python python/sitl_faults.py --only F1,F5    # 只跑指定场景
```

`results/tables/SITL_faults.csv`，L / avg，2026-11-03（已含 PLL 重新整定）：

| 场景 | 注入内容 | 首帧 FAULT | 保护码 | 峰值 i_g | 恢复耗时 |
| --- | --- | --- | --- | --- | --- |
| F1 过流（信号级 14 A / 6 ms） | 采样注入 | 2.0 ms | OC_SOFT + OC_HARD | 18.9 A | 0.15 s |
| F9 电网反相（180° / 60 ms） | `ph_extra` | 27.2 ms | VDC_OV | 10.0 A | 1.15 s |
| F2 并网点短路（150 ms） | `grid_short` | 19.9 ms | VAC_RANGE | 9.5 A | 0.45 s |
| F3 PV 掉电（辐照度 → 0） | `pv_scale=0` | 30.0 ms | VDC_UV | 7.2 A | 0.80 s |
| F4 电网跌落（36 → 18 V） | `grid_scale` | 19.9 ms | VAC_RANGE | 8.5 A | 0.60 s |
| F5 频率阶跃（50 → 55 Hz） | `grid_freq` | 29.4 ms | PLL_UNLOCK | 7.8 A | 0.77 s |
| F6 相位跳变（每 25 ms 60°） | `ph_extra` | 20.5 ms | PLL_UNLOCK | 8.1 A | 0.75 s |
| F7 硬件 Trip（CMPSS 锁存） | `sitl_set_trip()` | 0.1 ms | （无 FAULT，直接封锁） | 0.4 A | 0.30 s |
| F8 预充超时（预充支路断开） | `pre_break` | 3.00 s | PRECHARGE | 0.0 A | 0.55 s |

恢复耗时 = 恢复条件到位/复位发送 → 状态机重新走到 `MPPT_RUN`（含完整的
OFFSET_CAL → WAIT_GRID → PRECHARGE → SYNC → CONNECT 重启序列）。逐拍轨迹在
`.work/fault_traces/<场景>.csv`（不入库）。

结论与工程含义：

1. **软件保护链是通的**：过流 2.0 ms 动作（`OC_SOFT + OC_HARD` 同时置位）、掉电 30 ms、电网异常
   20–30 ms，动作后 `pwm_enable=0`、`relay_close=0`，并网电流立刻归零。掉电场景母线最低 57.02 V，
   只比 `VDC_UV_V 58` 低 1 V —— 说明确认时间 2 ms 没放过真跌落，也没被噪声误触发。
2. **硬件 Trip 走的是另一条路**：F7 全程没有进入 `ST_FAULT`（`app.c` 里 `pwm_ok = pwm_enable && !trip`
   在状态机之外直接封锁 PWM、`hal_relay(relay && !trip)` 同时断开继电器），0.1 ms 内生效；
   软件状态机在下一拍才看到电网/母线异常。两条路径互补，**硬件保护不依赖固件是否活着**。
3. **恢复依赖"条件消失 + 显式复位"**：所有 9 个场景在恢复条件到位、复位被接受后都能自己重新走完
   启动序列。复位被拒绝的场景（例如短路还没排除就按复位）会留在 FAULT —— 这是设计意图，不是 bug。
4. **E7/E9/E10 的实验准备**：F3/F4/F5 三档正好对应技术文件的"掉电、电网异常、动稳态"要求；
   建议实测时用同样的注入量（辐照→0、36→18 V、+5 Hz），复现同一张表的列。
5. **预充余量偏薄（设计风险）**：`R_pre = 100 Ω` + `Voc = 90 V` 时预充平衡点约 58 V，刚好压在
   `VDC_UV_V` 上；`PRECHARGE → SYNC` 又以"母线 ≥ 58 V"为条件。如果预充尚未到顶就先断开 PV
   （或接触器时序没配好），会立刻欠压跳闸。原理图阶段需要把"预充完成判据"（建议 ≥ 62 V 或
   延时确认）和接触器时序一起定稿，见 [docs/16](16_EDA原理图任务书.md)。

## 7. 局限（写清楚，避免被当成验收数据）

1. `avg` 模式没有开关纹波，THD 只反映低频与死区；要纹波必须 `--mode sw --log-sub`。
2. 主电路无寄生参数（只有 `Rf = 0.05 Ω`、`Rg = 0.1 Ω`），无传感器噪声、无 ADC 抖动、无温漂；真实样机的 THD 会更高。
3. MPPT 一直在小步扰动，稳态窗口内 `i_amp` 仍有漂移，短窗 THD 的重复性约 ±0.5 pp（4.3 的 LC 两档之间就差在这个量级，不要过度解读单格）。
4. 1.2 s 的算例只覆盖启动 + 0.7 s 稳态，不含辐照阶跃（E8）；故障注入场景在 §6，同样是 L/avg、
   `Vdc0 = 0` 起步，未覆盖 LC 结构下的故障行为（LC 的故障场景留给硬件阶段复核）。
5. 死区在 `sw` 模式里按「一拍平均偏差」施加，不是逐个开关沿插入 blanking；对 THD 量级够用，对单次换流细节不够。
6. 故障注入是"模型级注入"：`grid_scale`/`ph_extra` 等直接改理想电网，没有并网点阻抗、没有电网谐波、
   没有传感器噪声与延迟抖动；真实保护的动作时间会因噪声确认时间而略有差异。

## 8. 下一步

- 把 E 系列（E1–E10）的实测数据反标 `Plant`（寄生电阻、传感器增益、实际 td、电网内阻），
  让 SITL 从「能闭环」走向「能预测」；
- 在 LC 结构上重复 §6 的故障注入（尤其 R_d 档位对谐振的影响），硬件到位后与 E7 同台对照；
- 把故障注入的注入量固化成示波器/电源脚本（辐照→0、36→18 V、+5 Hz），让 E 系列能一键复现 §6 的表。

## 9. 门禁（对固件改动的保护）

本节的两条固件修复都已进 `tools/verify_all.py`：

- **V7（SITL 闭环冒烟）**：编出 `sitl.dll` 后跑 0.8 s，要求状态机到 `MPPT_RUN`、无故障；
- **V8（故障注入）**：跑 F1/F3/F7 三个场景，要求保护动作且复位后恢复。

```bash
python tools/verify_all.py            # V1–V8，实测 PASS 8 / FAIL 0（约 8 s）
python tools/verify_all.py --quick    # 跳过 V1/V5/V7/V8
```
