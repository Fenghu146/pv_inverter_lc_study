/**
 * param.h — 单相 H 桥光伏并网逆变器算法层参数（与控制架构定稿一致）
 *
 * 拓扑：PV → H 桥 → L / LC 耦合 → PCC
 * 目标：TI C2000 F28379D，全浮点（FPU32），本层无寄存器依赖。
 * 数值约定：电压 V、电流 A、功率 W、角频率 rad/s、时间 s、角度 rad。
 */
#ifndef PV_INV_PARAM_H
#define PV_INV_PARAM_H

#ifdef __cplusplus
extern "C" {
#endif

/* ---------- 采样 / 调度 ---------- */
#define CTRL_FS_HZ              (20000.0f)          /* 电流环 / SOGI-PLL ISR */
#define CTRL_TS_S               (50.0e-6f)          /* 1/20 kHz */
#define VDC_LOOP_DIV            (20u)               /* 直流电压环 1 kHz */
#define VDC_LOOP_TS_S           (0.001f)
#define MPPT_PERIOD_S           (0.100f)            /* P&O 100 ms */
#define MPPT_AVG_SAMPLES        (2000u)             /* 100 ms × 20 kHz */

/* ---------- 电网额定 ---------- */
#define GRID_F_NOM_HZ           (50.0f)
#define GRID_W0_RAD_S           (314.1592653589793f) /* 2π·50 */
#define GRID_U_RMS_NOM_V        (36.0f)
#define GRID_UM_V               (50.91168824543142f) /* 36·√2，PLL 归一化基准 */
#define TWO_PI                  (6.283185307179586f)

/* ---------- SOGI-PLL（20 kHz） ---------- */
#define SOGI_K                  (1.41f)
#define PLL_KP                  (0.67f)
#define PLL_KI                  (22.0f)
/* v_q / GRID_UM_V 进入 PI；输出为 Δω，叠加在 ω0 上 */
#define PLL_DW_LIM_RAD_S        (62.83185307179586f) /* ±10 Hz，抗饱和限幅 */

/* ---------- 电流环准 PR（20 kHz） ---------- */
/* G(s) = Kp + 2·Kr·ωc·s / (s² + 2·ωc·s + ω0²) */
#define PR_KP                   (4.7f)
#define PR_KR                   (300.0f)
#define PR_WC_RAD_S             (5.0f)
#define PR_W0_RAD_S             GRID_W0_RAD_S
#define MOD_DUTY_LIM            (0.95f)             /* 调制指令限幅 ±0.95·Vdc */
#define IREF_SIGN               (1.0f)              /* i_ref = I_amp* · sin(θ) */

/* ---------- 直流电压环 PI（1 kHz） ---------- */
#define VDC_KP                  (0.2f)
#define VDC_KI                  (5.0f)
#define IAMP_MIN_A              (0.0f)
#define IAMP_MAX_A              (10.0f)

/* ---------- P&O MPPT（100 ms） ---------- */
#define MPPT_DV_V               (0.5f)
#define MPPT_V_MIN_V            (62.0f)
#define MPPT_V_MAX_V            (75.0f)
#define MPPT_V_INIT_FRAC        (0.8f)              /* 初值 0.8·Voc */

/* ---------- 保护阈值 ---------- */
#define OC_SOFT_A               (10.0f)             /* 软件过流 */
#define OC_HARD_A               (12.0f)             /* 硬过流（比较器镜像量） */
#define VDC_OV_V                (95.0f)
#define VDC_UV_V                (58.0f)
#define VAC_RMS_MIN_V           (30.0f)
#define VAC_RMS_MAX_V           (42.0f)
#define FREQ_MIN_HZ             (49.0f)
#define FREQ_MAX_HZ             (51.0f)
#define PLL_LOCK_VQ_PU          (0.15f)             /* |v_q|/Um 超过则计失锁 */
#define PLL_UNLOCK_MS           (20.0f)             /* 连续超差时间 */
#define PROTECT_CONFIRM_MS      (2.0f)              /* 过流/母线电压确认 */

/* ---------- 状态机时序 ---------- */
#define OFFSET_CAL_MS           (50.0f)             /* 偏置校准窗口 */
#define GRID_OK_MS              (40.0f)             /* 电网合格持续 */
#define PRECHARGE_MS            (100.0f)            /* 预充典型时长（仅作参考/诊断） */
#define PRECHARGE_TIMEOUT_MS    (3000.0f)           /* 预充超时 → FAULT（不得绕过电压判据） */
#define SYNC_LOCK_MS            (40.0f)             /* PLL 锁定确认 */
#define CONNECT_DWELL_MS        (20.0f)             /* 合闸后电流建立 */

/* ---------- 调试模式默认 ---------- */
#define OPEN_LOOP_DUTY          (0.2f)
#define FIXED_I_AMP_A           (2.0f)

/* ---------- PWM 载波与时基 ---------- */
#define PWM_CLK_HZ              (100000000.0f)      /* EPWMCLK = SYSCLK/2 */
#define PWM_TBPRD              (5000u / 2u)         /* 增减计数：fsw = CLK/(2·TBPRD) = 20 kHz */
#define PWM_DUTY_LIM            (MOD_DUTY_LIM)      /* 0.95 */
#define DEADTIME_NS             (400.0f)
#define DEADTIME_COUNTS         ((unsigned)(DEADTIME_NS * 1e-9f * PWM_CLK_HZ + 0.5f))

/* ---------- 死区补偿（与 inverter_sim.py / Simulink 同式） ----------
 * 平均电压误差 v_err = -2·fsw·td·Vdc·sign(i_L)，控制侧反向补偿。
 * 系数 2·fsw·td = 0.016，乘 Vdc 得补偿伏特数。                                   */
#define DT_COMP_COEF            (2.0f * CTRL_FS_HZ * (DEADTIME_NS * 1e-9f))
#define DT_COMP_ENABLE          (1)

/* ---------- 采样调理（hal_raw_to_si 使用） ---------- */
#define ADC_BITS                (12)
#define ADC_FULL_SCALE          (4095.0f)
#define ADC_VREF_V              (3.0f)
/* 电压通道：100 V → 3 V，即分压比 33.333（V_pv / V_dc，单极性） */
#define SENSE_V_DIV             (100.0f / 3.0f)
/* 交流电压通道：±60 V → 1.5 V ± 1.5 V（双极性，需 1.5 V 偏置）
 * 36 Vrms 峰值 50.9 V，留 18% 余量 */
#define SENSE_VAC_DIV           (60.0f / 1.5f)
#define SENSE_VAC_OFFSET_V      (1.5f)
/* 电流通道：双向，±15 A 对应 0…3 V，中点 1.5 V，即 0.1 V/A */
#define SENSE_I_GAIN_A_PER_V    (10.0f)
/* 零偏默认值（未标定时的保守缺省，标定后覆盖） */
#define SENSE_I_OFFSET_V        (1.5f)

/* 故障码位（protect.h / fsm.h 共用） */
#define FAULT_NONE              (0u)
#define FAULT_OC_SOFT           (1u << 0)
#define FAULT_OC_HARD           (1u << 1)
#define FAULT_VDC_OV            (1u << 2)
#define FAULT_VDC_UV            (1u << 3)
#define FAULT_VAC_RANGE         (1u << 4)
#define FAULT_FREQ              (1u << 5)
#define FAULT_PLL_UNLOCK        (1u << 6)
#define FAULT_PRECHARGE         (1u << 7)           /* 预充超时/母线未建立 */

#ifdef __cplusplus
}
#endif

#endif /* PV_INV_PARAM_H */
