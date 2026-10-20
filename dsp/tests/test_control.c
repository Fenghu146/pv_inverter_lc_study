/**
 * tests/test_control.c — PC 单元测试主程序
 *
 * 覆盖：
 * (a) SOGI-PLL 50 Hz / 36 Vrms 锁相（θ 稳态误差 < 0.1 rad）
 * (b) PR 对 50 Hz 正弦参考跟踪（L=0.5 mH, r=0.1 Ω 一阶对象，幅值误差 < 5%）
 * (c) P&O 在抛物线 P(V) 上收敛到 MPP ±1 V
 * (d) 保护：11 A 软过流、96 V 过压、故障码正确
 * (e) 状态机：正常序列走到 MPPT_RUN，注入故障进 FAULT，需人工复位回 INIT
 *
 * 每个用例打印 PASS/FAIL，最终汇总并以非零退出码表示失败。
 */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "control_isr.h"
#include "fsm.h"
#include "mppt_po.h"
#include "param.h"
#include "pi_ctrl.h"
#include "pr_ctrl.h"
#include "protect.h"
#include "sogi_pll.h"

#define M_PI 3.14159265358979323846f

static int g_fail = 0;

static void check(const char *name, int cond)
{
    if (cond) {
        printf("  PASS  %s\n", name);
    } else {
        printf("  FAIL  %s\n", name);
        g_fail++;
    }
}

/* ---------- (a) SOGI-PLL ---------- */
static void test_pll(void)
{
    SogiPll pll;
    const float Ts = CTRL_TS_S;
    const float w0 = GRID_W0_RAD_S;
    const float Um = GRID_UM_V;
    const int N = (int)(1.0f / Ts);
    float max_abs = 0.0f;
    int n;

    printf("[a] SOGI-PLL\n");
    sogi_pll_init(&pll);

    for (n = 0; n < N; n++) {
        float t = (float)n * Ts;
        float vg = Um * sinf(w0 * t) + 0.05f * Um * sinf(3.0f * w0 * t);
        float th_true;
        float err;

        sogi_pll_step(&pll, vg);

        if (n > (int)(0.8f / Ts)) {
            th_true = fmodf(w0 * t, TWO_PI);
            if (th_true < 0.0f) {
                th_true += TWO_PI;
            }
            err = pll.theta - th_true;
            if (err > (float)M_PI) {
                err -= TWO_PI;
            }
            if (err < -(float)M_PI) {
                err += TWO_PI;
            }
            if (fabsf(err) > max_abs) {
                max_abs = fabsf(err);
            }
        }
    }

    printf("    steady |theta err| max = %.4f rad (limit 0.1)\n", max_abs);
    check("PLL lock within 1 s, |dtheta| < 0.1 rad", max_abs < 0.1f && pll.locked);
}

/* ---------- (b) PR + 一阶对象 ---------- */
static void test_pr(void)
{
    PrCtrl pr;
    const float Ts = CTRL_TS_S;
    const float w0 = GRID_W0_RAD_S;
    const float L = 0.5e-3f;
    const float r = 0.1f;
    const float Iref = 5.0f;
    const float Vdc = 80.0f;
    const int N = (int)(1.5f / Ts);
    float i = 0.0f;
    float peak = 0.0f;
    int n;

    printf("[b] quasi-PR current loop\n");
    pr_init(&pr);

    for (n = 0; n < N; n++) {
        float t = (float)n * Ts;
        float iref = Iref * sinf(w0 * t);
        float err = iref - i;
        float u = pr_step(&pr, err, 0.0f, Vdc);

        i += (Ts / L) * (u - r * i);
        if (n > N - (int)(0.02f / Ts)) {
            if (fabsf(i) > peak) {
                peak = fabsf(i);
            }
        }
    }

    printf("    last-cycle |i| peak = %.4f A (ref 5.0, err %.2f%%)\n",
           peak, (peak - Iref) / Iref * 100.0f);
    check("PR amplitude error < 5%", fabsf(peak - Iref) / Iref < 0.05f);
}

/* ---------- (c) P&O on parabola ---------- */
static void test_mppt(void)
{
    MpptPo m;
    /* P = Pmax - k·(V - Vmpp)² , Vmpp = 68 V, Voc 取 85 使 0.8·Voc=68 在窗内 */
    const float Vmpp = 68.0f;
    const float Pmax = 200.0f;
    const float k = 2.0f;
    const float Voc = 85.0f;
    float v = 0.0f;
    int step;
    int converged = 0;

    printf("[c] P&O MPPT\n");
    mppt_init(&m, Voc);
    v = m.v_ref;

    for (step = 0; step < 80; step++) {
        float p = Pmax - k * (v - Vmpp) * (v - Vmpp);
        float vref = mppt_step(&m, v, p);
        v = vref; /* 理想电压环，V 跟上 V* */
        if (step > 10 && fabsf(m.v_ref - Vmpp) <= 1.0f) {
            converged = 1;
        }
    }

    printf("    V* final = %.2f V (MPP %.1f, tol ±1)\n", m.v_ref, Vmpp);
    check("P&O converges to MPP ±1 V", converged && fabsf(m.v_ref - Vmpp) <= 1.0f);
    check("V* stays inside [62, 75]", m.v_ref >= MPPT_V_MIN_V && m.v_ref <= MPPT_V_MAX_V);
}

