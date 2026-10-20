/**
 * pi_ctrl.h — 通用 PI，条件积分抗饱和
 *
 * u = Kp·e + integ
 * 仅当输出未顶在限幅、或误差在把输出拉回限幅内的方向时，才积分：
 *   integ += Ki·e·Ts
 */
#ifndef PV_INV_PI_CTRL_H
#define PV_INV_PI_CTRL_H

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float kp;
    float ki;
    float ts;
    float out_min;
    float out_max;
    float integ;
    float out;
} PiCtrl;

void pi_init(PiCtrl *pi, float kp, float ki, float ts,
             float out_min, float out_max);
void pi_reset(PiCtrl *pi);
float pi_step(PiCtrl *pi, float err);

#ifdef __cplusplus
}
#endif

#endif
