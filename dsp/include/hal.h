/**
 * hal.h — 硬件抽象层（HAL）
 *
 * 算法层只认识 SI 单位的测量值与 CMPA 计数值，不认识任何寄存器。
 * 本头文件定义板级必须提供的原语；PC 上用 hal_stub.c（仿真/自测），
 * 目标板用 hal_c2000.c（SysConfig + driverlib）。
 *
 * 通道分配（F28379D LaunchPad，与 hal_c2000.c 一致）：
 *   ADCA-A0  V_pv    PV 电压       分压 100V→3V
 *   ADCA-A1  I_pv    PV 电流       0.1 V/A，偏置 1.5 V
 *   ADCA-A2  V_dc    母线电压       分压 100V→3V
 *   ADCA-A3  V_g     PCC 电压       分压 100V→3V
 *   ADCB-B0  I_L     逆变侧电流     0.1 V/A，偏置 1.5 V   ← 电流环反馈
 *   ADCB-B1  I_g     并网电流       0.1 V/A，偏置 1.5 V   ← 保护/计量
 *   ADCC-C0  硬件过流镜像（CMPSS 输入，可选）
 *
 * PWM：
 *   EPWM1 A/B 腿 → A 桥臂（S1 上管 / S2 下管）
 *   EPWM2 A/B 腿 → B 桥臂（S3 上管 / S4 下管）
 *   两模块同一 20 kHz 增减载波、同一 TBPRD(2500)、同一相位。
 *   死区由 EPWM 数字比较子模块（DB）产生，RED 400 ns = 40 个 100 MHz 计数。
 *   硬件过流 → CMPSS → EPWM XBAR Trip Zone（OST），一次性锁存。
 */
#ifndef PV_INV_HAL_H
#define PV_INV_HAL_H

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float v_pv;   /* V */
    float i_pv;   /* A */
    float vdc;    /* V */
    float v_grid; /* V */
    float i_L;    /* A 逆变侧 */
    float i_g;    /* A 并网侧 */
} HalMeas;

/* ---- 初始化 ---- */
void hal_init(void);

/* ---- 测量 ---- */
/** 读一拍已标定的 SI 值。raw 由调用方缓存；本函数只做换算。 */
void hal_read_adc_raw(unsigned short raw[6]);
/** 把原始码换算成 SI（用已保存的零偏）。 */
void hal_raw_to_si(const unsigned short raw[6], HalMeas *m);

/* ---- 零偏标定 ---- */
/** 采样一次零偏（要求主回路无电流）。可反复调用做平均。 */
void hal_calibrate_offset(const unsigned short raw[6]);
/** 标定窗口结束，锁定零偏。 */
void hal_calibrate_finish(void);

/* ---- PWM ---- */
/** 写比较值；内部同时更新 EPWM1/2 的 CMPA。 */
void hal_pwm_apply(unsigned cmpa_a, unsigned cmpa_b);
/** 全局使能/封锁 PWM 输出（TZ 软件强制）。 */
void hal_pwm_enable(int on);
/** 继电器（并网接触器）合/分。 */
void hal_relay(int close);
/** 预充旁路 MOSFET/继电器。 */
void hal_precharge(int on);

/* ---- 硬件保护 ---- */
/** 非 0：CMPSS 触发过流 Trip（已锁存）。 */
int hal_trip_latched(void);
/** 清除 Trip 锁存（仅人工复位路径调用）。 */
void hal_clear_trip(void);

/* ---- 板级扩展（PC stub 提供空实现） ---- */
/** 原始码直写入口，仅供 PC 自测注入；板级为 no-op。 */
void hal_stub_set_raw(const unsigned short raw[6]);

/* ---- 看门狗与计数（板级实现可空） ---- */
void hal_watchdog_kick(void);

#ifdef __cplusplus
}
#endif

#endif /* PV_INV_HAL_H */
