/**
 * sogi_pll.h — SOGI-PLL（20 kHz）
 *
 * SOGI（前向欧拉，ω 为 PLL 估计角频率）：
 *   e  = v_g - v_alpha
 *   v_alpha += Ts·ω·(k·e - v_beta)
 *   v_beta  += Ts·ω·v_alpha
 * Park（θ 为电网角，sin(θ) 与 v_g 同相）：
 *   v_d =  v_alpha·sin(θ) - v_beta·cos(θ)
 *   v_q =  v_alpha·cos(θ) + v_beta·sin(θ)
 * PI 输入为 v_q / U_m（U_m = 36·√2），输出 Δω，ω = ω0 + Δω，θ += ω·Ts。
 */
#ifndef PV_INV_SOGI_PLL_H
#define PV_INV_SOGI_PLL_H

#include "pi_ctrl.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float k;
    float ts;
    float w0;
    float um;
    float v_alpha;
    float v_beta;
    float theta;
    float omega;
    float vd;
    float vq;
    float vq_pu;
    int   locked;
    PiCtrl pi;
} SogiPll;

void sogi_pll_init(SogiPll *pll);
void sogi_pll_reset(SogiPll *pll);
void sogi_pll_step(SogiPll *pll, float v_grid);

#ifdef __cplusplus
}
#endif

#endif
