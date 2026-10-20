/**
 * fsm.h — 运行状态机
 *
 * INIT → OFFSET_CAL → WAIT_GRID → PRECHARGE → SYNC → CONNECT → MPPT_RUN
 * 任一运行态故障 → FAULT（封锁 PWM、断开继电器、锁存故障码）
 * FAULT 仅人工清除后回 INIT。
 * 调试：OPEN_LOOP、FIXED_I（由 debug_req 请求，不经 MPPT）。
 */
#ifndef PV_INV_FSM_H
#define PV_INV_FSM_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    ST_INIT = 0,
    ST_OFFSET_CAL,
    ST_WAIT_GRID,
    ST_PRECHARGE,
    ST_SYNC,
    ST_CONNECT,
    ST_MPPT_RUN,
    ST_FAULT,
    ST_OPEN_LOOP,
    ST_FIXED_I
} InvState;

enum {
    DBG_NONE = 0,
    DBG_OPEN_LOOP = 1,
    DBG_FIXED_I = 2
};

typedef struct {
    int grid_ok;        /* 电压/频率在范围内 */
    int pll_locked;
    int precharge_done; /* 母线已建立（调用方判定） */
    int fault_code;     /* 非 0 即故障，进入 FAULT 时锁存 */
    int debug_req;      /* DBG_* ，在 INIT 接受 */
    int clear_fault;    /* 人工复位脉冲，消费后清零 */
} FsmIn;

typedef struct {
    InvState state;
    float    timer_s;
    uint32_t fault_code;
    int      pwm_enable;
    int      relay_close;
} Fsm;

void fsm_init(Fsm *f);
void fsm_step(Fsm *f, FsmIn *in, float ts);

#ifdef __cplusplus
}
#endif

#endif
