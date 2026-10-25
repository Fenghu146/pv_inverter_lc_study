#include "pwm_mod.h"
#include "param.h"

#include <math.h>

static unsigned clamp_count(long v, unsigned lim)
{
    if (v < 0) {
        return 0u;
    }
    if ((unsigned)v > lim) {
        return lim;
    }
    return (unsigned)v;
}

void pwm_mod_init(PwmMod *p, unsigned tbprd, float duty_lim)
{
    p->tbprd = tbprd;
    p->duty_lim = duty_lim;
    p->m = 0.0f;
    p->cmpa_a = 0u;
    p->cmpa_b = 0u;
    p->enabled = 0;
}

void pwm_mod_step(PwmMod *p, float v_star, float vdc, int enable)
{
    float lim;
    float m;
    float da;
    float db;

    if (!enable || vdc < 10.0f) {
        /* 停机：双下管常通，v_ab = 0，无开关动作 */
        p->m = 0.0f;
        p->cmpa_a = 0u;
        p->cmpa_b = 0u;
        p->enabled = 0;
        return;
    }

    /* 调制比 m = v_star / vdc，限幅 ±duty_lim */
    lim = p->duty_lim;
    m = v_star / vdc;
    if (m > lim) {
        m = lim;
    } else if (m < -lim) {
        m = -lim;
    }

    /* d_A = (1+m)/2, d_B = (1-m)/2 ; CMPA = round(d·TBPRD) */
    da = 0.5f * (1.0f + m) * (float)p->tbprd;
    db = 0.5f * (1.0f - m) * (float)p->tbprd;

    p->m = m;
    p->cmpa_a = clamp_count((long)(da + 0.5f), p->tbprd);
    p->cmpa_b = clamp_count((long)(db + 0.5f), p->tbprd);
    p->enabled = 1;
}
