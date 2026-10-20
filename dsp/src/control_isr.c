#include "control_isr.h"
#include "param.h"

#include <math.h>

void ctrl_init(CtrlContext *c, float voc)
{
    sogi_pll_init(&c->pll);
    pr_init(&c->pr);
    pi_init(&c->vdc_pi, VDC_KP, VDC_KI, VDC_LOOP_TS_S, IAMP_MIN_A, IAMP_MAX_A);
    mppt_init(&c->mppt, voc);
    protect_init(&c->prot);
    fsm_init(&c->fsm);

    c->vdc_ref = c->mppt.v_ref;
    c->i_amp = 0.0f;
    c->vdc_div = 0u;
    c->mppt_n = 0u;
    c->p_acc = 0.0f;
    c->v_acc = 0.0f;
    c->vac_acc = 0.0f;
    c->vac_rms_last = 0.0f;
    c->vac_n = 0u;
    c->pll_unlock_s = 0.0f;
    c->pwm_enable = 0;
    c->relay_close = 0;
    c->v_star = 0.0f;
    c->i_ref = 0.0f;
}

void ctrl_isr(CtrlContext *c, const CtrlMeas *m, CtrlOut *o)
{
    ProtectIn pin;
    FsmIn fin;
    float vac_rms;
    float freq;
    float i_hard;
    int rms_ready;

    sogi_pll_step(&c->pll, m->v_grid);

    /* 一个工频周期的 v² 均值 → rms。m->vac_rms ≥ 0 时改用调用方给出的值。 */
    c->vac_acc += m->v_grid * m->v_grid;
    c->vac_n++;
    if (c->vac_n >= (unsigned)(CTRL_FS_HZ / GRID_F_NOM_HZ)) {
        c->vac_rms_last = sqrtf(c->vac_acc / (float)c->vac_n);
        c->vac_acc = 0.0f;
        c->vac_n = 0u;
    }
    rms_ready = (c->vac_rms_last > 0.0f) ? 1 : 0;
    if (m->vac_rms >= 0.0f) {
        vac_rms = m->vac_rms;
        rms_ready = 1;
    } else if (rms_ready) {
        vac_rms = c->vac_rms_last;
    } else {
        vac_rms = GRID_U_RMS_NOM_V; /* 第一周期未结束，不拿半窗判范围 */
    }

    freq = c->pll.omega / TWO_PI;
    i_hard = (m->i_hard < 0.0f) ? fabsf(m->i_grid) : m->i_hard;

    /* |v_q|/U_m 连续超差 PLL_UNLOCK_MS 记为失锁 */
    if (c->pll.vq_pu > PLL_LOCK_VQ_PU || c->pll.vq_pu < -PLL_LOCK_VQ_PU) {
        c->pll_unlock_s += CTRL_TS_S;
        if (c->pll_unlock_s > 1.0f) {
            c->pll_unlock_s = 1.0f;
        }
    } else {
        c->pll_unlock_s = 0.0f;
    }

    pin.i_g = m->i_grid;
    pin.i_hard = i_hard;
    pin.vdc = m->vdc;
    pin.vac_rms = vac_rms;
    pin.freq_hz = freq;
    pin.pll_unlocked = (c->pll_unlock_s >= PLL_UNLOCK_MS * 0.001f) &&
                       (c->fsm.state == ST_MPPT_RUN ||
                        c->fsm.state == ST_CONNECT ||
                        c->fsm.state == ST_FIXED_I);
    /* 电网范围在并网前也要看，但 PLL 未锁时频率会漂，WAIT_GRID 只用 rms */
    pin.grid_check_en = (c->fsm.state == ST_WAIT_GRID ||
                         c->fsm.state == ST_SYNC ||
                         c->fsm.state == ST_CONNECT ||
                         c->fsm.state == ST_MPPT_RUN ||
                         c->fsm.state == ST_FIXED_I) ? 1 : 0;
    /* WAIT_GRID / SYNC 阶段不把 PLL 未锁当故障，只作转移条件 */
    if (c->fsm.state == ST_WAIT_GRID || c->fsm.state == ST_SYNC) {
        pin.pll_unlocked = 0;
        pin.freq_hz = (c->pll.locked) ? freq : GRID_F_NOM_HZ;
    }

    protect_step(&c->prot, &pin, CTRL_TS_S);

    fin.grid_ok = (vac_rms >= VAC_RMS_MIN_V && vac_rms <= VAC_RMS_MAX_V &&
                   freq >= FREQ_MIN_HZ && freq <= FREQ_MAX_HZ) ? 1 : 0;
    if (!rms_ready && m->vac_rms < 0.0f) {
        fin.grid_ok = 0; /* 第一周期 rms 未完成 */
    }
    fin.pll_locked = c->pll.locked;
    fin.precharge_done = (m->vdc >= VDC_UV_V) ? 1 : 0;
    fin.fault_code = (int)c->prot.active;
    fin.debug_req = m->debug_req;
    fin.clear_fault = m->clear_fault;
    fsm_step(&c->fsm, &fin, CTRL_TS_S);

    /* 电压外环 1 kHz：MPPT_RUN 跟踪 Vdc*，FIXED_I 不用 */
    c->vdc_div++;
    if (c->vdc_div >= VDC_LOOP_DIV) {
        c->vdc_div = 0u;
        if (c->fsm.state == ST_MPPT_RUN && c->fsm.pwm_enable) {
            /* 母线高于给定 → 加大并网电流把能量送出 */
            c->i_amp = pi_step(&c->vdc_pi, m->vdc - c->vdc_ref);
        } else if (c->fsm.state == ST_FIXED_I) {
            c->i_amp = FIXED_I_AMP_A;
        } else if (c->fsm.state == ST_CONNECT) {
            /* 合闸暂态给一个小电流，电压环从下一拍开始真正调节 */
            c->i_amp = 0.5f;
        } else {
            pi_reset(&c->vdc_pi);
            c->i_amp = 0.0f;
        }
    }

    if (c->fsm.pwm_enable &&
        (c->fsm.state == ST_CONNECT || c->fsm.state == ST_MPPT_RUN ||
         c->fsm.state == ST_FIXED_I)) {
        float err;
        c->i_ref = c->i_amp * sinf(c->pll.theta);
        err = c->i_ref - m->i_grid;
        c->v_star = pr_step(&c->pr, err, m->v_grid, m->vdc);
    } else if (c->fsm.state == ST_OPEN_LOOP && c->fsm.pwm_enable) {
        pr_reset(&c->pr);
        c->i_ref = 0.0f;
        c->v_star = OPEN_LOOP_DUTY * m->vdc * sinf(c->pll.theta);
    } else {
        pr_reset(&c->pr);
        c->i_ref = 0.0f;
        c->v_star = 0.0f;
    }

    /* P&O：仅 MPPT_RUN，100 ms 平均功率 */
    if (c->fsm.state == ST_MPPT_RUN) {
        c->p_acc += m->v_pv * m->i_pv;
        c->v_acc += m->v_pv;
        c->mppt_n++;
        if (c->mppt_n >= MPPT_AVG_SAMPLES) {
            float p_avg = c->p_acc / (float)c->mppt_n;
            float v_avg = c->v_acc / (float)c->mppt_n;
            c->vdc_ref = mppt_step(&c->mppt, v_avg, p_avg);
            c->p_acc = 0.0f;
            c->v_acc = 0.0f;
            c->mppt_n = 0u;
        }
    } else {
        c->p_acc = 0.0f;
        c->v_acc = 0.0f;
        c->mppt_n = 0u;
    }

    c->pwm_enable = c->fsm.pwm_enable;
    c->relay_close = c->fsm.relay_close;

    if (o) {
        o->v_star = c->v_star;
        o->i_ref = c->i_ref;
        o->i_amp = c->i_amp;
        o->vdc_ref = c->vdc_ref;
        o->theta = c->pll.theta;
        o->omega = c->pll.omega;
        o->pwm_enable = c->pwm_enable;
        o->relay_close = c->relay_close;
        o->state = c->fsm.state;
        o->fault_code = c->fsm.fault_code ? c->fsm.fault_code : c->prot.active;
    }
}
