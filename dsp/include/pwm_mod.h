/**
 * pwm_mod.h — 调制映射：桥臂电压指令 → 单极性倍频 SPWM 比较值
 *
 * 拓扑约定（与仿真 / Simulink 完全一致）：
 *   H 桥 A 腿 = EPWM1A/1B，B 腿 = EPWM2A/2B，两腿同一增减计数器、同一 TBPRD。
 *   v_ab = (d_A - d_B)·Vdc，要求 v_ab = v_star  ⇒  d_A = (1+m)/2, d_B = (1-m)/2，
 *   其中 m = v_star / Vdc。两腿互补对称，v_ab 的基波按 2·f_sw 次跳变（倍频）。
 *
 * 比较值语义（与 hal_c2000.c 的 AQ 配置严格对应）：
 *   TB 为增减计数，AQ 配置为
 *       CTR = 0   (up)   → SET      CTR = CMPA (up)   → CLEAR
 *       CTR = CMPA(down) → SET      CTR = 0   (down) → CLEAR
 *   上管导通时间 = 2·CMPA / (2·TBPRD) ⇒ duty = CMPA / TBPRD。
 *   故 CMPA = round(d · TBPRD)。
 *
 * 停机语义：
 *   pwm_enable = 0 时两腿 CMPA 全部强制为 0，上管常关、下管常通（经死区后），
 *   桥臂电压 v_ab = 0 且不再有开关动作 —— 这是"有源短路"态，电网电流经下管
 *   与 L_g 续流，不会经体二极管反灌抬升母线。
 */
#ifndef PV_INV_PWM_MOD_H
#define PV_INV_PWM_MOD_H

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    unsigned tbprd;    /* 三角载波周期计数值（20 kHz @ 100 MHz 增减计数 = 2500） */
    float    duty_lim; /* 调制比限幅，取 0.95 */
    float    m;        /* 本拍实际使用的调制比（已在 ±duty_lim 内） */
    unsigned cmpa_a;   /* A 腿比较值 */
    unsigned cmpa_b;   /* B 腿比较值 */
    int      enabled;  /* 1 = 正在调制，0 = 已强制零占空比 */
} PwmMod;

void pwm_mod_init(PwmMod *p, unsigned tbprd, float duty_lim);

/**
 * v_star  桥臂电压指令（V），已含死区补偿
 * vdc     直流母线电压（V）
 * enable  非 0 才输出调制；0 则强制停机
 */
void pwm_mod_step(PwmMod *p, float v_star, float vdc, int enable);

#ifdef __cplusplus
}
#endif

#endif /* PV_INV_PWM_MOD_H */
