#include "sogi_pll.h"
#include "param.h"

#ifndef PV_INV_NO_LIBM
#include <math.h>
#endif

static float wrap_2pi(float th)
{
    while (th >= TWO_PI) {
        th -= TWO_PI;
    }
    while (th < 0.0f) {
        th += TWO_PI;
    }
    return th;
}

void sogi_pll_init(SogiPll *pll)
{
    pll->k = SOGI_K;
    pll->ts = CTRL_TS_S;
    pll->w0 = GRID_W0_RAD_S;
    pll->um = GRID_UM_V;
    pi_init(&pll->pi, PLL_KP, PLL_KI, CTRL_TS_S,
            -PLL_DW_LIM_RAD_S, PLL_DW_LIM_RAD_S);
    sogi_pll_reset(pll);
}

void sogi_pll_reset(SogiPll *pll)
{
    pll->v_alpha = 0.0f;
    pll->v_beta = 0.0f;
    pll->theta = 0.0f;
    pll->omega = pll->w0;
    pll->vd = 0.0f;
    pll->vq = 0.0f;
    pll->vq_pu = 0.0f;
    pll->locked = 0;
    pi_reset(&pll->pi);
}

void sogi_pll_step(SogiPll *pll, float v_grid)
{
    float e = v_grid - pll->v_alpha;
    float w = pll->omega;

    /* 前向欧拉 SOGI，增益 k=1.41 */
    pll->v_alpha += pll->ts * w * (pll->k * e - pll->v_beta);
    pll->v_beta  += pll->ts * w * pll->v_alpha;

    {
        float s = sinf(pll->theta);
        float c = cosf(pll->theta);
        pll->vd = pll->v_alpha * s - pll->v_beta * c;
        pll->vq = pll->v_alpha * c + pll->v_beta * s;
    }

    pll->vq_pu = pll->vq / pll->um;
    pll->omega = pll->w0 + pi_step(&pll->pi, pll->vq_pu);
    pll->theta = wrap_2pi(pll->theta + pll->omega * pll->ts);

    /* 锁定粗判：归一化 q 轴足够小（状态机再用时间确认） */
    pll->locked = (pll->vq_pu < PLL_LOCK_VQ_PU && pll->vq_pu > -PLL_LOCK_VQ_PU) ? 1 : 0;
}
