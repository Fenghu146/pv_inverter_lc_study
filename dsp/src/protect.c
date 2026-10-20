#include "protect.h"
#include "param.h"

static int over_for(float *acc, int cond, float ts, float need)
{
    if (cond) {
        *acc += ts;
        if (*acc >= need) {
            *acc = need;
            return 1;
        }
        return 0;
    }
    *acc = 0.0f;
    return 0;
}

void protect_init(ProtectState *p)
{
    protect_clear(p);
}

void protect_clear(ProtectState *p)
{
    p->oc_soft_s = 0.0f;
    p->oc_hard_s = 0.0f;
    p->ov_s = 0.0f;
    p->uv_s = 0.0f;
    p->latched = FAULT_NONE;
    p->active = FAULT_NONE;
}

uint32_t protect_step(ProtectState *p, const ProtectIn *in, float ts)
{
    uint32_t now = FAULT_NONE;
    float i_abs = in->i_g >= 0.0f ? in->i_g : -in->i_g;
    float ih = in->i_hard >= 0.0f ? in->i_hard : -in->i_hard;
    const float tconf = PROTECT_CONFIRM_MS * 0.001f;

    if (over_for(&p->oc_soft_s, i_abs > OC_SOFT_A, ts, tconf)) {
        now |= FAULT_OC_SOFT;
    }
    if (over_for(&p->oc_hard_s, ih > OC_HARD_A, ts, tconf)) {
        now |= FAULT_OC_HARD;
    }
    if (over_for(&p->ov_s, in->vdc > VDC_OV_V, ts, tconf)) {
        now |= FAULT_VDC_OV;
    }
    if (over_for(&p->uv_s, in->vdc < VDC_UV_V, ts, tconf)) {
        now |= FAULT_VDC_UV;
    }

    if (in->grid_check_en) {
        if (in->vac_rms < VAC_RMS_MIN_V || in->vac_rms > VAC_RMS_MAX_V) {
            now |= FAULT_VAC_RANGE;
        }
        if (in->freq_hz < FREQ_MIN_HZ || in->freq_hz > FREQ_MAX_HZ) {
            now |= FAULT_FREQ;
        }
        if (in->pll_unlocked) {
            now |= FAULT_PLL_UNLOCK;
        }
    }

    p->latched |= now;
    p->active = p->latched;
    return p->active;
}
