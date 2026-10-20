%% thd_metrics.m —— 统一数据分析口径 (对齐实施方案 6.3 / 7.4)
%  输入: t(可为空), x (列向量), fs 采样率
%  输出: thd_pct (2~50次谐波), ripple_pp (>5kHz高通峰峰值), sw40k_pct (40kHz簇占基波%)
%  用法: m = thd_metrics([], i_g, fs)
%  说明: 与 python/analysis/metrics.py 同口径; 仅用 base MATLAB
%        (本机无 Signal Processing Toolbox, 窗函数与高通均以 FFT 方式实现;
%         ripple_pp 采用 FFT 谱零化高通, 与 Python 的 4 阶 Butterworth
%         filtfilt 结果略有差异, THD 与 sw40k 口径完全一致)
function m = thd_metrics(t, x, fs) %#ok<INUSD>
    FG = 50;                 % 工频
    WIN_MS = 200;            % 窗口 200ms = 10 工频周期
    H_MIN = 2; H_MAX = 50;   % 谐波范围
    HP_CUTOFF = 5000;        % 纹波高通截止
    F_SW2 = 40000;           % 2f_sw 开关纹波簇
    BAND = 500;              % 簇带宽

    x = x(:);
    n = round(WIN_MS/1000*fs);
    if numel(x) < n
        error('信号长度不足 200ms 窗口');
    end
    w = x(end-n+1:end);
    N = numel(w);
    win = 0.5 - 0.5*cos(2*pi*(0:N-1)'/(N-1));   % Hann (手写, 无工具箱依赖)
    spec = abs(fft(w .* win)) * 2 / sum(win);
    f = (0:N-1)' * (fs/N);

    % 簇带内峰值 (工频调幅 → 40kHz±k·50Hz 边带)
    band_max = @(f0, half) max(spec(f >= f0-half & f <= f0+half));

    % THD: 2~50次谐波
    u1 = band_max(FG, 15);
    s = 0;
    for h = H_MIN:H_MAX
        s = s + band_max(h*FG, 15)^2;
    end
    m.thd_pct = 100 * sqrt(s) / u1;
    m.fund_amp = u1;

    % 高频纹波: FFT 谱零化高通(>HP_CUTOFF)后峰峰值 (正/镜像两端都要清零)
    W = fft(w);
    fW = (0:N-1)' * (fs/N);
    W(fW < HP_CUTOFF | fW > fs - HP_CUTOFF) = 0;
    hp = real(ifft(W));
    m.ripple_pp = max(hp) - min(hp);
    m.ripple_rms = sqrt(mean(hp.^2));

    % 40kHz 开关纹波簇
    m.sw40k_amp = band_max(F_SW2, BAND);
    m.sw40k_pct_fund = 100 * m.sw40k_amp / u1;
end
