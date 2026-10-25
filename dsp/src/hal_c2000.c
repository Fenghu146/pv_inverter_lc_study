/**
 * hal_c2000.c -- HAL implementation for TI C2000 F28379D (SysConfig + driverlib)
 *
 * Compile guard: defines __C2000__.
 *
 * This is the ONLY file in the project that touches registers.
 *
 * Channel map (must match dsp/ccs/pv_inverter.syscfg and dsp/include/hal.h):
 *
 *   ADC-A  A0  V_pv     divider 100 V -> 3 V        (unipolar)
 *          A1  I_pv     0.1 V/A, 1.5 V offset
 *          A2  V_dc     divider 100 V -> 3 V        (unipolar)
 *          A3  V_g      bipolar +-60 V -> 1.5 V +- 1.5 V
 *   ADC-B  B0  I_L      0.1 V/A, 1.5 V offset   <-- current-loop feedback
 *          B1  I_g      0.1 V/A, 1.5 V offset   <-- protection / metering
 *
 *   All channels are triggered by EPWM1 SOCA at carrier peak (20 kHz).
 *
 *   EPWM1 A/B -> leg A (S1 high / S2 low)
 *   EPWM2 A/B -> leg B (S3 high / S4 low)
 *   Both modules: 20 kHz up-down carrier, TBPRD = PWM_TBPRD, phase 0,
 *   EPWM2 syncs from EPWM1 SYNCOUT so the two legs stay locked.
 *
 *   Dead band: DB submodule on EPWMxA generates the complementary EPWMxB,
 *   RED = FED = DEADTIME_COUNTS (400 ns at 100 MHz).
 *
 *   CMPSS1: high comparator on the I_L conditioning node. Threshold set by
 *   DAC to OC_HARD_A. Output routed through EPWM XBAR to TRIP4, which drives
 *   the one-shot trip zone of both EPWM modules.
 *
 *   Trip is LATCHED in hardware. Only hal_clear_trip() (called from the
 *   manual-reset path) releases it.
 */
#include "hal.h"
#include "param.h"

#ifdef __C2000__

#include "driverlib.h"
#include "device.h"

/* ---- peripheral bases (from SysConfig) ---- */
#define PWM_A_BASE      EPWM1_BASE    /* leg A: S1 high / S2 low */
#define PWM_B_BASE      EPWM2_BASE    /* leg B: S3 high / S4 low */
#define ADC_A_BASE      ADCA_BASE     /* V_pv / I_pv / V_dc / V_g */
#define ADC_B_BASE      ADCB_BASE     /* I_L / I_g */
#define TRIP_CMPSS_BASE CMPSS1_BASE   /* hardware over-current comparator */

/* ---- GPIO map (must match SysConfig) ---- */
#define GPIO_RELAY      32u   /* grid contactor */
#define GPIO_PRECHARGE  33u   /* pre-charge bypass */
#define GPIO_FAULT_LED  34u   /* fault indicator */
#define GPIO_RUN_LED    35u   /* run indicator */

#define ADC_SOC_VPV     ADC_SOC_NUMBER0
#define ADC_SOC_IPV     ADC_SOC_NUMBER1
#define ADC_SOC_VDC     ADC_SOC_NUMBER2
#define ADC_SOC_VG      ADC_SOC_NUMBER3
#define ADC_SOC_IL      ADC_SOC_NUMBER0
#define ADC_SOC_IG      ADC_SOC_NUMBER1

#define ADC_SAMPLE_WINDOW  15u

static int g_trip = 0;

