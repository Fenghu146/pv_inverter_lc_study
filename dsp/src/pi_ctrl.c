#include "pi_ctrl.h"

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

void pi_init(PiCtrl *pi, float kp, float ki, float ts,
             float out_min, float out_max)
{
    pi->kp = kp;
    pi->ki = ki;
    pi->ts = ts;
    pi->out_min = out_min;
    pi->out_max = out_max;
    pi_reset(pi);
}

void pi_reset(PiCtrl *pi)
{
    pi->integ = 0.0f;
    pi->out = 0.0f;
}

float pi_step(PiCtrl *pi, float err)
{
    float u_unsat = pi->kp * err + pi->integ;
    float u = clampf(u_unsat, pi->out_min, pi->out_max);

    /* 条件积分：饱和且误差仍推向饱和侧时冻结积分 */
    if (u == u_unsat || (u < u_unsat && err < 0.0f) || (u > u_unsat && err > 0.0f)) {
        pi->integ += pi->ki * err * pi->ts;
    }

    pi->out = u;
    return u;
}
