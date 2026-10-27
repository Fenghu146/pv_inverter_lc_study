function M = analyze_ig(t, x, ug, p)
%ANALYZE_IG 并网电流稳态指标：基波幅值/相位、THD、TDD、直流分量、高频纹波
%
%   输入 t,x,ug 为等间隔采样（建议控制周期 20 kHz 或记录率 200 kHz），
%   自动截取整数个工频周期（从 t(1) 起）。
%
%   返回：
%     I1        基波幅值 [A]
%     phase_deg i_g 相对 u_g 的相位 [deg]
%     Idc       直流分量 [A]
%     THD       2..50 次谐波畸变率（相对基波）[%]
%     TDD       以额定电流为基准的畸变率 [%]
%     HF_rms    >2 kHz 高频纹波有效值 [A]
%     HF_pct    高频纹波 / 基波有效值 [%]
%     SW_rms    15..25 kHz 开关频段纹波有效值 [A]
%     P_ac      并网有功 [W]

p.fg = p.fg;                        %#ok<*NASGU>
Tg = 1/p.fg;
Ncyc = floor((t(end)-t(1))/Tg);
if Ncyc < 1
    error('analyze_ig: 窗口不足一个工频周期');
end
tend = t(1) + Ncyc*Tg;
idx = (t >= t(1)) & (t < tend);
tt = t(idx); xx = x(idx); uu = ug(idx);
N = numel(xx);
dt = tt(2)-tt(1);
fs = 1/dt;
w = 2*pi*p.fg;

% 基波（整周期矩形窗）
X = 2*sum(xx.*exp(-1j*w*tt))/N;
U = 2*sum(uu.*exp(-1j*w*tt))/N;
M.I1 = abs(X);
M.phase_deg = wrapdeg(angle(X) - angle(U));
M.Idc = mean(xx);

% FFT 谐波
Y = abs(fft(xx))/N*2;
fax = (0:N-1)'*fs/N;
fb = round(p.fg*N/fs);
if fb < 1 || 50*fb > floor(N/2)
    error('analyze_ig: 频率分辨率不足');
end
I1 = Y(fb+1);
harm = Y(2*fb+1 : 50*fb+1);
M.THD = 100*sqrt(sum(harm.^2))/I1;
% TDD 的分子必须是谐波有效值；Y 是峰值，故除以 sqrt(2)。
% 额定点 I1/sqrt(2)=I_rated_rms，因此 TDD 应与 THD 相等。
M.TDD = 100*(sqrt(sum(harm.^2))/sqrt(2))/p.I_rated_rms;

% 高频纹波（单边谱，非直流/奈奎斯特 bin）
kHF = fax > 2e3 & fax < fs/2;
M.HF_rms = sqrt(sum(Y(kHF).^2)/2);
M.HF_pct = 100*M.HF_rms/(I1/sqrt(2));
kSW = fax > 15e3 & fax < 25e3;
M.SW_rms = sqrt(sum(Y(kSW).^2)/2);

% 有功
M.P_ac = mean(uu.*xx);
end

function d = wrapdeg(a)
d = mod(a*180/pi + 180, 360) - 180;
end