/* ---------------- GPIO ---------------- */
static void init_gpio(void)
{
    GPIO_setPadConfig(GPIO_RELAY, GPIO_PIN_TYPE_STD);
    GPIO_setDirectionMode(GPIO_RELAY, GPIO_DIR_MODE_OUT);
    GPIO_writePin(GPIO_RELAY, 0);

    GPIO_setPadConfig(GPIO_PRECHARGE, GPIO_PIN_TYPE_STD);
    GPIO_setDirectionMode(GPIO_PRECHARGE, GPIO_DIR_MODE_OUT);
    GPIO_writePin(GPIO_PRECHARGE, 0);

    GPIO_setPadConfig(GPIO_FAULT_LED, GPIO_PIN_TYPE_STD);
    GPIO_setDirectionMode(GPIO_FAULT_LED, GPIO_DIR_MODE_OUT);
    GPIO_writePin(GPIO_FAULT_LED, 0);

    GPIO_setPadConfig(GPIO_RUN_LED, GPIO_PIN_TYPE_STD);
    GPIO_setDirectionMode(GPIO_RUN_LED, GPIO_DIR_MODE_OUT);
    GPIO_writePin(GPIO_RUN_LED, 0);
}

/* ---------------- ePWM ---------------- */
static void init_epwm(uint32_t base, int is_slave)
{
    /* Time base: up-down, TBPRD = 2500 -> 20 kHz at 100 MHz EPWMCLK */
    EPWM_setClockPrescaler(base, EPWM_CLOCK_DIVIDER_1, EPWM_HSCLOCK_DIVIDER_1);
    EPWM_setTimeBasePeriod(base, PWM_TBPRD);
    EPWM_setPhaseShift(base, 0);

    /* EPWM2 follows EPWM1 so the two legs never drift.
     * On F2837xD the SYNCI of EPWM2 is hardwired to EPWM1SYNCOUT --
     * there is no per-module sync-input selection register (only EPWM4/7/10
     * have one, via SYNCSELECT). So EPWM1 emits SYNCOUT at counter zero and
     * EPWM2 locks to it automatically. */
    if (!is_slave) {
        EPWM_setSyncOutPulseMode(base, EPWM_SYNC_OUT_PULSE_ON_COUNTER_ZERO);
        EPWM_setCountModeAfterSync(base, EPWM_COUNT_MODE_UP_AFTER_SYNC);
    } else {
        EPWM_setCountModeAfterSync(base, EPWM_COUNT_MODE_UP_AFTER_SYNC);
    }

    /* Action qualifier on EPWMxA:
     *   CTR = 0        (up)   -> SET
     *   CTR = CMPA     (up)   -> CLEAR
     *   CTR = CMPA     (down) -> SET
     *   CTR = TBPRD    (down) -> CLEAR
     * => high time = 2*CMPA out of 2*TBPRD, i.e. duty = CMPA / TBPRD */
    EPWM_setActionQualifierAction(base, EPWM_AQ_OUTPUT_A,
                                  EPWM_AQ_OUTPUT_HIGH,
                                  EPWM_AQ_OUTPUT_ON_TIMEBASE_ZERO);
    EPWM_setActionQualifierAction(base, EPWM_AQ_OUTPUT_A,
                                  EPWM_AQ_OUTPUT_LOW,
                                  EPWM_AQ_OUTPUT_ON_TIMEBASE_UP_CMPA);
    EPWM_setActionQualifierAction(base, EPWM_AQ_OUTPUT_A,
                                  EPWM_AQ_OUTPUT_HIGH,
                                  EPWM_AQ_OUTPUT_ON_TIMEBASE_DOWN_CMPA);
    EPWM_setActionQualifierAction(base, EPWM_AQ_OUTPUT_A,
                                  EPWM_AQ_OUTPUT_LOW,
                                  EPWM_AQ_OUTPUT_ON_TIMEBASE_PERIOD);

    /* Dead band: complementary EPWMxB derived from EPWMxA.
     * Both edges delayed so neither device can be on early. */
    EPWM_setDeadBandDelayMode(base, EPWM_DB_RED, true);
    EPWM_setDeadBandDelayMode(base, EPWM_DB_FED, true);
    EPWM_setRisingEdgeDelayCount(base, (uint16_t)DEADTIME_COUNTS);
    EPWM_setFallingEdgeDelayCount(base, (uint16_t)DEADTIME_COUNTS);
    EPWM_setDeadBandDelayPolarity(base, EPWM_DB_RED, EPWM_DB_POLARITY_ACTIVE_HIGH);
    EPWM_setDeadBandDelayPolarity(base, EPWM_DB_FED, EPWM_DB_POLARITY_ACTIVE_HIGH);
    EPWM_setDeadBandOutputSwapMode(base, EPWM_DB_OUTPUT_A, false);
    EPWM_setDeadBandCounterClock(base, EPWM_DB_COUNTER_CLOCK_FULL_CYCLE);

    /* Start at 50 % so the first ISR sees a defined bridge voltage */
    EPWM_setCounterCompareValue(base, EPWM_COUNTER_COMPARE_A,
                                (uint16_t)(PWM_TBPRD / 2u));

    /* ADC SOC at carrier peak (TBCTR = TBPRD).
     * Sampling at the peak keeps away from the switching edges. */
    EPWM_setADCTriggerSource(base, EPWM_SOC_A, EPWM_SOC_TBCTR_PERIOD);
    EPWM_setADCTriggerEventPrescale(base, EPWM_SOC_A, 1);
    EPWM_enableADCTrigger(base, EPWM_SOC_A);

    EPWM_setTimeBaseCounterMode(base, EPWM_COUNTER_MODE_UP_DOWN);
}

