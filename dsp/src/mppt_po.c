#include "mppt_po.h"
#include "param.h"

static float clampf(float x, float lo, float hi)
{
    if (x < lo) {
        return lo;
    }
    if (x > hi) {
        return hi;
    }
    return x;
}

void mppt_init(MpptPo *m, float voc)
{
    m->v_min = MPPT_V_MIN_V;
    m->v_max = MPPT_V_MAX_V;
    m->dv = MPPT_DV_V;
    mppt_reset(m, voc);
}

void mppt_reset(MpptPo *m, float voc)
{
    m->v_ref = clampf(MPPT_V_INIT_FRAC * voc, m->v_min, m->v_max);
    m->p_prev = 0.0f;
    m->v_prev = m->v_ref;
    m->dir = 1;
    m->inited = 0;
}

float mppt_step(MpptPo *m, float v_avg, float p_avg)
{
    float dp;
    float dv;

    if (!m->inited) {
        m->p_prev = p_avg;
        m->v_prev = v_avg;
        m->inited = 1;
        return m->v_ref;
    }

    dp = p_avg - m->p_prev;
    dv = v_avg - m->v_prev;

    /* 经典 P&O：功率升则保持电压扰动方向，否则反向 */
    if (dp > 0.0f) {
        m->dir = (dv >= 0.0f) ? 1 : -1;
    } else if (dp < 0.0f) {
        m->dir = (dv >= 0.0f) ? -1 : 1;
    }

    m->v_ref = clampf(m->v_ref + (float)m->dir * m->dv, m->v_min, m->v_max);
    m->p_prev = p_avg;
    m->v_prev = v_avg;
    return m->v_ref;
}
