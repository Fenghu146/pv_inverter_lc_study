/**
 * protect.h — 软件保护判断
 *
 * 输入一拍测量，输出故障位标志（见 param.h FAULT_*）。
 * 过流 / 母线过欠压带短确认时间；交流有效值、频率、PLL 失锁由调用方
 * 给出已计算量（rms、Hz、|vq|_pu 与连续失锁标志）。
 */
#ifndef PV_INV_PROTECT_H
#define PV_INV_PROTECT_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float i_g;          /* 并网电流瞬时值，A（取绝对值比较） */
    float i_hard;       /* 硬件过流比较器镜像，A；无则传 |i_g| */
    float vdc;          /* 母线电压，V */
    float vac_rms;      /* 交流电压有效值，V */
    float freq_hz;      /* 估计电网频率，Hz */
    int   pll_unlocked; /* 非 0：PLL 已判定失锁 */
    int   grid_check_en;/* 非 0：才判交流范围 / 频率 / PLL */
    int   uv_mask;      /* 非 0：屏蔽母线欠压（预充前母线本来就在 0 V） */
} ProtectIn;

typedef struct {
    float oc_soft_s;
    float oc_hard_s;
    float ov_s;
    float uv_s;
    uint32_t latched;   /* 保持，直到 protect_clear / protect_try_clear */
    uint32_t active;    /* 本拍新判定（含已锁存） */
    uint32_t current;   /* 本拍"仍然存在"的条件（不带确认时间、不锁存） */
} ProtectState;

void protect_init(ProtectState *p);
void protect_clear(ProtectState *p);
/**
 * 复位锁存，但只在本拍故障条件已经消失时才允许。
 * 返回 1=已复位；0=条件仍在，拒绝复位（调用方应维持 FAULT 状态）。
 *
 * 2026-11-03 SITL 故障注入发现：原来 protect_clear 只在 protect_init 里调用，
 * clear_fault 之后 latched 仍非零 → 状态机回 INIT 的下一拍立刻再进 FAULT，
 * 故障永远恢复不了（现场只能断电重启）。这个函数补上安全复位路径。
 */
int protect_try_clear(ProtectState *p);
uint32_t protect_step(ProtectState *p, const ProtectIn *in, float ts);

#ifdef __cplusplus
}
#endif

#endif
