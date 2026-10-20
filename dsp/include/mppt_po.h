/**
 * mppt_po.h — 扰动观察法
 *
 * 每 100 ms 用该窗平均功率判向：
 *   dP、dV 同号 → 继续同向扰动 ΔV，否则反向。
 * V* 限幅 [62, 75] V，初值 0.8·Voc。
 */
#ifndef PV_INV_MPPT_PO_H
#define PV_INV_MPPT_PO_H

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float v_ref;
    float v_min;
    float v_max;
    float dv;
    float p_prev;
    float v_prev;
    int   dir;      /* +1 / -1 */
    int   inited;
} MpptPo;

void mppt_init(MpptPo *m, float voc);
void mppt_reset(MpptPo *m, float voc);

/** 输入本周期平均 V_pv、P_pv，返回更新后的 V* */
float mppt_step(MpptPo *m, float v_avg, float p_avg);

#ifdef __cplusplus
}
#endif

#endif
