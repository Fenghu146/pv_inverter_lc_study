#include "app.h"
#include "hal.h"
#include "param.h"
#include "pwm_mod.h"

#include <string.h>

static PwmMod g_pwm;

void app_init(App *a, float voc)
{
    memset(a, 0, sizeof(*a));
    hal_init();
    pwm_mod_init(&g_pwm, PWM_TBPRD, PWM_DUTY_LIM);
    ctrl_init(&a->ctrl, voc);
    a->voc = voc;
    a->last_state = ST_INIT;
    hal_pwm_enable(0);
    hal_relay(0);
    hal_precharge(0);
}

void app_isr(App *a)
{
    int trip;
    int pwm_ok;
    InvState prev;
    CtrlMeas m;

    /* ---- 1. 采样 ---- */
    hal_read_adc_raw(a->raw);
    hal_raw_to_si(a->raw, &a->meas);

    /* ---- 2. OFFSET_CAL 期间累积零偏；离开该状态时锁定 ---- */
    prev = a->ctrl.fsm.state;
    if (prev == ST_OFFSET_CAL) {
        hal_calibrate_offset(a->raw);
    }

    /* ---- 3. 算法 ---- */
    m.v_grid      = a->meas.v_grid;
    m.i_L         = a->meas.i_L;
    m.i_grid      = a->meas.i_g;
    m.vdc         = a->meas.vdc;
    m.v_pv        = a->meas.v_pv;
    m.i_pv        = a->meas.i_pv;
    m.i_hard      = -1.0f;   /* 硬件过流走 CMPSS Trip，不在此处判 */
    m.vac_rms     = -1.0f;   /* 内部递推一个工频周期 */
    m.debug_req   = a->debug_req;
    m.clear_fault = a->clear_fault;
    m.voc         = a->voc;
    ctrl_isr(&a->ctrl, &m, &a->out);
    a->clear_fault = 0;
    if (a->out.state != ST_INIT) {
        a->debug_req = DBG_NONE;   /* 只在 INIT 接受一次 */
    }

    if (prev == ST_OFFSET_CAL && a->ctrl.fsm.state != ST_OFFSET_CAL) {
        hal_calibrate_finish();
    }
    a->last_state = a->ctrl.fsm.state;

    /* ---- 4. 硬件 Trip：优先于软件状态机 ---- */
    trip = hal_trip_latched();
    pwm_ok = a->out.pwm_enable && !trip;

    /* ---- 5. 调制映射：v_cmd → CMPA ---- */
    pwm_mod_step(&g_pwm, a->out.v_cmd, a->meas.vdc, pwm_ok);
    a->cmpa_a = g_pwm.cmpa_a;
    a->cmpa_b = g_pwm.cmpa_b;
    hal_pwm_apply(a->cmpa_a, a->cmpa_b);

    /* ---- 6. 板级动作 ---- */
    hal_pwm_enable(g_pwm.enabled);
    hal_relay(a->out.relay_close && !trip);
    hal_precharge(a->ctrl.fsm.state == ST_PRECHARGE);

    a->isr_count++;
}
