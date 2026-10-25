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

#include "app.h"
#include "control_isr.h"
#include "fsm.h"
#include "hal.h"
#include "mppt_po.h"
#include "param.h"
#include "pi_ctrl.h"
#include "pr_ctrl.h"
#include "protect.h"
#include "pwm_mod.h"
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
    m.i_L = 0.0f;

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
        m.i_L = 0.0f;
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

/* ---------- (f) PWM 调制映射 ---------- */
static void test_pwm(void)
{
    PwmMod p;
    unsigned half = PWM_TBPRD / 2u;

    printf("[f] PWM mapping (uni-polar doubling)\n");
    pwm_mod_init(&p, PWM_TBPRD, PWM_DUTY_LIM);

    /* m = 0 → 两腿 50% */
    pwm_mod_step(&p, 0.0f, 75.0f, 1);
    printf("    m=0     : CMPA_A=%u CMPA_B=%u (expect %u/%u)\n",
           p.cmpa_a, p.cmpa_b, half, half);
    check("m=0 gives 50/50",
          p.cmpa_a == half && p.cmpa_b == half && p.enabled);

    /* m = +0.5 → dA = 0.75, dB = 0.25 */
    pwm_mod_step(&p, 0.5f * 75.0f, 75.0f, 1);
    printf("    m=+0.5  : CMPA_A=%u CMPA_B=%u\n", p.cmpa_a, p.cmpa_b);
    check("m=+0.5 gives dA=0.75 dB=0.25",
          p.cmpa_a == (unsigned)(0.75f * PWM_TBPRD + 0.5f) &&
          p.cmpa_b == (unsigned)(0.25f * PWM_TBPRD + 0.5f));

    /* 过调制限幅：|m| 不得超过 0.95 */
    pwm_mod_step(&p, 5.0f * 75.0f, 75.0f, 1);
    printf("    v*=375V : m=%.3f CMPA_A=%u CMPA_B=%u\n", p.m, p.cmpa_a, p.cmpa_b);
    check("over-modulation clamps to 0.95",
          fabsf(p.m - PWM_DUTY_LIM) < 1e-5f && p.cmpa_a <= PWM_TBPRD);

    /* 停机：CMPA 全 0（双下管常通，v_ab=0，无开关动作） */
    pwm_mod_step(&p, 30.0f, 75.0f, 0);
    printf("    disabled: CMPA_A=%u CMPA_B=%u en=%d\n",
           p.cmpa_a, p.cmpa_b, p.enabled);
    check("disable forces zero compare",
          p.cmpa_a == 0u && p.cmpa_b == 0u && p.enabled == 0);

    /* 母线欠压保护：vdc < 10 V 时不调制 */
    pwm_mod_step(&p, 5.0f, 8.0f, 1);
    check("low Vdc blocks modulation", p.enabled == 0 && p.cmpa_a == 0u);
}

/* ---------- (g) 死区补偿 ---------- */
static void test_deadtime_comp(void)
{
    CtrlContext c;
    CtrlMeas m;
    CtrlOut o;

    printf("[g] deadtime compensation\n");
    ctrl_init(&c, 85.0f);
    memset(&m, 0, sizeof(m));
    m.vdc = 75.0f;
    m.v_pv = 68.0f;
    m.i_pv = 2.0f;
    m.i_hard = -1.0f;
    m.vac_rms = 36.0f;
    m.voc = 85.0f;

    /* 先跑进 MPPT_RUN */
    {
        int n;
        for (n = 0; n < (int)(0.5f / CTRL_TS_S); n++) {
            float t = (float)n * CTRL_TS_S;
            m.v_grid = GRID_UM_V * sinf(GRID_W0_RAD_S * t);
            m.i_L = 0.0f;
            ctrl_isr(&c, &m, &o);
            if (o.state == ST_MPPT_RUN) {
                break;
            }
        }
    }
    check("reached MPPT_RUN for DT test", o.state == ST_MPPT_RUN);

    /* 正电流：v_cmd 应比 v_star 高 +2·fsw·td·Vdc */
    {
        float expect;
        m.i_L = 5.0f;
        ctrl_isr(&c, &m, &o);
        expect = 2.0f * CTRL_FS_HZ * (DEADTIME_NS * 1e-9f) * 75.0f;
        printf("    iL=+5A: v_star=%.3f v_cmd=%.3f delta=%.3f (expect %.3f)\n",
               o.v_star, o.v_cmd, o.v_cmd - o.v_star, expect);
        /* 若被限幅则 delta 可能小于 expect，这里只要求方向与量级 */
        check("DT comp adds +ve offset for iL>0",
              (o.v_cmd - o.v_star) > 0.9f * expect - 1e-3f);
    }

    /* 负电流：反向 */
    {
        float expect;
        m.i_L = -5.0f;
        ctrl_isr(&c, &m, &o);
        expect = 2.0f * CTRL_FS_HZ * (DEADTIME_NS * 1e-9f) * 75.0f;
        printf("    iL=-5A: v_star=%.3f v_cmd=%.3f delta=%.3f\n",
               o.v_star, o.v_cmd, o.v_cmd - o.v_star);
        check("DT comp adds -ve offset for iL<0",
              (o.v_cmd - o.v_star) < -0.9f * expect + 1e-3f);
    }

    /* 过零死区：|iL|<0.05 不补偿 */
    {
        float base;
        m.i_L = 5.0f;
        ctrl_isr(&c, &m, &o);
        base = o.v_cmd;
        m.i_L = 0.0f;
        ctrl_isr(&c, &m, &o);
        printf("    iL=0A : v_cmd=%.3f (expect no offset band)\n", o.v_cmd);
        check("DT comp suppressed near zero crossing",
              fabsf(o.v_cmd - o.v_star) < 1e-3f);
        (void)base;
    }
}

