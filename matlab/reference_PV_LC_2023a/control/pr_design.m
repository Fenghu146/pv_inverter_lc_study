function cfg = pr_design(Kp, Kr, f_bw, f0, Ts)
%PR_DESIGN 标准准PR调节器的预畸变Tustin离散化（二阶差分方程/biquad）
%
%   R(s) = Kp + 2*Kr*wc*s / (s^2 + 2*wc*s + w0^2)
%
%   输入：
%     Kp   比例增益（调节器输出为调制比 m，故单位为 1/A）
%     Kr   谐振增益（50 Hz 处 R(jw0) = Kp + Kr）
%     f_bw 谐振项半带宽 [Hz]，wc = 2*pi*f_bw
%     f0   谐振频率 [Hz]（50 Hz）
%     Ts   控制周期 [s]（50 us）
%   输出：
%     cfg.Kp, cfg.b=[b0 b1 b2], cfg.a=[1 a1 a2], cfg.vmax
%
%   离散化：s = k*(1-z^-1)/(1+z^-1)，k = w0/tan(w0*Ts/2)（50 Hz 预畸变），
%   保证离散后 50 Hz 处幅值/相位与连续域严格一致。
%   差分方程（Direct Form II Transposed）：
%     y[n] = b0*e[n] + s1[n-1]
%     s1[n] = b1*e[n] - a1*y[n] + s2[n-1]
%     s2[n] = b2*e[n] - a2*y[n]
%
%   %#codegen

w0 = 2*pi*f0;
wc = 2*pi*f_bw;
k  = w0/tan(w0*Ts/2);

D0 = k^2 + 2*wc*k + w0^2;
D1 = -2*k^2 + 2*w0^2;
D2 = k^2 - 2*wc*k + w0^2;
N0 = 2*Kr*wc*k;
N2 = -2*Kr*wc*k;

cfg.Kp = Kp;
cfg.b  = [N0/D0, 0, N2/D0];
cfg.a  = [1, D1/D0, D2/D0];
cfg.vmax = 10;          % 默认不限幅；电流环里由调用者设为 0.9
end