/* ---------------- ADC ---------------- */
static void init_adc(void)
{
    ADC_setInterruptPulseMode(ADC_A_BASE, ADC_PULSE_END_OF_CONV);
    ADC_setupSOC(ADC_A_BASE, ADC_SOC_VPV, ADC_TRIGGER_EPWM1_SOCA,
                 ADC_CH_ADCIN0, ADC_SAMPLE_WINDOW);
    ADC_setupSOC(ADC_A_BASE, ADC_SOC_IPV, ADC_TRIGGER_EPWM1_SOCA,
                 ADC_CH_ADCIN1, ADC_SAMPLE_WINDOW);
    ADC_setupSOC(ADC_A_BASE, ADC_SOC_VDC, ADC_TRIGGER_EPWM1_SOCA,
                 ADC_CH_ADCIN2, ADC_SAMPLE_WINDOW);
    ADC_setupSOC(ADC_A_BASE, ADC_SOC_VG, ADC_TRIGGER_EPWM1_SOCA,
                 ADC_CH_ADCIN3, ADC_SAMPLE_WINDOW);

    ADC_setInterruptPulseMode(ADC_B_BASE, ADC_PULSE_END_OF_CONV);
    ADC_setupSOC(ADC_B_BASE, ADC_SOC_IL, ADC_TRIGGER_EPWM1_SOCA,
                 ADC_CH_ADCIN0, ADC_SAMPLE_WINDOW);
    ADC_setupSOC(ADC_B_BASE, ADC_SOC_IG, ADC_TRIGGER_EPWM1_SOCA,
                 ADC_CH_ADCIN1, ADC_SAMPLE_WINDOW);

    ADC_enableConverter(ADC_A_BASE);
    ADC_enableConverter(ADC_B_BASE);
}

