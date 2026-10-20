/**
 * pr_ctrl.h — 准 PR 电流调节器 + 电网电压前馈 + 调制限幅
 *
 * 连续：G(s) = Kp + 2·Kr·ωc·s / (s² + 2·ωc·s + ω0²)
 * Tustin + 谐振频率预畸变（ω0' 用 k_pre = ω0 / tan(ω0·Ts/2)）：
 *   a0 = k² + 2·ωc·k + ω0²
 *   a1 = -2·k² + 2·ω0²
 *   a2 = k² - 2·ωc·k + ω0²
 *   b0 =  2·Kr·ωc·k ,  b1 = 0 ,  b2 = -b0
 *   y[n] = (b0·x[n] + b2·x[n-2] - a1·y[n-1] - a2·y[n-2]) / a0
 * 比例项在差分方程外：u = Kp·e + y_res + v_ff，再限幅到 ±lim·Vdc。
 */
#ifndef PV_INV_PR_CTRL_H
#define PV_INV_PR_CTRL_H

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float kp;
    float a0, a1, a2;
    float b0, b2;
    float x1, x2;   /* e[n-1], e[n-2] */
    float y1, y2;   /* y[n-1], y[n-2] */
    float y;        /* 谐振支路输出 */
    float u;        /* 限幅后的调制电压指令 */
} PrCtrl;

void pr_init(PrCtrl *pr);
void pr_reset(PrCtrl *pr);

/**
 * err      电流误差 i_ref - i_g
 * v_ff     电网电压前馈（通常为 v_g）
 * vdc      直流母线电压，用于 ±MOD_DUTY_LIM·Vdc
 * 返回限幅后的桥臂电压指令（V）
 */
float pr_step(PrCtrl *pr, float err, float v_ff, float vdc);

#ifdef __cplusplus
}
#endif

#endif