/* ---------- (h) i_L 反馈口径 ---------- */
static void test_il_feedback(void)
{
    CtrlContext c;
    CtrlMeas m;
    CtrlOut o;

    printf("[h] current feedback uses i_L (inverter side)\n");
    ctrl_init(&c, 85.0f);
    memset(&m, 0, sizeof(m));
    m.vdc = 75.0f;
    m.v_pv = 68.0f;
    m.i_pv = 2.0f;
    m.i_hard = -1.0f;
    m.vac_rms = 36.0f;
    m.voc = 85.0f;

    {
        int n;
        for (n = 0; n < (int)(0.5f / CTRL_TS_S); n++) {
            float t = (float)n * CTRL_TS_S;
            m.v_grid = GRID_UM_V * sinf(GRID_W0_RAD_S * t);
            m.i_L = 0.0f;
            ctrl_isr(&c, &m, &o);
            if (o.state == ST_MPPT_RUN) {
                break;
            }
        }
    }

    /* 只给 i_grid 不给 i_L，v_star 不应响应 */
    {
        float v0;
        m.i_grid = 8.0f;
        m.i_L = 0.0f;
        ctrl_isr(&c, &m, &o);
        v0 = o.v_star;
        m.i_grid = 0.0f;
        m.i_L = 8.0f;
        ctrl_isr(&c, &m, &o);
        printf("    i_g only: v*=%.3f ; i_L only: v*=%.3f\n", v0, o.v_star);
        check("PR ignores i_grid, responds to i_L", fabsf(v0 - o.v_star) > 1.0f);
    }

    /* 回读字段 */
    m.i_L = 3.25f;
    ctrl_isr(&c, &m, &o);
    printf("    o.i_L = %.2f (expect 3.25)\n", o.i_L);
    check("CtrlOut echoes i_L", fabsf(o.i_L - 3.25f) < 1e-6f);
}

/* ---------- (i) ADC 换算 ---------- */
static void test_hal_scale(void)
{
    unsigned short raw[6];
    HalMeas h;

    printf("[i] ADC scaling\n");
    hal_init();

    /* 1.5 V = 2048 码 = 零电流；3.0 V = 4095 码 = +15 A */
    raw[0] = (unsigned short)(4095.0f * (100.0f / SENSE_V_DIV) / ADC_VREF_V);
    raw[1] = (unsigned short)(4095.0f * 1.5f / ADC_VREF_V);
    raw[2] = (unsigned short)(4095.0f * (75.0f / SENSE_V_DIV) / ADC_VREF_V);
    raw[3] = (unsigned short)(4095.0f * 1.5f / ADC_VREF_V);   /* V_g = 0 V */
    raw[4] = (unsigned short)(4095.0f * 2.0f / ADC_VREF_V);   /* I_L = +5 A */
    raw[5] = (unsigned short)(4095.0f * 1.0f / ADC_VREF_V);   /* I_g = -5 A */

    hal_raw_to_si(raw, &h);
    printf("    vpv=%.2f ipv=%.2f vdc=%.2f vg=%.2f iL=%.2f ig=%.2f\n",
           h.v_pv, h.i_pv, h.vdc, h.v_grid, h.i_L, h.i_g);
    check("V_pv scales to 100 V", fabsf(h.v_pv - 100.0f) < 0.1f);
    check("Vdc scales to 75 V", fabsf(h.vdc - 75.0f) < 0.1f);
    check("I_L scales to +5 A", fabsf(h.i_L - 5.0f) < 0.01f);
    check("I_g scales to -5 A", fabsf(h.i_g + 5.0f) < 0.01f);

    /* 交流通道：+36√2 V → 应为 50.91 V */
    raw[3] = (unsigned short)(4095.0f * (1.5f + 50.91f / SENSE_VAC_DIV) / ADC_VREF_V);
    hal_raw_to_si(raw, &h);
    printf("    vac peak: vg=%.2f (expect 50.91)\n", h.v_grid);
    check("V_g bipolar scales to +50.91 V", fabsf(h.v_grid - 50.91f) < 0.1f);}