/* ---------------- CMPSS + TripZone ---------------- */
static void init_cmpss_trip(void)
{
    /* High comparator, DAC threshold = OC_HARD_A.
     * LATCHED output: once the threshold is crossed the trip stays asserted
     * until software clears the CMPSS latch -- that is what makes the
     * over-current protection fail-safe rather than transient. */
    CMPSS_enableModule(TRIP_CMPSS_BASE);
    CMPSS_configHighComparator(TRIP_CMPSS_BASE, CMPSS_INSRC_DAC);
    CMPSS_configOutputsHigh(TRIP_CMPSS_BASE, CMPSS_TRIP_LATCH);
    CMPSS_setDACValueHigh(TRIP_CMPSS_BASE, (uint16_t)(4095.0f *
        (SENSE_I_OFFSET_V + OC_HARD_A / SENSE_I_GAIN_A_PER_V) / ADC_VREF_V));

    /* Digital filter: 8 samples over threshold before tripping.
     * 8 / 20 kHz = 400 us -- far faster than the 2 ms software path,
     * but rejects a single switching spike. */
    CMPSS_configFilterHigh(TRIP_CMPSS_BASE, 0u, 8u, 8u);
    CMPSS_initFilterHigh(TRIP_CMPSS_BASE);

    /* Route CMPSS1 CTRIPH to EPWM XBAR TRIP4 */
    XBAR_setEPWMMuxConfig(XBAR_TRIP4, XBAR_EPWM_MUX00_CMPSS1_CTRIPH);
    XBAR_enableEPWMMux(XBAR_TRIP4, XBAR_MUX00);

    /* One-shot trip on both legs.
     * TZA -> LOW  (high-side off)
     * TZB -> HIGH (low-side on, so the inductor has a free-wheeling path) */
    EPWM_enableTripZoneSignals(PWM_A_BASE, EPWM_TZ_SIGNAL_OSHT4);
    EPWM_enableTripZoneSignals(PWM_B_BASE, EPWM_TZ_SIGNAL_OSHT4);
    EPWM_setTripZoneAction(PWM_A_BASE, EPWM_TZ_ACTION_EVENT_TZA, EPWM_TZ_ACTION_LOW);
    EPWM_setTripZoneAction(PWM_A_BASE, EPWM_TZ_ACTION_EVENT_TZB, EPWM_TZ_ACTION_HIGH);
    EPWM_setTripZoneAction(PWM_B_BASE, EPWM_TZ_ACTION_EVENT_TZA, EPWM_TZ_ACTION_LOW);
    EPWM_setTripZoneAction(PWM_B_BASE, EPWM_TZ_ACTION_EVENT_TZB, EPWM_TZ_ACTION_HIGH);
}

/* ---------------- HAL API ---------------- */
void hal_init(void)
{
    init_gpio();
    init_epwm(PWM_A_BASE, 0);
    init_epwm(PWM_B_BASE, 1);
    init_adc();
    init_cmpss_trip();

    g_trip = 0;
    hal_pwm_enable(0);
    hal_relay(0);
    hal_precharge(0);
}

void hal_read_adc_raw(unsigned short raw[6])
{
    raw[0] = ADC_readResult(ADCARESULT_BASE, ADC_SOC_VPV);
    raw[1] = ADC_readResult(ADCARESULT_BASE, ADC_SOC_IPV);
    raw[2] = ADC_readResult(ADCARESULT_BASE, ADC_SOC_VDC);
    raw[3] = ADC_readResult(ADCARESULT_BASE, ADC_SOC_VG);
    raw[4] = ADC_readResult(ADCBRESULT_BASE, ADC_SOC_IL);
    raw[5] = ADC_readResult(ADCBRESULT_BASE, ADC_SOC_IG);
}

/* ---- offset calibration ----
 * g_off is the value in force; g_acc accumulates during the CAL window.
 * Keeping them separate matters: if the running sum were used directly the
 * offset would grow to thousands of volts within the 50 ms window. */
static float g_off_iL = SENSE_I_OFFSET_V;
static float g_off_ig = SENSE_I_OFFSET_V;
static float g_acc_iL;
static float g_acc_ig;
static int   g_acc_n;

void hal_raw_to_si(const unsigned short raw[6], HalMeas *m)
{
    const float lsb = ADC_VREF_V / ADC_FULL_SCALE;

    m->v_pv   = (float)raw[0] * lsb * SENSE_V_DIV;
    m->i_pv   = ((float)raw[1] * lsb - g_off_iL) * SENSE_I_GAIN_A_PER_V;
    m->vdc    = (float)raw[2] * lsb * SENSE_V_DIV;
    m->v_grid = ((float)raw[3] * lsb - SENSE_VAC_OFFSET_V) * SENSE_VAC_DIV;
    m->i_L    = ((float)raw[4] * lsb - g_off_iL) * SENSE_I_GAIN_A_PER_V;
    m->i_g    = ((float)raw[5] * lsb - g_off_ig) * SENSE_I_GAIN_A_PER_V;
}

