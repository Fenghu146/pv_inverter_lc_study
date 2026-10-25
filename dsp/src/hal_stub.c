/**
 * hal_stub.c — HAL 的 PC 实现（单元测试 / 算法回归用）
 *
 * 不接触任何硬件，只维护"最后一次写入"的影子状态，供测试断言：
 *   - PWM 比较值、使能位
 *   - 继电器、预充
 *   - Trip 锁存
 * ADC 原始码由测试直接灌入 hal_set_raw()。
 */
#include "hal.h"
#include "param.h"

#include <string.h>

static unsigned short g_raw[6];
/* 零偏：g_off 是“当前生效的平均值”，g_acc 是标定窗口内的累计和。
 * 两者必须分开——否则标定期间累计值会被当成偏置用掉（1000 拍后就成 1500 V）。 */
static float g_off[2] = { SENSE_I_OFFSET_V, SENSE_I_OFFSET_V };
static float g_acc[2];
static int   g_acc_n;

typedef struct {
    unsigned cmpa_a;
    unsigned cmpa_b;
    int      pwm_on;
    int      relay;
    int      precharge;
    int      trip;
    unsigned adc_reads;
    unsigned wdog;
} StubState;

static StubState g_s;

void hal_stub_reset(void)
{
    memset(&g_s, 0, sizeof(g_s));
    memset(g_raw, 0, sizeof(g_raw));
    g_acc[0] = 0.0f;
    g_acc[1] = 0.0f;
    g_acc_n = 0;
    g_off[0] = SENSE_I_OFFSET_V;
    g_off[1] = SENSE_I_OFFSET_V;
}

/* ---- 测试注入 ---- */
void hal_stub_set_raw(const unsigned short raw[6])
{
    memcpy(g_raw, raw, 6 * sizeof(unsigned short));
}

const StubState *hal_stub_state(void)
{
    return &g_s;
}

/* ---- HAL ---- */
void hal_init(void)
{
    hal_stub_reset();
}

void hal_read_adc_raw(unsigned short raw[6])
{
    memcpy(raw, g_raw, 6 * sizeof(unsigned short));
    g_s.adc_reads++;
}

static float raw_to_volt(unsigned short code)
{
    return (float)code * ADC_VREF_V / ADC_FULL_SCALE;
}

void hal_raw_to_si(const unsigned short raw[6], HalMeas *m)
{
    /* idx: 0=V_pv 1=I_pv 2=V_dc 3=V_g 4=I_L 5=I_g */
    m->v_pv   = raw_to_volt(raw[0]) * SENSE_V_DIV;
    m->i_pv   = (raw_to_volt(raw[1]) - g_off[0]) * SENSE_I_GAIN_A_PER_V;
    m->vdc    = raw_to_volt(raw[2]) * SENSE_V_DIV;
    m->v_grid = (raw_to_volt(raw[3]) - SENSE_VAC_OFFSET_V) * SENSE_VAC_DIV;
    m->i_L    = (raw_to_volt(raw[4]) - g_off[0]) * SENSE_I_GAIN_A_PER_V;
    m->i_g    = (raw_to_volt(raw[5]) - g_off[1]) * SENSE_I_GAIN_A_PER_V;
}

void hal_calibrate_offset(const unsigned short raw[6])
{
    g_acc[0] += raw_to_volt(raw[1]);
    g_acc[1] += raw_to_volt(raw[5]);
    g_acc_n++;
}

void hal_calibrate_finish(void)
{
    if (g_acc_n > 0) {
        g_off[0] = g_acc[0] / (float)g_acc_n;
        g_off[1] = g_acc[1] / (float)g_acc_n;
    }
    g_acc[0] = 0.0f;
    g_acc[1] = 0.0f;
    g_acc_n = 0;
}

void hal_pwm_apply(unsigned cmpa_a, unsigned cmpa_b)
{
    g_s.cmpa_a = cmpa_a;
    g_s.cmpa_b = cmpa_b;
}

void hal_pwm_enable(int on)
{
    g_s.pwm_on = on ? 1 : 0;
}

void hal_relay(int close)
{
    g_s.relay = close ? 1 : 0;
}

void hal_precharge(int on)
{
    g_s.precharge = on ? 1 : 0;
}

int hal_trip_latched(void)
{
    return g_s.trip;
}

void hal_clear_trip(void)
{
    g_s.trip = 0;
}

void hal_watchdog_kick(void)
{
    g_s.wdog++;
}
