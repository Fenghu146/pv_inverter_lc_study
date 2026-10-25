/**
 * app.h — 应用层：把算法节拍接到硬件
 *
 * 这一个文件就是"算出来的 v*"到"引脚上的 PWM"之间的那一层。
 * 它把 control_isr() 的纯算法输出翻译成 HAL 调用，顺序固定：
 *
 *   ADC 采样 → SI 换算 → (CAL 阶段累计零偏) → ctrl_isr
 *            → 硬件 Trip 检查 → pwm_mod_step → hal_pwm_apply
 *            → hal_pwm_enable / hal_relay / hal_precharge
 *
 * 中断服务函数里只调 app_isr()，不写任何寄存器。
 */
#ifndef PV_INV_APP_H
#define PV_INV_APP_H

#include "control_isr.h"
#include "hal.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    CtrlContext ctrl;
    unsigned short raw[6];
    HalMeas meas;
    CtrlOut out;
    unsigned cmpa_a;
    unsigned cmpa_b;
    float voc;
    InvState last_state;
    unsigned isr_count;
    int   debug_req;     /* DBG_*，仅在 INIT 被接受一次 */
    int   clear_fault;   /* 人工复位脉冲 */
} App;

void app_init(App *a, float voc);
void app_isr(App *a);

#ifdef __cplusplus
}
#endif

#endif /* PV_INV_APP_H */
