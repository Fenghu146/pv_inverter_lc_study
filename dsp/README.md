# dsp/README.md — 算法层 + 硬件抽象层

本目录是完整的 DSP 侧代码：**算法（与硬件无关）** + **HAL（唯一碰寄存器的地方）** + **CCS 工程骨架**。
算法层可在 PC 上编译并跑单元测试；HAL 有两个实现，编译期二选一。

## 分层

```
        ┌─────────────────────────────────────────┐
        │ app/main.c        C2000 入口，只调 app_isr │
        ├─────────────────────────────────────────┤
        │ app/app.c         ADC→算法→调制→HAL 编排   │  ← PC 可测
        ├─────────────────────────────────────────┤
        │ control_isr.c     PLL→保护→FSM→电压环→    │
        │                   PR→死区补偿             │  ← PC 可测
        │ pr/pi/sogi/protect/fsm/mppt_po/pwm_mod   │
        ├─────────────────────────────────────────┤
        │ hal.h  ← 接口                            │
        │   hal_stub.c    PC 替身（单元测试）       │
        │   hal_c2000.c   F28379D driverlib 实现    │  ← 唯一写寄存器处
        └─────────────────────────────────────────┘
```

算法层不知道任何寄存器、引脚、ADC 码。`hal_read_adc_raw()` 交出原始码，
`hal_raw_to_si()` 换算成 SI，算法只吃 SI 单位。

## 模块清单

| 文件 | 作用 |
|---|---|
| `include/param.h` | 全部参数集中定义，与 `params/params.json` 一一对应 |
| `include/control_isr.h` | 20 kHz 节拍接口；`CtrlMeas` / `CtrlOut` |
| `include/pwm_mod.h` | `v*` → `CMPA` 映射（单极性倍频） |
| `include/hal.h` | 硬件抽象层接口 + 通道分配表 |
| `include/app.h` | 应用层编排接口 |
| `src/control_isr.c` | 主算法节拍 |
| `src/pr_ctrl.c` | 准 PR（Tustin + 谐振频率预畸变） |
| `src/pi_ctrl.c` | 通用 PI + 条件积分抗饱和 |
| `src/sogi_pll.c` | SOGI-PLL |
| `src/protect.c` | 软件保护（过流/过欠压/交流范围/频率/失锁） |
| `src/fsm.c` | 状态机（含预充超时转 FAULT） |
| `src/mppt_po.c` | P&O MPPT |
| `src/pwm_mod.c` | 调制映射 + 停机语义 |
| `src/app.c` | 全链路编排 |
| `src/hal_stub.c` | PC 版 HAL |
| `src/hal_c2000.c` | F28379D 版 HAL（`__C2000__`） |
| `app/main.c` | C2000 入口（`__C2000__`） |
| `ccs/` | CCS 工程、SysConfig、链接脚本、构建脚本 |
| `tests/test_control.c` | PC 单元测试 |

## 编译与运行（PC）

```bash
gcc -std=c99 -Wall -Wextra -O2 -I include tests/test_control.c src/*.c -lm -o tests/test_control
./tests/test_control
```

`src/hal_c2000.c` 与 `app/main.c` 在 PC 上编译为空（受 `__C2000__` 保护），
所以 `src/*.c` 通配可以直接用。

**当前结果：35 条断言全部 PASS。**

覆盖：

| 组 | 内容 |
|---|---|
| (a) | SOGI-PLL 50 Hz 锁相，θ 稳态误差 0.0396 rad |
| (b) | 准 PR 跟踪 50 Hz 正弦，幅值误差 0.03% |
| (c) | P&O 收敛到 MPP ±1 V，V* 不越界 |
| (d) | 保护：11 A 软过流、96 V 过压、故障码互不串扰 |
| (e) | 状态机：正常序列→MPPT_RUN、故障锁存、人工复位 |
| (f) | 调制映射：m=0 时 50/50、m=0.5 时 75/25、过调制限幅、停机 CMPA=0 |
| (g) | 死区补偿：i_L>0 加正偏、i_L<0 加负偏、过零不补 |
| (h) | 电流环只认 i_L，不认 i_g |
| (i) | ADC 换算：V_pv/Vdc/I_L/I_g/双极性 V_g |
| (j) | 全链路 app_isr 从 INIT 走到 MPPT_RUN，CMPA 正确写入 |
| (k) | 预充超时转 FAULT，不绕过电压判据 |

## 编译（C2000）

见 [`ccs/README.md`](ccs/README.md)。C2000Ware 26.01 已安装，完整构建通过：

```
.\build.ps1  ->  build\pv_inverter.out (164 KB) + pv_inverter.hex (54 KB)
                 29 个源文件, 0 error
```

## 关键设计决定

### 1. 电流环反馈取 `i_L`，不是 `i_g`

`python/sim/inverter_sim.py:217`、Simulink 模型、方案 5.1 控制框图都用逆变侧 `i_L`。
LC 结构下 `i_g = i_L − i_C`，40 kHz 分量几乎全走电容；若反馈用 `i_g`，PR 会去追一个
已经被 LC 滤掉的量，从而推高调制并激发谐振 —— 会直接推翻结论③（LC 是否引入振荡）。

所以 `CtrlMeas` 里 `i_L` 与 `i_g` 是**两个独立字段**，硬件上也要两路独立采样。

### 2. PWM 映射语义

```
m = v_cmd / Vdc,  |m| ≤ 0.95
d_A = (1+m)/2,   d_B = (1-m)/2
CMPA_A = round(d_A · TBPRD),  CMPA_B = round(d_B · TBPRD)
```
TBPRD = 2500（100 MHz / (2·20 kHz)）。两腿同一增减载波、同相位，`v_ab` 的
基波按 2·f_sw 跳变（倍频）。

停机时 CMPA 全 0：双下管常通、`v_ab=0`、无开关动作。这是"有源短路"态，
电网电流经下管与 L_g 续流，不会经体二极管反灌抬升母线。

### 3. 死区补偿

与仿真完全同式：`v_cmd = v* + 2·fsw·td·Vdc·sign(i_L)`，
系数 `2·fsw·td = 0.016`，75 V 母线下补偿 1.2 V（≈1.6% 调制）。
`|i_L| < 0.05 A` 时不补，避免过零抖动。

### 4. 预充不再"闯关"

原实现是 `precharge_done || timer ≥ 100 ms` → SYNC，即母线没充起来也会带 PWM
合闸。现改为：**只认 `precharge_done`**，超时 3 s 转 `FAULT_PRECHARGE`。
这是安全项，不是优化。

## 移植注意事项

- 全浮点，无 Q 格式（FPU32）
- `sinf/cosf` 直接用 C2000 数学库
- 保护/FSM 故障码 `uint32_t`
- ISR 里只调 `app_isr()`，不写寄存器
- 中断优先级：EPWM1 周期中断（20 kHz）为唯一硬实时任务

## 待办（板级）

- [x] 装 C2000Ware（26.01 已装）
- [x] 板级初始化（手写 `board.c`，等价 SysConfig 生成物，免 GUI 依赖）
- [x] 完整构建出 `.out` / `.hex`
- [ ] 首次上电验证 PWM 死区（见 `ccs/README.md` 的上电顺序）
- [ ] CMPSS 阈值按实测调理增益校准
- [ ] 继电器/预充驱动电路（GPIO 直驱不够）
