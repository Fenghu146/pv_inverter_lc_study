"""统一数据分析口径 —— 对齐实施方案 6.3 / 7.4
- THD: 2~50 次谐波, 200ms 窗口(10个工频周期), 频率分辨率 5Hz
- 高频纹波: >5kHz 高通后峰峰值
- 40kHz(2f_sw)分量幅值及占基波百分比
同一套函数同时用于仿真 CSV 与实测 CSV。
"""
import numpy as np
from scipy.signal import butter, filtfilt

FG = 50.0           # 工频 Hz
WINDOW_MS = 200.0   # THD 窗口
H_MIN, H_MAX = 2, 50
HP_CUTOFF = 5000.0  # 纹波高通截止
RIPPLE_FREQ = 40000.0  # 2f_sw


def _window(x, fs, window_ms=WINDOW_MS):
    n = int(round(window_ms / 1000.0 * fs))
    if len(x) < n:
        raise ValueError(f"信号长度 {len(x)} < 窗口所需 {n}")
    return x[-n:]


def thd(x, fs, window_ms=WINDOW_MS, h_min=H_MIN, h_max=H_MAX):
    """按 GB/T 与 IEEE 1547 口径: THD = sqrt(ΣU_h²)/U_1, h=2..50"""
    w = _window(x, fs, window_ms)
    N = len(w)
    freqs = np.fft.rfftfreq(N, 1.0 / fs)
    spec = np.abs(np.fft.rfft(w * np.hanning(N))) * 2.0 / np.sum(np.hanning(N))
    df = fs / N
    hz = freqs / FG

    def harm(h):
        idx = int(round(h * FG / df))
        lo, hi = max(0, idx - 1), min(len(spec), idx + 2)
        return spec[lo:hi].max() if len(spec) else 0.0

    u1 = harm(1)
    if u1 <= 0:
        return {"thd_pct": np.nan, "u1": 0.0}
    s = sum(harm(h) ** 2 for h in range(h_min, h_max + 1))
    return {"thd_pct": 100.0 * np.sqrt(s) / u1, "u1": u1, "df_Hz": df}


def ripple(x, fs, cutoff=HP_CUTOFF, window_ms=WINDOW_MS):
    """高通(>cutoff)后峰峰值"""
    w = _window(x, fs, window_ms)
    b, a = butter(4, cutoff / (fs / 2.0), "high")
    hp = filtfilt(b, a, w)
    return {"ripple_pp": float(hp.max() - hp.min()), "ripple_rms": float(np.sqrt(np.mean(hp ** 2)))}


def switching_component(x, fs, f_sw2=RIPPLE_FREQ, window_ms=WINDOW_MS, band_hz=500.0):
    """2f_sw 开关纹波簇幅值及占基波百分比
    注意: 开关纹波被工频调幅, 频谱为 2f_sw±k·50Hz 边带, 故取 ±band_hz 内峰值"""
    w = _window(x, fs, window_ms)
    N = len(w)
    win = np.hanning(N)
    spec = np.abs(np.fft.rfft(w * win)) * 2.0 / np.sum(win)
    freqs = np.fft.rfftfreq(N, 1.0 / fs)

    def band_max(f0, half=band_hz):
        sel = (freqs >= f0 - half) & (freqs <= f0 + half)
        return float(spec[sel].max()) if sel.any() else 0.0

    u1 = band_max(FG, half=15.0)
    u_sw = band_max(f_sw2)
    return {"f_sw2_Hz": f_sw2, "u_sw2": u_sw, "u1": u1,
            "sw2_pct_of_fund": 100.0 * u_sw / u1 if u1 > 0 else np.nan}


def full_metrics(x, fs, window_ms=WINDOW_MS):
    """完整口径: THD + 纹波 + 40kHz 分量 (方案6.3)"""
    t = thd(x, fs, window_ms)
    r = ripple(x, fs, window_ms=window_ms)
    s = switching_component(x, fs, window_ms=window_ms)
    return {
        "thd_pct": t["thd_pct"],
        "fund_amp": t["u1"],
        "ripple_pp_A": r["ripple_pp"],
        "ripple_rms_A": r["ripple_rms"],
        "sw40k_amp": s["u_sw2"],
        "sw40k_pct_fund": s["sw2_pct_of_fund"],
    }
