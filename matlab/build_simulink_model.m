%% build_simulink_model.m —— 依据实施方案 6.1 搭建 Simulink 主电路模型
%  工具: MATLAB R2026b + Simscape Electrical (原生 ee_lib, R2026b 已无经典 SPS 库)
%  拓扑: PV → C_dc → 单相H桥(理想开关+死区) → 耦合网络(L或LC, Variant Subsystem 切换)
%        → L_g + 36V/50Hz 交流源
%  用法: 在 MATLAB 中运行: build_simulink_model
%  输出: 光伏并网逆变器_L_LC对比.slx (参数来自 params/params.json)
%  注意: 本脚本创建基础模型框架与参数配置; 模块端口连线需在 Simulink 中微调验证后运行
function build_simulink_model()
    % 读取统一参数
    pj = fileread(fullfile('..', 'params', 'params.json'));
    P = jsondecode(pj);

    model = '光伏并网逆变器_L_LC对比';
    if bdIsLoaded(model), close_system(model, 0); end
    new_system(model);
    open_system(model);
    set_param(model, 'StopTime', '0.5', 'MaxStep', '2e-6', ...
        'Solver', 'ode23tb', 'RelTol', '1e-4');

    % ---- 参数加载到 base workspace (供模块引用) ----
    assignin('base', 'V_mpp', P.rating.V_mpp_V);
    assignin('base', 'P_n',   P.rating.P_n_W);
    assignin('base', 'U_g',   P.rating.U_g_Vrms);
    assignin('base', 'f_g',   P.rating.f_g_Hz);
    assignin('base', 'f_sw',  P.switching.f_sw_Hz);
    assignin('base', 't_dead', P.switching.t_dead_ns * 1e-9);
    assignin('base', 'L_c',   P.plant.L_H);
    assignin('base', 'C_f',   P.plant.C_F);
    assignin('base', 'R_d',   P.plant.R_d_default_ohm);
    assignin('base', 'L_g',   P.plant.L_g_H);
    assignin('base', 'C_dc',  P.plant.C_dc_F);

    % ---- 说明: R2026b 无经典 SPS 库(powerlib/sps_lib), 用 Simscape Electrical 原生库 ----
    % ee_lib 位置: ee_lib/Sources, ee_lib/Passive, ee_lib/Semiconductors & Converters
    % 建议搭建步骤(在 Simulink 界面完成, 本脚本建框架与注释):
    add_block('simulink/Sources/Constant', [model '/I_amp_ref'], 'Value', '7.86', ...
        'Position', [40 40 120 80]);
    add_block('simulink/Sinks/Scope', [model '/i_g_scope'], 'Position', [700 40 760 90]);
    add_block('simulink/Sinks/Scope', [model '/v_dc_scope'], 'Position', [700 120 760 170]);

    % ---- 模型说明注释 ----
    note = sprintf(['主电路(Simscape Electrical 原生库搭建):\n' ...
        '1. PV: ee_lib/Sources/Solar Cell (Voc=90V Isc=2.9A Vmpp=75V)\n' ...
        '2. C_dc = 4.5mF: ee_lib/Passive/Capacitor\n' ...
        '3. H桥: ee_lib/Semiconductors & Converters (MOSFET理想开关, 单极性倍频SPWM, 死区400ns)\n' ...
        '4. 耦合网络 Variant Subsystem:\n' ...
        '   变体L: L=0.5mH 串联\n' ...
        '   变体LC: L=0.5mH + (C=20uF 串 R_d=0/1/2.2) 并联到PCC\n' ...
        '5. L_g=0.5mH + 36V/50Hz 电压源\n' ...
        '6. 控制: 离散子系统 50us (SOGI-PLL + PR电流环 + 电压环PI + P&O)\n' ...
        '   与 dsp/src 的 C 代码同参数 (params/params.json)\n' ...
        '7. FFT/THD 分析: 用 matlab/thd_metrics.m 或 python/analysis/metrics.py\n' ...
        '   (R2026b 无经典 powergui, 分析走脚本口径)');
    add_block('built-in/Note', [model '/搭建说明'], 'Position', [40 220 520 420], ...
        'Text', note);

    save_system(model, fullfile(pwd, [model '.slx']));
    fprintf('模型框架已保存: %s\n', fullfile(pwd, [model '.slx']));
    fprintf('请在 Simulink 中按注释完成 ee_lib 模块连线, 然后运行仿真;\n');
    fprintf('分析统一调用 matlab/thd_metrics.m (与 Python 口径一致)。\n');
end
