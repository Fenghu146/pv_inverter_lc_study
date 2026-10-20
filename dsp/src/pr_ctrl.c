#include "pr_ctrl.h"
#include "param.h"

#include <math.h>

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

void pr_init(PrCtrl *pr)
{
    /* k = ω0 / tan(ω0·Ts/2)，把离散谐振极点预畸变到 50 Hz */
    const float w0 = PR_W0_RAD_S;
    const float wc = PR_WC_RAD_S;
    const float ts = CTRL_TS_S;
    const float k = w0 / tanf(w0 * ts * 0.5f);
    const float k2 = k * k;
    const float w02 = w0 * w0;

    pr->kp = PR_KP;
    pr->a0 = k2 + 2.0f * wc * k + w02;
    pr->a1 = -2.0f * k2 + 2.0f * w02;
    pr->a2 = k2 - 2.0f * wc * k + w02;
    pr->b0 = 2.0f * PR_KR * wc * k;
    pr->b2 = -pr->b0;
    pr_reset(pr);
}

void pr_reset(PrCtrl *pr)
{
    pr->x1 = 0.0f;
    pr->x2 = 0.0f;
    pr->y1 = 0.0f;
    pr->y2 = 0.0f;
    pr->y = 0.0f;
    pr->u = 0.0f;
}

float pr_step(PrCtrl *pr, float err, float v_ff, float vdc)
{
    float lim;
    float y;

    /* y[n] = (b0·x[n] + b2·x[n-2] - a1·y[n-1] - a2·y[n-2]) / a0 */
    y = (pr->b0 * err + pr->b2 * pr->x2
         - pr->a1 * pr->y1 - pr->a2 * pr->y2) / pr->a0;

    pr->x2 = pr->x1;
    pr->x1 = err;
    pr->y2 = pr->y1;
    pr->y1 = y;
    pr->y = y;

    lim = MOD_DUTY_LIM * vdc;
    if (lim < 0.0f) {
        lim = 0.0f;
    }
    pr->u = clampf(pr->kp * err + y + v_ff, -lim, lim);
    return pr->u;
}
