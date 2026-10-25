/**
 * board.h -- board-level initialisation for the F28379D control card
 *
 * Explicit driverlib equivalent of what SysConfig would generate.
 * Hand-written so the build has no GUI/codegen dependency and every
 * register write is reviewable.
 *
 * Pin/peripheral assignment is documented in pv_inverter.syscfg and must
 * stay in sync with hal_c2000.c.
 */
#ifndef PV_INV_BOARD_H
#define PV_INV_BOARD_H

#ifdef __cplusplus
extern "C" {
#endif

/* From C2000Ware device_support/f2837xd/common/source/device.c */
void Device_init(void);
void Device_initGPIO(void);

/* From C2000Ware driverlib interrupt.c */
void Interrupt_initModule(void);
void Interrupt_initVectorTable(void);

/* Local: analog reference + EPWM clock divider */
void board_init(void);

#ifdef __cplusplus
}
#endif

#endif /* PV_INV_BOARD_H */