/* ---------- (d) protection ---------- */
static void test_protect(void)
{
    ProtectState p;
    ProtectIn in;
    uint32_t code = 0;
    int n;
    const float Ts = CTRL_TS_S;
    const int nconf = (int)(PROTECT_CONFIRM_MS * 0.001f / Ts) + 2;

    printf("[d] protection\n");
    protect_init(&p);
    memset(&in, 0, sizeof(in));
    in.i_g = 11.0f;
    in.i_hard = 11.0f;
    in.vdc = 70.0f;
    in.vac_rms = 36.0f;
    in.freq_hz = 50.0f;
    in.grid_check_en = 1;

    for (n = 0; n < nconf; n++) {
        code = protect_step(&p, &in, Ts);
    }
    printf("    11 A -> code 0x%X\n", code);
    check("11 A sets FAULT_OC_SOFT", (code & FAULT_OC_SOFT) != 0);
    check("11 A does not set FAULT_OC_HARD", (code & FAULT_OC_HARD) == 0);

    protect_clear(&p);
    in.i_g = 1.0f;
    in.i_hard = 1.0f;
    in.vdc = 96.0f;
    code = 0;
    for (n = 0; n < nconf; n++) {
        code = protect_step(&p, &in, Ts);
    }
    printf("    96 V -> code 0x%X\n", code);
    check("96 V sets FAULT_VDC_OV", (code & FAULT_VDC_OV) != 0);
    check("96 V code is only OV", code == FAULT_VDC_OV);
}

/* ---------- (e) FSM sequence ---------- */
static void test_fsm(void)
{
    CtrlContext ctx;
    CtrlMeas m;
    CtrlOut o;
    int n;
    int saw_mppt = 0;
    int saw_fault = 0;
    int back_to_init = 0;
    const int N = (int)(0.5f / CTRL_TS_S);

    printf("[e] state machine\n");
    ctrl_init(&ctx, 85.0f);
    memset(&m, 0, sizeof(m));
    m.vdc = 70.0f;
    m.v_pv = 68.0f;
    m.i_pv = 2.0f;
    m.i_grid = 0.0f;
    m.i_hard = -1.0f;
    m.vac_rms = 36.0f;
    m.debug_req = DBG_NONE;
    m.clear_fault = 0;
    m.voc = 85.0f;

    for (n = 0; n < N; n++) {
        float t = (float)n * CTRL_TS_S;
        m.v_grid = GRID_UM_V * sinf(GRID_W0_RAD_S * t);
        m.i_grid = 0.0f;
        m.clear_fault = 0;
        ctrl_isr(&ctx, &m, &o);
        if (o.state == ST_MPPT_RUN) {
            saw_mppt = 1;
            break;
        }
    }
    printf("    reached state %d (MPPT_RUN=%d), pwm=%d relay=%d\n",
           (int)o.state, (int)ST_MPPT_RUN, o.pwm_enable, o.relay_close);
    check("normal sequence reaches MPPT_RUN", saw_mppt && o.pwm_enable && o.relay_close);

    /* 注入硬条件：母线 96 V 持续超过确认时间 */
    for (n = 0; n < 200; n++) {
        float t = (float)n * CTRL_TS_S;
        m.v_grid = GRID_UM_V * sinf(GRID_W0_RAD_S * t);
        m.vdc = 96.0f;
        m.clear_fault = 0;
        ctrl_isr(&ctx, &m, &o);
        if (o.state == ST_FAULT) {
            saw_fault = 1;
            break;
        }
    }
    printf("    after OV, state %d fault 0x%X pwm=%d relay=%d\n",
           (int)o.state, o.fault_code, o.pwm_enable, o.relay_close);
    check("OV enters FAULT and blocks PWM/relay",
          saw_fault && o.pwm_enable == 0 && o.relay_close == 0 &&
          (o.fault_code & FAULT_VDC_OV) != 0);

    /* 不复位应停在 FAULT */
    m.vdc = 70.0f;
    m.clear_fault = 0;
    ctrl_isr(&ctx, &m, &o);
    check("FAULT holds without manual clear", o.state == ST_FAULT);

    m.clear_fault = 1;
    ctrl_isr(&ctx, &m, &o);
    back_to_init = (o.state == ST_INIT || o.state == ST_OFFSET_CAL);
    printf("    after clear, state %d\n", (int)o.state);
    check("manual clear returns toward INIT", back_to_init);
}

int main(void)
{
    printf("pv inverter algorithm tests (Ts=50 us)\n");
    test_pll();
    test_pr();
    test_mppt();
    test_protect();
    test_fsm();

    printf("----\n");
    if (g_fail == 0) {
        printf("SUMMARY PASS  (0 failed)\n");
        return 0;
    }
    printf("SUMMARY FAIL  (%d failed)\n", g_fail);
    return 1;
}
