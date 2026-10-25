/**
 * board.c -- board-level initialisation for F28379D (CPU1)
 *
 * Explicit driverlib equivalent of what SysConfig would generate.
 * Hand-written so the build has no GUI/codegen dependency and every
 * register write is reviewable.
 *
 * Clock tree:
 *   XTAL 20 MHz -> PLL -> PLLSYSCLK 200 MHz
 *   EPWMCLK = PLLSYSCLK / 2 = 100 MHz   (matches PWM_CLK_HZ in param.h)
 *
 * DEVICE_SETCLOCK_CFG and DEVICE_OSCSRC_FREQ come from the C2000Ware
 * example device support for this board; if the crystal on the actual
 * LaunchPad differs, change both here and PWM_CLK_HZ/PWM_TBPRD together.
 */
#include "board.h"
#include "driverlib.h"
#include "device.h"

void board_init(void)
{
    /* ePWM clock: PLLSYSCLK/2 = 100 MHz.
     * This must match PWM_CLK_HZ in param.h -- TBPRD and the dead-band
     * count are both derived from it. A mismatch silently shifts the
     * switching frequency and the dead time. */
    SysCtl_setEPWMClockDivider(SYSCTL_EPWMCLK_DIV_2);
}
