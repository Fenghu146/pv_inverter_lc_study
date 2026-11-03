/**
 * sitl_bridge.h — SITL 桥接层 ABI（供 Python ctypes 调用）
 *
 * 编译：gcc -std=c99 -O2 -I dsp/include dsp/src/*.c dsp/sim/sitl_bridge.c \
 *        -shared -o dsp/sim/build/sitl.dll -lm
 * （tools/sitl_build.py 已封装，不要手敲）
 */
#ifndef PV_INV_SITL_BRIDGE_H
#define PV_INV_SITL_BRIDGE_H

#ifdef __cplusplus
extern "C" {
#endif

/* sitl_step 的输出打包长度 */
#define SITL_OUT_N 20

/* 入口：复位整机（app_init），voc 用于 MPPT 初值（0.8·Voc） */
int sitl_reset(float voc);

/** 一拍之前设置调试请求/人工复位（清零后自动消费，与真机一致） */
void sitl_request(int debug_req, int clear_fault);

/**
 * 跑一拍 20 kHz 中断。
 * si[6]  : [v_pv, i_pv, vdc, v_grid, i_L, i_g]，SI 单位
 * out[20] : 见下
 */
void sitl_step(const double si[6], double out[SITL_OUT_N]);

unsigned sitl_tbprd(void);

#ifdef __cplusplus
}
#endif

/* out[] 索引约定（与 sitl_bridge.c 一一对应） */
#define SITL_OUT_CMPA_A     0
#define SITL_OUT_CMPA_B     1
#define SITL_OUT_V_CMD      2
#define SITL_OUT_V_STAR     3
#define SITL_OUT_I_REF      4
#define SITL_OUT_I_AMP      5
#define SITL_OUT_VDC_REF    6
#define SITL_OUT_THETA      7
#define SITL_OUT_OMEGA      8
#define SITL_OUT_PWM_REQ    9
#define SITL_OUT_RELAY_REQ  10
#define SITL_OUT_STATE      11
#define SITL_OUT_FAULT      12
#define SITL_OUT_ISR_COUNT  13
#define SITL_OUT_PWM_ON     14
#define SITL_OUT_PRECHARGE  15
#define SITL_OUT_TRIP       16
#define SITL_OUT_VDC_MEAS   17
#define SITL_OUT_IL_MEAS    18
#define SITL_OUT_VG_MEAS    19

#endif /* PV_INV_SITL_BRIDGE_H */
