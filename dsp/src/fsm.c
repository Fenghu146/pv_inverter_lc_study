#include "fsm.h"
#include "param.h"

static void enter_fault(Fsm *f, uint32_t code)
{
    f->state = ST_FAULT;
    f->fault_code = code;
    f->pwm_enable = 0;
    f->relay_close = 0;
    f->timer_s = 0.0f;
}

static int take_fault(Fsm *f, const FsmIn *in)
{
    if (in->fault_code != 0) {
        enter_fault(f, (uint32_t)in->fault_code);
        return 1;
    }
    return 0;
}

void fsm_init(Fsm *f)
{
    f->state = ST_INIT;
    f->timer_s = 0.0f;
    f->fault_code = FAULT_NONE;
    f->pwm_enable = 0;
    f->relay_close = 0;
}

void fsm_step(Fsm *f, FsmIn *in, float ts)
{
    f->timer_s += ts;

    if (f->state == ST_FAULT) {
        f->pwm_enable = 0;
        f->relay_close = 0;
        if (in->clear_fault) {
            in->clear_fault = 0;
            f->fault_code = FAULT_NONE;
            f->state = ST_INIT;
            f->timer_s = 0.0f;
        }
        return;
    }

    if (f->state != ST_INIT && take_fault(f, in)) {
        return;
    }

    switch (f->state) {
    case ST_INIT:
        f->pwm_enable = 0;
        f->relay_close = 0;
        f->fault_code = FAULT_NONE;
        if (in->debug_req == DBG_OPEN_LOOP) {
            f->state = ST_OPEN_LOOP;
            f->timer_s = 0.0f;
        } else if (in->debug_req == DBG_FIXED_I) {
            f->state = ST_FIXED_I;
            f->timer_s = 0.0f;
        } else {
            f->state = ST_OFFSET_CAL;
            f->timer_s = 0.0f;
        }
        break;

    case ST_OFFSET_CAL:
        f->pwm_enable = 0;
        f->relay_close = 0;
        if (f->timer_s >= OFFSET_CAL_MS * 0.001f) {
            f->state = ST_WAIT_GRID;
            f->timer_s = 0.0f;
        }
        break;

    case ST_WAIT_GRID:
        f->pwm_enable = 0;
        f->relay_close = 0;
        if (!in->grid_ok) {
            f->timer_s = 0.0f;
        } else if (f->timer_s >= GRID_OK_MS * 0.001f) {
            f->state = ST_PRECHARGE;
            f->timer_s = 0.0f;
        }
        break;

    case ST_PRECHARGE:
        /* 预充阶段允许上管调制由上层解释；算法层只给出使能。
         * 母线必须真正建立（in->precharge_done）才前进；
         * 超时不再"闯关"，而是报 FAULT_PRECHARGE 停住。 */
        f->pwm_enable = 0;
        f->relay_close = 0;
        if (in->precharge_done) {
            f->state = ST_SYNC;
            f->timer_s = 0.0f;
        } else if (f->timer_s >= PRECHARGE_TIMEOUT_MS * 0.001f) {
            enter_fault(f, FAULT_PRECHARGE);
        }
        break;

    case ST_SYNC:
        f->pwm_enable = 0;
        f->relay_close = 0;
        if (!in->pll_locked || !in->grid_ok) {
            f->timer_s = 0.0f;
        } else if (f->timer_s >= SYNC_LOCK_MS * 0.001f) {
            f->state = ST_CONNECT;
            f->timer_s = 0.0f;
        }
        break;

    case ST_CONNECT:
        f->pwm_enable = 1;
        f->relay_close = 1;
        if (f->timer_s >= CONNECT_DWELL_MS * 0.001f) {
            f->state = ST_MPPT_RUN;
            f->timer_s = 0.0f;
        }
        break;

    case ST_MPPT_RUN:
        f->pwm_enable = 1;
        f->relay_close = 1;
        break;

    case ST_OPEN_LOOP:
        f->pwm_enable = 1;
        f->relay_close = 0;
        break;

    case ST_FIXED_I:
        f->pwm_enable = 1;
        f->relay_close = 1;
        break;

    case ST_FAULT:
    default:
        enter_fault(f, f->fault_code);
        break;
    }
}
