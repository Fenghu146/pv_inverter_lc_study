/**
 * main.c -- C2000 application entry point (F28379D)
 *
 * Responsibilities, in order:
 *   1. device + board initialisation (clock, EPWM clock divider)
 *   2. app_init() to bind the algorithm layer to the HAL
 *   3. 20 kHz EPWM1 period interrupt whose ISR calls app_isr()
 *   4. background loop: watchdog, fault LED
 *
 * Compiled only when __C2000__ is defined.
 */
#include "app.h"
#include "hal.h"
#include "param.h"

#ifdef __C2000__

#include "driverlib.h"
#include "device.h"
#include "board.h"

static App g_app;

__interrupt void epwm1_isr(void)
{
    app_isr(&g_app);
    hal_watchdog_kick();

    EPWM_clearEventTriggerInterruptFlag(EPWM1_BASE);
    Interrupt_clearACKGroup(INTERRUPT_ACK_GROUP3);
}

int main(void)
{
    /* ---- 1. device / board ---- */
    Device_init();
    Device_initGPIO();
    board_init();

    Interrupt_initModule();
    Interrupt_initVectorTable();

    Interrupt_register(INT_EPWM1, epwm1_isr);
    EPWM_setInterruptSource(EPWM1_BASE, EPWM_INT_TBCTR_ZERO);
    EPWM_setInterruptEventCount(EPWM1_BASE, 1);
    EPWM_enableInterrupt(EPWM1_BASE);
    Interrupt_enable(INT_EPWM1);

    /* ---- 2. algorithm + HAL ---- */
    app_init(&g_app, 85.0f);   /* Voc of the PV array, sets P&O start point */

    EINT;
    ERTM;

    /* ---- 3. background ---- */
    for (;;) {
        if (g_app.out.state == ST_FAULT) {
            GPIO_writePin(34u, 1);   /* fault LED, matches hal_c2000.c */
        }
        hal_watchdog_kick();
    }
}

#endif /* __C2000__ */