void hal_calibrate_offset(const unsigned short raw[6])
{
    const float lsb = ADC_VREF_V / ADC_FULL_SCALE;

    g_acc_iL += (float)raw[4] * lsb;
    g_acc_ig += (float)raw[5] * lsb;
    g_acc_n++;
}

void hal_calibrate_finish(void)
{
    if (g_acc_n > 0) {
        g_off_iL = g_acc_iL / (float)g_acc_n;
        g_off_ig = g_acc_ig / (float)g_acc_n;
    }
    g_acc_iL = 0.0f;
    g_acc_ig = 0.0f;
    g_acc_n = 0;
}

void hal_pwm_apply(unsigned cmpa_a, unsigned cmpa_b)
{
    EPWM_setCounterCompareValue(PWM_A_BASE, EPWM_COUNTER_COMPARE_A,
                                (uint16_t)cmpa_a);
    EPWM_setCounterCompareValue(PWM_B_BASE, EPWM_COUNTER_COMPARE_A,
                                (uint16_t)cmpa_b);
}

void hal_pwm_enable(int on)
{
    if (on) {
        /* Release the software force; output follows AQ again.
         * Trip flags are deliberately untouched here -- only
         * hal_clear_trip() may release a hardware trip. */
        EPWM_setActionQualifierContSWForceAction(PWM_A_BASE, EPWM_AQ_OUTPUT_A,
                                                 EPWM_AQ_SW_DISABLED);
        EPWM_setActionQualifierContSWForceAction(PWM_B_BASE, EPWM_AQ_OUTPUT_A,
                                                 EPWM_AQ_SW_DISABLED);
    } else {
        /* Normal stop: force EPWMxA low, DB pulls EPWMxB high.
         * => high-side off, low-side on, v_ab = 0, no switching.
         * Cannot use an OST here: that shares the latch with the real
         * hardware fault, and the fault would then be indistinguishable. */
        EPWM_setActionQualifierContSWForceAction(PWM_A_BASE, EPWM_AQ_OUTPUT_A,
                                                 EPWM_AQ_SW_OUTPUT_LOW);
        EPWM_setActionQualifierContSWForceAction(PWM_B_BASE, EPWM_AQ_OUTPUT_A,
                                                 EPWM_AQ_SW_OUTPUT_LOW);
    }
}

void hal_relay(int close)
{
    GPIO_writePin(GPIO_RELAY, close ? 1 : 0);
    GPIO_writePin(GPIO_RUN_LED, close ? 1 : 0);
}

void hal_precharge(int on)
{
    GPIO_writePin(GPIO_PRECHARGE, on ? 1 : 0);
}

int hal_trip_latched(void)
{
    /* OST4 is the one wired to CMPSS1 via EPWM XBAR */
    if (EPWM_getTripZoneFlagStatus(PWM_A_BASE) & EPWM_TZ_FLAG_OST) {
        g_trip = 1;
        GPIO_writePin(GPIO_FAULT_LED, 1);
    }
    return g_trip;
}

void hal_clear_trip(void)
{
    g_trip = 0;
    GPIO_writePin(GPIO_FAULT_LED, 0);
    EPWM_clearOneShotTripZoneFlag(PWM_A_BASE, EPWM_TZ_OST_FLAG_OST4);
    EPWM_clearOneShotTripZoneFlag(PWM_B_BASE, EPWM_TZ_OST_FLAG_OST4);
    EPWM_clearTripZoneFlag(PWM_A_BASE, EPWM_TZ_FLAG_OST);
    EPWM_clearTripZoneFlag(PWM_B_BASE, EPWM_TZ_FLAG_OST);
    /* Also release the latched CMPSS output, otherwise the trip
     * re-asserts the moment the flags are cleared. */
    CMPSS_clearFilterLatchHigh(TRIP_CMPSS_BASE);
}

void hal_stub_set_raw(const unsigned short raw[6])
{
    (void)raw;   /* not a target-board entry point */
}

void hal_watchdog_kick(void)
{
    SysCtl_serviceWatchdog();
}

#endif /* __C2000__ */
