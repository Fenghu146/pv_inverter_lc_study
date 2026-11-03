/**
 * sitl_bridge.c — 软件在环（SITL）桥接层
 *
 * 把 DSP 算法层（app_isr + 全部 dsp/src）编译成共享库，供 Python 逐拍调用：
 *
 *   Python plant（主电路数值积分）  ──SI 测量值──▶  sitl_step()
 *                                    ◀──CMPA/状态──
 *
 * 与真机的对应关系：
 *   - 采样：Python 给的是"已标定的 SI 值"，桥接层按 param.h 的调理参数
 *     （SENSE_V_DIV / SENSE_VAC_* / SENSE_I_GAIN）反算成 12 位 ADC 码再灌进
 *     hal_stub，于是 DSP 侧走的是完整链路：ADC 码 → SI → 零偏 → ctrl_isr。
 *     这样零偏标定（OFFSET_CAL 累计、FINISH 锁定）也在环内真实发生。
 *   - 执行：hal_stub 记下 CMPA_A/B、继电器、预充、Trip；Python 用 CMPA 还原
 *     占空比去驱动 H 桥模型，并把这些影子状态读回去判断硬件动作。
 *   - 温度/硬件故障不入环：Trip 始终由 hal_stub 的锁存位模拟，Python 侧不触发。
 *
 * 不在这里做的事：开关器件损耗、驱动延时（已由 DEADTIME 常数在算法里表达）、
 * ADC 量化误差以外的噪声（如需可加在 Python plant 侧）。
 */
#include "app.h"
#include "hal.h"
#include "param.h"
#include "sitl_bridge.h"

#include <math.h>
#include <string.h>

static App g_app;

/* hal_stub 的影子状态（hal.h 未导出，此处按其定义声明；字段顺序须一致） */
typedef struct {
    unsigned cmpa_a;
    unsigned cmpa_b;
    int      pwm_on;
    int      relay;
    int      precharge;
    int      trip;
    unsigned adc_reads;
    unsigned wdog;
} StubStateView;

extern const StubStateView *hal_stub_state(void);

/* CMPA 无符号：pwm_mod 已限幅到 [0, TBPRD] */
static unsigned adc_code(float pin_volt)
{
    long c;
    if (pin_volt < 0.0f) {
        pin_volt = 0.0f;
    }
    if (pin_volt > ADC_VREF_V) {
        pin_volt = ADC_VREF_V;
    }
    c = (long)(pin_volt * ADC_FULL_SCALE / ADC_VREF_V + 0.5f);
    if (c < 0) {
        c = 0;
    }
    if (c > (long)ADC_FULL_SCALE) {
        c = (long)ADC_FULL_SCALE;
    }
    return (unsigned)c;
}

/* SI → ADC 码（hal_raw_to_si 的逆） */
static void si_to_raw(const double si[6], unsigned short raw[6])
{
    /* idx: 0=V_pv 1=I_pv 2=V_dc 3=V_g 4=I_L 5=I_g */
    raw[0] = (unsigned short)adc_code((float)si[0] / SENSE_V_DIV);
    raw[1] = (unsigned short)adc_code((float)si[1] / SENSE_I_GAIN_A_PER_V + SENSE_I_OFFSET_V);
    raw[2] = (unsigned short)adc_code((float)si[2] / SENSE_V_DIV);
    raw[3] = (unsigned short)adc_code((float)si[3] / SENSE_VAC_DIV + SENSE_VAC_OFFSET_V);
    raw[4] = (unsigned short)adc_code((float)si[4] / SENSE_I_GAIN_A_PER_V + SENSE_I_OFFSET_V);
    raw[5] = (unsigned short)adc_code((float)si[5] / SENSE_I_GAIN_A_PER_V + SENSE_I_OFFSET_V);
}

/* ---- 生命周期 ---- */
int sitl_reset(float voc)
{
    app_init(&g_app, voc);
    return 0;
}

void sitl_request(int debug_req, int clear_fault)
{
    g_app.debug_req = debug_req;
    g_app.clear_fault = clear_fault;
}

/* ---- 一拍：喂测量、跑 app_isr、取输出 ---- */
/**
 * si: 6 个 SI 测量值 [v_pv, i_pv, vdc, v_grid, i_L, i_g]
 * out: 定长 20 个输出，索引见 sitl_bridge.h
 */
void sitl_step(const double si[6], double out[SITL_OUT_N])
{
    unsigned short raw[6];
    const StubStateView *st;

    si_to_raw(si, raw);
    hal_stub_set_raw(raw);
    app_isr(&g_app);

    st = hal_stub_state();

    out[0]  = (double)(g_app.cmpa_a > PWM_TBPRD ? PWM_TBPRD : g_app.cmpa_a);
    out[1]  = (double)(g_app.cmpa_b > PWM_TBPRD ? PWM_TBPRD : g_app.cmpa_b);
    out[2]  = (double)g_app.out.v_cmd;
    out[3]  = (double)g_app.out.v_star;
    out[4]  = (double)g_app.out.i_ref;
    out[5]  = (double)g_app.out.i_amp;
    out[6]  = (double)g_app.out.vdc_ref;
    out[7]  = (double)g_app.out.theta;
    out[8]  = (double)g_app.out.omega;
    out[9]  = (double)g_app.out.pwm_enable;
    out[10] = (double)g_app.out.relay_close;
    out[11] = (double)g_app.out.state;
    out[12] = (double)g_app.out.fault_code;
    out[13] = (double)g_app.isr_count;
    out[14] = (double)st->pwm_on;
    out[15] = (double)st->precharge;
    out[16] = (double)st->trip;
    out[17] = (double)g_app.meas.vdc;
    out[18] = (double)g_app.meas.i_L;
    out[19] = (double)g_app.meas.v_grid;
}

/* 便于 Python 侧做一致性自检：返回算法层看到的 CMPA 上限（TBPRD） */
void sitl_set_trip(int on)
{
    hal_stub_set_trip(on);
}

unsigned sitl_tbprd(void)
{
    return PWM_TBPRD;
}
