function p = project_params()
%PROJECT_PARAMS 全项目唯一参数源（L0~L5 共用）
%   规格以 技术文件2.docx 为准：200 W / 36 Vrms / 50 Hz / Vdc(MPP)=80 V /
%   fsw=20 kHz / L=2 mH / C=12 uF / Rd=1 ohm。修改参数只改本文件。
%
%   注意：Rf 为电感等效串联电阻，Rg 为电网侧电阻，Lg 为隔离变压器漏感
%   （实验室短路试验待测，默认 1 mH，可扫描）。L0 解析与 L3 仿真使用同一组值。

p.P_rated = 200;            % 额定并网功率 [W]
p.Ug_rms  = 36;             % 并网电压有效值 [V]
p.fg      = 50;             % 电网频率 [Hz]
p.wg      = 2*pi*p.fg;
p.fsw     = 20e3;           % 开关频率 [Hz]
p.Ts      = 1e-6;           % 功率级仿真步长 [s]（L5 可改 0.2~0.5 us）
p.Tsc     = 1/p.fsw;        % 控制/采样周期 [s]
p.Td      = 1.5*p.Tsc;      % 数字电流环等效延时（1 拍计算 + 0.5 拍 ZOH）
p.Tsoft   = 0.05;           % 软启动时间 [s]
p.Cdc     = 2200e-6;        % 直流母线电容 [F]
p.Ron_sw  = 0.01;           % 开关导通电阻 [Ohm]
p.Td_pwm  = 1e-6;           % DSP 死区 [s]（理论平均 2*Td/Tsw*Vdc=3.2 V）
p.td_comp_mis = 0.027;      % 失配敏感性用：旧版“计数少一拍 + IGBT 默认
                            % 1/2 us”下拟合出的系数。计数与 IGBT 参数修正后
                            % 有效误差约 3.19 V（0.0399），0.027 只用于演示
                            % 补偿失配，不是标定结果。
p.Vdc     = 80;             % 额定直流母线电压 [V]（L2/L3 直流源）
p.m_max   = 0.95;           % 线性调制区上限（双极性 SPWM）

% ---- 交流侧耦合网络 ----
p.L  = 2.0e-3;              % 串联耦合电感 [H]
p.Rf = 0.05;                % 电感等效串联电阻 [Ohm]
p.C  = 12e-6;               % 并联滤波电容 [F]
p.Rd = 1.0;                 % 电容支路阻尼电阻 [Ohm]
p.Rg = 0.1;                 % 电网等效电阻 [Ohm]
p.Lg = 1.0e-3;              % 电网电感/变压器漏感 [H]（L0 扫描，L3 验证）

% 死区补偿饱和阈值：半个开关纹波峰峰值（过零区宽度）
% dIpp=Vdc/(2*Ltot*fsw)；L 结构 Ltot=L+Lg=3 mH -> 0.667 A pp，
% LC 结构逆变器侧 Ltot=L=2 mH -> 1.000 A pp。补偿在 ±i_sat 内线性，
% 超出后补满；避免在电流过零区按 sign(i_ref) 补满造成过补偿。
p.i_sat_L  = p.Vdc/(4*(p.L+p.Lg)*p.fsw);  % 0.333 A
p.i_sat_LC = p.Vdc/(4*p.L*p.fsw);         % 0.500 A

% ---- 三个实验功率点（技术文件：30-40% / 60-70% / 80-100%） ----
p.P_points = [70 130 200];              % [W]
p.G_points = [400 700 1000];            % 对应光照（L4 用）[W/m^2]
p.Im_ref   = sqrt(2)*p.P_points/p.Ug_rms;   % 单位功率因数电流峰值指令 [A]
p.I_rated_rms = p.P_rated/p.Ug_rms;         % 5.556 A
p.Im_rated    = sqrt(2)*p.I_rated_rms;      % 7.857 A

% ---- L4 PV 面板（单二极管模型，params_design 校准结果） ----
% 标定目标：G=1000 时 Vmp=80.00 V, Imp=2.500 A, Pmp=200.0 W；
% 标定得到 N=1.058, Rs=0.937 Ω（G=400/700 对应 68.4/134.8 W）。
p.pv.Isc = 2.9; p.pv.Voc = 96; p.pv.Nser = 160;
p.pv.N = 1.058; p.pv.Rs = 0.937; p.pv.Rp = 300;
p.pv.Ki = 1.3e-3; p.pv.Tvco = -0.13;

% ---- 电流环 / PLL（L1 冻结设计）----
% 准PR：R(s)=Kp+2*Kr*wc*s/(s^2+2*wc*s+w0^2)，输出为调制比。
% Kp 按 500 Hz 穿越设计；Kr=4 使 50 Hz 环路增益约 518（跟踪误差 0.19%）。
% 冻结裕度：L 对象(L+Lg) PM=49.1°、GM=17.4 dB；LC(LCL,Lg=1mH,Rd=1) PM=49.0°、GM=12.3 dB。
p.Kp_pr   = 2*pi*500*p.L/p.Vdc;   % 0.07854
p.Kr_pr   = 4;
p.f_bw_pr = 2;                    % 谐振项半带宽 [Hz]
p.vmax_pr = 0.9;                  % 调节器输出限幅（调制比）
p.pll.Kp = 0.5;                   % PLL 比例
p.pll.Ki = 30;                    % PLL 积分
p.pll.vq_max   = 20;              % 鉴相器误差限幅 [V]
p.pll.wint_max = 31.4;            % 积分限幅 [rad/s]

% ---- MPPT / 直流电压环（L4）----
% 电压环按 5 Hz 设计：C dV/dt = Ipv - P/V，P=0.5*Ug_pk*Im，
% 小信号 plant ≈ -102/s V/A；Kp=0.6, Ki=8 给出约 5 Hz 带宽。
% 10 ms 滑动平均滤除单相系统 100 Hz 纹波；P&O 判决 0.5 s
% （约 5 倍电压环调节时间），电压搜索下限 58 V。
p.mppt.Kp    = 0.6;         % [A/V]
p.mppt.Ki    = 20;          % [A/(V*s)]，wn≈8.6 Hz, zeta≈0.81
p.mppt.Tp    = 0.5;         % P&O 判决周期 [s]
p.mppt.dV    = 1.0;         % 电压扰动步长 [V]
p.mppt.Vmin  = 58;          % 搜索下限 [V]（审阅建议，非技术文件原文）
p.mppt.Vmax  = 92;          % 搜索上限 [V]（Voc=96 V）
p.mppt.Im_max = 8.5;        % 电流指令上限 [A]（略高于额定 7.86 A）
p.mppt.V0    = 79;          % 初始电压参考 [V]（MPP 约 80 V）
p.pv_V0      = 80;          % 直流母线/PV 初始电压 [V]

% ---- 保护 ----
p.I_trip = 15;              % |i_L| > 15 A 立即停止（规则 8）
end
