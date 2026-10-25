/**
 * control_isr.h — 20 kHz 算法节拍（无寄存器）
 *
 * 调用顺序：
 *   1. SOGI-PLL(v_g)
 *   2. 保护采样更新（过流/母线每拍；交流范围用 PLL 频率与调用方 rms）
 *   3. 状态机
 *   4. 每 20 拍：直流电压 PI → I_amp*
 *   5. 电流参考 i_ref = I_amp*·sin(θ)
 *   6. 准 PR + v_g 前馈 → v*（反馈取逆变侧 i_L）
 *   7. 死区补偿 → v_cmd
 *   8. 100 ms 窗平均后 P&O，更新 Vdc*
 * FAULT：pwm_enable=0，relay_close=0，v*=0。
 *
 * 反馈电流口径：电流环用 i_L（逆变侧），与 python/sim/inverter_sim.py、
 * Simulink 模型及方案 5.1 控制框图一致。i_g 只用于保护与并网计量。
 */
#ifndef PV_INV_CONTROL_ISR_H
#define PV_INV_CONTROL_ISR_H

#include "fsm.h"
#include "mppt_po.h"
#include "pr_ctrl.h"
#include "protect.h"
#include "sogi_pll.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float v_grid;       /* PCC 电压，V */
    float i_L;          /* 逆变侧电流，A —— 电流环反馈（与仿真/方案 5.1 一致） */
    float i_grid;       /* 并网侧电流，A —— 仅保护与计量 */
    float vdc;          /* 母线电压，V */
    float v_pv;         /* 光伏电压，V */
    float i_pv;         /* 光伏电流，A */
    float i_hard;       /* 硬过流镜像；<0 表示用 |i_grid| */
    float vac_rms;      /* 已算好的交流有效值；<0 表示内部递推 */
    int   debug_req;
    int   clear_fault;
    float voc;          /* MPPT 初值用，仅 init 读取 */
} CtrlMeas;

typedef struct {
    float v_star;       /* 电流环输出：桥臂电压指令（V，未含死区补偿） */
    float v_cmd;        /* 死区补偿后的桥臂电压指令（V）→ pwm_mod 输入 */
    float i_ref;
    float i_amp;
    float vdc_ref;
    float theta;
    float omega;
    int   pwm_enable;
    int   relay_close;
    InvState state;
    uint32_t fault_code;
    float i_L;          /* 回读：本拍用于反馈的逆变侧电流 */
} CtrlOut;

typedef struct {
    SogiPll      pll;
    PrCtrl       pr;
    PiCtrl       vdc_pi;
    MpptPo       mppt;
    ProtectState prot;
    Fsm          fsm;

    float vdc_ref;
    float i_amp;
    unsigned vdc_div;
    unsigned mppt_n;
    float p_acc;
    float v_acc;
    float vac_acc;      /* v_g² 累加，用于内部 rms */
    float vac_rms_last; /* 最近一个工频周期的有效值 */
    unsigned vac_n;
    float pll_unlock_s; /* |v_q| 超差累计时间 */

    int   pwm_enable;
    int   relay_close;
    float v_star;
    float v_cmd;
    float i_ref;
} CtrlContext;

void ctrl_init(CtrlContext *c, float voc);
void ctrl_isr(CtrlContext *c, const CtrlMeas *m, CtrlOut *o);

#ifdef __cplusplus
}
#endif

#endif