/* ---------- (j) 全链路：app_isr ---------- */
static void test_app_chain(void)
{
    App a;
    unsigned short raw[6];
    int n;
    int reached = 0;
    const int N = (int)(0.6f / CTRL_TS_S);

    printf("[j] app_isr full chain\n");
    app_init(&a, 85.0f);

    for (n = 0; n < N; n++) {
        float t = (float)n * CTRL_TS_S;
        float vg = GRID_UM_V * sinf(GRID_W0_RAD_S * t);
        HalMeas h;

        /* 造 ADC 码：Vdc=70, V_pv=68, 电网 36Vrms, I_L 微小 */
        raw[0] = (unsigned short)(4095.0f * (68.0f / SENSE_V_DIV) / ADC_VREF_V);
        raw[1] = (unsigned short)(4095.0f * 1.5f / ADC_VREF_V);
        raw[2] = (unsigned short)(4095.0f * (70.0f / SENSE_V_DIV) / ADC_VREF_V);
        raw[3] = (unsigned short)(4095.0f * (SENSE_VAC_OFFSET_V + vg / SENSE_VAC_DIV) / ADC_VREF_V);
        raw[4] = (unsigned short)(4095.0f * (1.5f + 0.05f * sinf(GRID_W0_RAD_S * t)) / ADC_VREF_V);
        raw[5] = raw[4];
        hal_stub_set_raw(raw);

        app_isr(&a);

        if (a.out.state == ST_MPPT_RUN) {
            reached = 1;
            break;
        }
        (void)h;
    }

    printf("    state=%d fault=0x%X cmpa_a=%u cmpa_b=%u isr=%u\n",
           (int)a.out.state, a.out.fault_code, a.cmpa_a, a.cmpa_b, a.isr_count);
    check("app chain reaches MPPT_RUN", reached == 1);
    check("PWM compares populated after enable",
          a.out.pwm_enable && a.cmpa_a > 0u && a.cmpa_b > 0u);
    check("ISR count advanced", a.isr_count == (unsigned)N || a.isr_count > 0u);
}

/* ---------- (k) 预充不得绕过电压判据 ---------- */
static void test_precharge_guard(void)
{
    Fsm f;
    FsmIn in;

    printf("[k] precharge guard\n");
    fsm_init(&f);
    memset(&in, 0, sizeof(in));
    in.grid_ok = 1;
    in.pll_locked = 1;
    in.precharge_done = 0;

    /* 直接推进到 PRECHARGE */
    {
        int n;
        for (n = 0; n < (int)(0.5f / CTRL_TS_S); n++) {
            fsm_step(&f, &in, CTRL_TS_S);
            if (f.state == ST_PRECHARGE) {
                break;
            }
        }
    }
    check("reached PRECHARGE", f.state == ST_PRECHARGE);

    /* 母线始终未建立，跑过超时时间 */
    {
        int n;
        const int N = (int)((PRECHARGE_TIMEOUT_MS + 50.0f) * 0.001f / CTRL_TS_S);
        for (n = 0; n < N; n++) {
            fsm_step(&f, &in, CTRL_TS_S);
            if (f.state == ST_FAULT) {
                break;
            }
        }
    }
    printf("    after timeout: state=%d fault=0x%X pwm=%d\n",
           (int)f.state, f.fault_code, f.pwm_enable);
    check("precharge timeout goes FAULT not CONNECT",
          f.state == ST_FAULT && (f.fault_code & FAULT_PRECHARGE) != 0);
    check("FAULT blocks PWM during precharge timeout", f.pwm_enable == 0);

    /* 正常路径：电压建立后能走下去 */
    fsm_init(&f);
    {
        int n;
        for (n = 0; n < (int)(0.5f / CTRL_TS_S); n++) {
            fsm_step(&f, &in, CTRL_TS_S);
            if (f.state == ST_PRECHARGE) {
                break;
            }
        }
        in.precharge_done = 1;
        for (n = 0; n < (int)(0.2f / CTRL_TS_S); n++) {
            fsm_step(&f, &in, CTRL_TS_S);
            if (f.state == ST_MPPT_RUN) {
                break;
            }
        }
    }
    check("precharge_done still allows normal progression",
          f.state == ST_MPPT_RUN);
}

int main(void)
{
    printf("pv inverter algorithm tests (Ts=50 us)\n");
    test_pll();
    test_pr();
    test_mppt();
    test_protect();
    test_fsm();
    test_pwm();
    test_deadtime_comp();
    test_il_feedback();
    test_hal_scale();
    test_app_chain();
    test_precharge_guard();

    printf("----\n");
    if (g_fail == 0) {
        printf("SUMMARY PASS  (0 failed)\n");
        return 0;
    }
    printf("SUMMARY FAIL  (%d failed)\n", g_fail);
    return 1;
}
