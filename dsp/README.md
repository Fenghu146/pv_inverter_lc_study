# dsp/README.md — 硬件无关算法层说明

本目录存放纯 C99 算法层（无硬件寄存器、I/O、SPI、ADC 等），可直接在 PC 上编译运行单元测试，也可无缝移植到 TI C2000 F28379D 浮点核（FPU32）。

## 模块清单
- include/param.h —— 全部控制参数集中定义，数值与控制架构定稿完全一致。
- include/xxx.h —— 各模块头文件（结构体 + 接口）。
- src/xxx.c —— 实现。
- tests/test_control.c —— PC 主测试程序（覆盖所有功能点）。
- control_isr.h / control_isr.c —— 20 kHz 核心 ISR 编排（顺序：PLL → 保护 → FSM → 电压环 → 电流环），纯算法函数。

## 编译与运行
1. 确保有 C 编译器（gcc/clang/cl）。
2. 编译测试：
   ```bash
   gcc -std=c99 -Wall -O2 \
     tests/test_control.c \
     src/*.c \
     -lm -o test_control
   ./test_control
   ```
3. 编译命令已在最终报告给出。
4. 移植到 C2000：保持 ISR 顺序，FPU32 无 Q 格式转换，参数宏完全匹配。

## 移植注意事项（C2000）
- ISR 调用顺序固定：PLL → 保护 → FSM → VDC 1 kHz → 电流环。
- 全浮点，无 Q 格式（FPU32 即可）。
- 保护/FSM 状态机用 `uint32_t` 故障码。
- `sinf/cosf` 可用 C2000 库 `sin/cos`（浮点）。
- 限幅、条件积分、Tustin 预畸变公式全部保持不变。
- `vac_rms_last`、`pll_unlock_s` 等辅助字段已全部显式定义，无全局变量依赖。

## 与 params.json 对应关系（若有外部 JSON）
- GRID_F_NOM_HZ → 50
- GRID_U_RMS_NOM_V → 36
- SOGI_K → 1.41
- PLL_KP/Ki → 0.67/22
- PR_KP/KR/WC/W0 → 4.7/300/5/314.159265
- VDC_KP/Ki → 0.2/5
- MPPT_xxx → 0.5/62/75/0.8
- 保护阈值：OC_SOFT_A=10, OC_HARD_A=12, VDC_OV_V=95 等
- 状态机定时：OFFSET_CAL_MS=50 等

## 质量自检
- 数值：PR 离散化、PLL k=1.41、Ts=50 µs 均已验证。
- 单元测试覆盖：PLL 50 Hz 稳态、PR 跟踪、P&O 收敛、保护触发、状态机序列。
- 无动态分配、无硬件依赖、可 PC 编译运行。

## 后续
- 若需 SIL/HIL 移植，只需把 `control_isr.c` 里的 `CtrlMeas/CtrlOut` 映射到 DSP 寄存器即可。
