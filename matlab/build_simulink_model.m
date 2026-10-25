function build_simulink_model(doSmoke)
%BUILD_SIMULINK_MODEL  脚本化搭建 L/LC 单相并网逆变器 Simscape 模型
%
%  拓扑: PV(受控电流源+单二极管模型) -> C_dc -> H桥(4x理想开关, 单极性倍频SPWM)
%        -> L(0.5mH + r) -> PCC -> [C 20uF + R_d 串联] / [双反串联旁路开关]
%        -> L_g -> 36Vrms/50Hz 电网
%
%  L 结构 : 旁路开关导通 -> 短接 C+R_d, 只剩 L + L_g
%  LC结构 : 旁路开关关断 -> C+R_d 并入 PCC
%
%  死区: 400ns 以平均电压误差模型注入 (v_err = -2*fsw*td*Vdc*sign(iL)),
%        与 python/sim/inverter_sim.py 开关级模型完全同式。400ns 远小于
%        2us 求解步长, 用 Transport Delay 无法表达, 故采用同式等效。
%
%  用法:  build_simulink_model          搭建 + 编译检查
%         build_simulink_model(true)   搭建 + 编译检查 + 0.02s 冒烟仿真
%
%  输出:  matlab/pv_inverter_L_LC.slx
    if nargin < 1, doSmoke = false; end

    here = fileparts(mfilename('fullpath'));
    root = fileparts(here);
    P = jsondecode(fileread(fullfile(root, 'params', 'params.json')));

    mdl = 'pv_inverter_L_LC';
    if bdIsLoaded(mdl), close_system(mdl, 0); end
    if exist(fullfile(here, [mdl '.slx']), 'file'), delete(fullfile(here, [mdl '.slx'])); end
    new_system(mdl);
    load_system('ee_lib'); load_system('nesl_utility'); load_system('fl_lib');

    set_param(mdl, 'StopTime', '0.35', 'Solver', 'ode23tb', ...
        'MaxStep', '2e-6', 'RelTol', '1e-4', 'AbsTol', '1e-6');

    f_sw   = P.switching.f_sw_Hz;
    t_dead = P.switching.t_dead_ns * 1e-9;
    Lf     = P.plant.L_H;
    Cf     = P.plant.C_F;
    Rd     = P.plant.R_d_default_ohm;
    Lg     = P.plant.L_g_H;
    Cdc    = P.plant.C_dc_F;
    r_par  = P.plant.R_parasitic_ohm;
    Ug_pk  = P.rating.U_g_Vrms * sqrt(2);
    f_g    = P.rating.f_g_Hz;
    V_mpp  = P.rating.V_mpp_V;

    % ===================== 主电路 =====================
    add_block('fl_lib/Electrical/Electrical Sources/Controlled Current Source', ...
        [mdl '/PV'], 'Position', [60 300 120 360]);
    add_block('ee_lib/Passive/Capacitor', [mdl '/Cdc'], 'Position', [180 240 230 300]);
    set_param([mdl '/Cdc'], 'c', num2str(Cdc, 12));
    set_param([mdl '/Cdc'], 'vc_specify', 'on', 'vc', num2str(V_mpp));

    sw = 'ee_lib/Semiconductors & Converters/Ideal Semiconductor Switch';
    add_block(sw, [mdl '/S1'], 'Position', [320 90 380 130]);
    add_block(sw, [mdl '/S2'], 'Position', [320 210 380 250]);
    add_block(sw, [mdl '/S3'], 'Position', [320 380 380 420]);
    add_block(sw, [mdl '/S4'], 'Position', [320 500 380 540]);
    for k = 1:4
        set_param(sprintf('%s/S%d', mdl, k), 'diode_param', ...
            'ee.enum.semiconductors.protectionDiode.nodynamics');
    end

    add_block('ee_lib/Sensors & Transducers/Current Sensor', [mdl '/CS_L'], ...
        'Position', [440 210 490 250]);
    add_block('ee_lib/Passive/Inductor', [mdl '/Lf'], 'Position', [540 210 600 250]);
    set_param([mdl '/Lf'], 'l', num2str(Lf, 12));
    add_block('ee_lib/Passive/Resistor', [mdl '/rL'], 'Position', [640 210 690 250]);
    set_param([mdl '/rL'], 'R', num2str(r_par, 12));

    add_block('ee_lib/Passive/Capacitor', [mdl '/Cf'], 'Position', [760 360 810 400]);
    set_param([mdl '/Cf'], 'c', num2str(Cf, 12));
    add_block('ee_lib/Passive/Resistor', [mdl '/Rd'], 'Position', [760 450 810 490]);
    % R_d=0 时用 1mΩ 占位(远小于 Z0=5Ω), 避免零阻回路造成刚性
    set_param([mdl '/Rd'], 'R', num2str(max(Rd, 1e-3), 12));

    add_block(sw, [mdl '/Sbp1'], 'Position', [900 350 960 390]);
    add_block(sw, [mdl '/Sbp2'], 'Position', [900 440 960 480]);
    set_param([mdl '/Sbp1'], 'diode_param', 'ee.enum.semiconductors.protectionDiode.nodynamics');
    set_param([mdl '/Sbp2'], 'diode_param', 'ee.enum.semiconductors.protectionDiode.nodynamics');

    add_block('ee_lib/Passive/Inductor', [mdl '/Lg'], 'Position', [720 120 780 160]);
    set_param([mdl '/Lg'], 'l', num2str(Lg, 12));
    add_block('ee_lib/Sensors & Transducers/Current Sensor', [mdl '/CS_g'], ...
        'Position', [830 120 880 160]);
    add_block('ee_lib/Sources/Programmable Voltage Source', [mdl '/Vg'], ...
        'Position', [940 90 1000 170]);
    set_param([mdl '/Vg'], 'dc_voltage', '0', ...
        'ac_magnitude', num2str(Ug_pk, 10), 'ac_frequency', num2str(f_g));

    add_block('ee_lib/Sensors & Transducers/Voltage Sensor', [mdl '/VS_dc'], ...
        'Position', [180 150 230 200]);
    add_block('ee_lib/Sensors & Transducers/Voltage Sensor', [mdl '/VS_c'], ...
        'Position', [760 260 810 310]);
    add_block('ee_lib/Sensors & Transducers/Voltage Sensor', [mdl '/VS_g'], ...
        'Position', [940 200 990 250]);

    add_block('nesl_utility/Solver Configuration', [mdl '/SC'], 'Position', [60 470 140 510]);
    add_block('ee_lib/Connectors & References/Electrical Reference', [mdl '/REF'], ...
        'Position', [60 560 120 590]);

    % ===================== PS 转换 =====================
    ps2s('PSiL',  [540 320], 'A');
    ps2s('PSig',  [830 210], 'A');
    ps2s('PSvdc', [180 90],  'V');
    ps2s('PSvc',  [860 250], 'V');
    ps2s('PSvg',  [1010 250], 'V');
    ps2p('PSipv', [60 390],  'A');

    ps2p('G1', [250 90],  'V');
    ps2p('G2', [250 210], 'V');
    ps2p('G3', [250 380], 'V');
    ps2p('G4', [250 500], 'V');
    ps2p('Gb1', [860 300], 'V');
    ps2p('Gb2', [860 600], 'V');

    % ===================== 控制 =====================
    add_block('simulink/User-Defined Functions/MATLAB Function', [mdl '/PVmodel'], ...
        'Position', [80 640 180 700]);
    add_block('simulink/User-Defined Functions/MATLAB Function', [mdl '/Ctrl'], ...
        'Position', [320 640 420 720]);
    add_block('simulink/User-Defined Functions/MATLAB Function', [mdl '/Mod'], ...
        'Position', [540 640 640 700]);

    add_block('simulink/Sources/Constant', [mdl '/IrrG'], 'Position', [80 750 140 780], ...
        'Value', num2str(P.power_points(3).irradiance), 'SampleTime', 'inf');
    add_block('simulink/Sources/Constant', [mdl '/IampCmd'], 'Position', [80 800 140 830], ...
        'Value', num2str(sqrt(2) * P.rating.P_n_W / P.rating.U_g_Vrms, 6), 'SampleTime', 'inf');
    add_block('simulink/Sources/Constant', [mdl '/ModeSel'], 'Position', [80 850 140 880], ...
        'Value', '0', 'SampleTime', 'inf');
    add_block('simulink/Sources/Constant', [mdl '/BypassCmd'], 'Position', [860 640 920 670], ...
        'Value', '5', 'SampleTime', 'inf');

    % 采样保持 (20kHz 控制环 / 400kHz PWM)
    zoh('Zv',  [240 700], '5e-5');
    zoh('Zi',  [240 740], '5e-5');
    zoh('Zvdc',[240 780], '5e-5');
    zoh('Zm',  [480 700], '2.5e-6');
    zoh('Zi2', [480 740], '2.5e-6');
    % 一拍延时(2.5us) = 数字控制器采样保持延迟, 同时切断
    % Mod -> 门极 -> Simscape -> 传感器 -> 控制 的代数环
    ud('UDiL',  [500 380], '2.5e-6');
    ud('UDvdc', [230 130], '2.5e-6');
    % 门极一拍延时: 彻底断开 PWM -> 桥臂 -> 电流 -> PWM 的代数环
    ud('UDg1', [270 100], '2.5e-6');
    ud('UDg2', [270 220], '2.5e-6');
    ud('UDg3', [270 390], '2.5e-6');
    ud('UDg4', [270 510], '2.5e-6');

    % ===================== 记录 =====================
    tw('TW_ig',   [560 350], 'sim_ig',  '2.5e-6');
    tw('TW_iL',   [560 400], 'sim_iL',  '2.5e-6');
    tw('TW_vdc',  [270 80],  'sim_vdc', '2.5e-6');
    tw('TW_vc',   [860 200], 'sim_vc',  '2.5e-6');
    tw('TW_ipv',  [150 400], 'sim_ipv', '2.5e-6');
    tw('TW_iamp', [430 640], 'sim_iamp','5e-5');
    tw('TW_m',    [660 640], 'sim_m',   '5e-5');

    % ===================== 物理网络 (链式) =====================
    % 端口约定 (实测): 理想开关 LConn1 = 门极(PS), RConn1/RConn2 = 功率端
    % 1) 直流正母线 DCP
    net({LC('PV',1), LC('Cdc',1), RC('S1',1), RC('S3',1), LC('VS_dc',1)});
    % 2) 直流负母线 DCN
    net({RC('PV',2), RC('Cdc',1), RC('S2',2), RC('S4',2), RC('VS_dc',2), ...
         LC('REF',1), RC('SC',1)});
    % 3) 桥臂 A 中点
    net({RC('S1',2), RC('S2',1), LC('CS_L',1)});
    % 4) 逆变侧电感串
    net({RC('CS_L',2), LC('Lf',1)});
    net({RC('Lf',1), LC('rL',1)});
    % 5) PCC 节点
    net({RC('rL',1), RC('Sbp1',1), LC('Lg',1), LC('VS_c',1)});
    % 6) 旁路双反串联 (与 C+R_d 支路串联): 导通=LC, 关断=L
    %    两只开关体二极管相对, 关断时双向阻断, 从而真正"断开"电容支路
    net({RC('Sbp1',2), RC('Sbp2',2)});
    net({RC('Sbp2',1), LC('Cf',1)});
    net({RC('Cf',1), LC('Rd',1)});
    % 7) 桥臂 B 中点 / 公共回线
    net({RC('S3',2), RC('S4',1), RC('Rd',1), RC('Vg',1), ...
         RC('VS_c',2), RC('VS_g',2)});
    % 8) 网侧电感 + 电流传感器
    net({RC('Lg',1), LC('CS_g',1)});
    net({RC('CS_g',2), LC('Vg',1), LC('VS_g',1)});

    % 传感器 / 门极 PS 口
    % 注: Simulink-PS Converter 的物理口在 RConn1; PS-Simulink Converter 在 LConn1
    net({RC('CS_L',1), LC('PSiL',1)});
    net({RC('CS_g',1), LC('PSig',1)});
    net({RC('VS_dc',1), LC('PSvdc',1)});
    net({RC('VS_c',1), LC('PSvc',1)});
    net({RC('VS_g',1), LC('PSvg',1)});
    net({RC('PV',1), RC('PSipv',1)});          % PV 的 PS 控制口在 RConn1
    net({RC('G1',1), LC('S1',1)});
    net({RC('G2',1), LC('S2',1)});
    net({RC('G3',1), LC('S3',1)});
    net({RC('G4',1), LC('S4',1)});
    net({RC('Gb1',1), LC('Sbp1',1)});
    net({RC('Gb2',1), LC('Sbp2',1)});

    % ===================== 代码 (须在信号连线前设置: 端口随代码重排) =====================
    setcode('PVmodel', code_pv());
    setcode('Ctrl', code_ctrl(f_sw, t_dead));
    setcode('Mod', code_mod(f_sw, t_dead));
    setdisc('Ctrl', '5e-5');
    setdisc('Mod', '2.5e-6');

    % ===================== Simulink 连线 =====================
    sig('PSvdc/1', 'Zvdc/1');
    sig('PSvg/1', 'Zv/1');
    sig('PSiL/1', 'UDiL/1');       % 一拍延时: 切断 门极->桥->电流传感器->PWM 代数环
    sig('UDiL/1', 'Zi/1');    sig('Zvdc/1', 'PVmodel/1');
    sig('IrrG/1', 'PVmodel/2');
    sig('PVmodel/1', 'PSipv/1');

    sig('Zv/1',   'Ctrl/1');
    sig('Zi/1',   'Ctrl/2');
    sig('Zvdc/1', 'Ctrl/3');
    sig('IampCmd/1', 'Ctrl/4');
    sig('IrrG/1', 'Ctrl/5');
    sig('ModeSel/1', 'Ctrl/6');

    sig('Ctrl/1', 'Zm/1');
    sig('Zi/1',   'Zi2/1');
    sig('Zm/1',   'Mod/1');
    sig('Zi2/1',  'Mod/2');

    sig('Mod/1', 'UDg1/1');
    sig('Mod/2', 'UDg2/1');
    sig('Mod/3', 'UDg3/1');
    sig('Mod/4', 'UDg4/1');
    sig('UDg1/1', 'G1/1');
    sig('UDg2/1', 'G2/1');
    sig('UDg3/1', 'G3/1');
    sig('UDg4/1', 'G4/1');
    sig('BypassCmd/1', 'Gb1/1');
    sig('BypassCmd/1', 'Gb2/1');

    sig('PSiL/1',  'TW_iL/1');
    sig('PSig/1',  'TW_ig/1');
    sig('PSvdc/1', 'TW_vdc/1');
    sig('PSvc/1',  'TW_vc/1');
    sig('PVmodel/1', 'TW_ipv/1');
    sig('Ctrl/2',  'TW_iamp/1');
    sig('Ctrl/1',  'TW_m/1');

    % ===================== 保存 / 编译 =====================
    save_system(mdl, fullfile(here, [mdl '.slx']));
    fprintf('MODEL SAVED: %s\n', fullfile(here, [mdl '.slx']));

    ok = true;
    try
        set_param(mdl, 'SimulationCommand', 'update');
        fprintf('COMPILE OK\n');
    catch e
        ok = false;
        fprintf('COMPILE FAIL: %s\n', e.message);
    end

    if ok && doSmoke
        try
            set_param(mdl, 'StopTime', '0.02');
            t0 = tic;
            out = sim(mdl, 'ReturnWorkspaceOutputs', 'on');
            fprintf('SMOKE OK: %.1f s wall\n', toc(t0));
            show(out, 'sim_vdc', 'Vdc');
            show(out, 'sim_ipv', 'Ipv');
            show(out, 'sim_iL',  'iL');
            show(out, 'sim_ig',  'ig');
        catch e
            fprintf('SMOKE FAIL: %s\n', e.message);
        end
    end

    % ---------------- 嵌套函数 ----------------
    function h = LC(name, i)
        h = get_param([mdl '/' name], 'PortHandles').LConn(i);
    end
    function h = RC(name, i)
        h = get_param([mdl '/' name], 'PortHandles').RConn(i);
    end
    function net(ports)
        for q = 1:numel(ports) - 1
            add_line(mdl, ports{q}, ports{q + 1}, 'autorouting', 'on');
        end
    end
    function sig(a, b)
        add_line(mdl, a, b, 'autorouting', 'on');
    end
    function ps2s(name, pos, unit)
        add_block('nesl_utility/PS-Simulink Converter', [mdl '/' name], ...
            'Position', [pos(1) pos(2) pos(1) + 50 pos(2) + 20]);
        set_param([mdl '/' name], 'Unit', unit);
    end
    function ps2p(name, pos, unit)
        add_block('nesl_utility/Simulink-PS Converter', [mdl '/' name], ...
            'Position', [pos(1) pos(2) pos(1) + 50 pos(2) + 20]);
        set_param([mdl '/' name], 'Unit', unit);
    end
    function zoh(name, pos, st)
        add_block('simulink/Discrete/Zero-Order Hold', [mdl '/' name], ...
            'Position', [pos(1) pos(2) pos(1) + 40 pos(2) + 30]);
        set_param([mdl '/' name], 'SampleTime', st);
    end
    function ud(name, pos, st)
        add_block('simulink/Discrete/Unit Delay', [mdl '/' name], ...
            'Position', [pos(1) pos(2) pos(1) + 40 pos(2) + 30]);
        set_param([mdl '/' name], 'SampleTime', st, 'InitialCondition', '0');
    end
    function tw(name, pos, varname, st)
        add_block('simulink/Sinks/To Workspace', [mdl '/' name], ...
            'Position', [pos(1) pos(2) pos(1) + 60 pos(2) + 30]);
        set_param([mdl '/' name], 'VariableName', varname, ...
            'SaveFormat', 'Timeseries', 'SampleTime', st);
    end
    function setcode(name, code)
        rt = sfroot;
        ch = rt.find('-isa', 'Stateflow.EMChart', 'Path', [mdl '/' name]);
        if isempty(ch)
            error('MATLAB Function block not found: %s', [mdl '/' name]);
        end
        ch.Script = code;
    end
    function setdisc(name, st)
        % 显式离散采样时间: 既是真实数字控制器的行为, 也彻底切断代数环
        rt = sfroot;
        ch = rt.find('-isa', 'Stateflow.EMChart', 'Path', [mdl '/' name]);
        if isempty(ch), return; end
        ch.ChartUpdate = 'DISCRETE';
        ch.SampleTime = st;
        if ~strcmp(ch.ChartUpdate, 'DISCRETE')
            fprintf('WARN: %s ChartUpdate=%s\n', name, ch.ChartUpdate);
        end
    end
    function show(out, vn, lbl)
        try
            s = out.get(vn);
            d = s.Data(:);
            fprintf('  %-5s mean=%8.3f  min=%8.3f  max=%8.3f  end=%8.3f\n', ...
                lbl, mean(d), min(d), max(d), d(end));
        catch e
            fprintf('  %s read ERR: %s\n', vn, e.message);
        end
    end
end

% ===================== 生成代码 =====================
function s = code_pv()
s = join([
"function ipv = pv_current(vdc, G)"
"%#codegen"
"% 单二极管模型, 与 python/sim/pv_model.py 完全一致"
"Iph = 2.9; I0 = 4.05e-8; nVT = 4.95;"
"ipv = G*Iph - I0*(exp(vdc/nVT) - 1.0);"
], newline);
end

function s = code_mod(f_sw, t_dead)
s = join([
"function [g1, g2, g3, g4] = pwm(m, il)"
"%#codegen"
"% 单极性倍频 SPWM + 死区平均电压误差 (与 inverter_sim.py 同式)"
"persistent cnt"
"if isempty(cnt)"
"    cnt = 0;"
"end"
sprintf("fsw = %.10g; td = %.10g;", f_sw, t_dead)
sprintf("N = %d;", round(1 / (f_sw * 2.5e-6)))
"sgn = 1 - 2*(il < 0);"
"meff = m - 2*fsw*td*sgn;"
"if meff > 0.999, meff = 0.999; end"
"if meff < -0.999, meff = -0.999; end"
"carrier = 2*abs(cnt/N - 0.5);"
"duty = 0.5*(1 + meff);"
"sa = double(duty > carrier);"
"sb = double((1 - duty) > carrier);"
"g1 = sa; g2 = 1 - sa; g3 = sb; g4 = 1 - sb;"
"cnt = cnt + 1;"
"if cnt >= N"
"    cnt = 0;"
"end"
], newline);
end

function s = code_ctrl(f_sw, t_dead)
s = join([
"function [m, iamp] = ctrl(vg, il, vdc, iamp_cmd, G, mode)"
"%#codegen"
"% SOGI-PLL + 准PR(Tustin预畸变) + 电压环PI + P&O, 与 control_algos.py 同参数"
"Ts = 5e-5;"
"persistent th ia ib wq pii y1 y2 e1 e2 vint cnt pacc pn vref lastp dirp iampp init"
"if isempty(init)"
"    th = 0; ia = 0; ib = 0; wq = 2*pi*50; pii = 0;"
"    y1 = 0; y2 = 0; e1 = 0; e2 = 0; vint = 0;"
"    cnt = 0; pacc = 0; pn = 0; vref = 0.8*90; lastp = -1; dirp = 1; iampp = 0;"
"    init = 1;"
"end"
"w0 = 2*pi*50; ks = 1.41; kpp = 0.67; kip = 22; Um = 36*sqrt(2);"
"kppr = 4.7; kr = 300; wc = 5;"
"kpv = 0.2; kiv = 5; imin = 0; imax = 10;"
"dv = 0.5; vmin = 62; vmax = 75;"
sprintf("fsw = %.10g; td = %.10g; mlim = 0.95;", f_sw, t_dead)
"Iph = 2.9; I0 = 4.05e-8; nVT = 4.95;"
"kk = w0/tan(w0*Ts/2);"
"a0 = kk*kk + 2*wc*kk + w0*w0;"
"b0 = 2*kr*wc*kk/a0;"
"b2 = -2*kr*wc*kk/a0;"
"a1 = (-2*kk*kk + 2*w0*w0)/a0;"
"a2 = (kk*kk - 2*wc*kk + w0*w0)/a0;"
"% ---- SOGI-PLL ----"
"ia = ia + Ts*(ks*wq*(vg - ia) - wq*ib);"
"ib = ib + Ts*(wq*ia);"
"vq = ia*cos(th) + ib*sin(th);"
"vqn = vq/Um;"
"pii = pii + kip*vqn*Ts;"
"wq = w0 + kpp*vqn + pii;"
"th = th + wq*Ts;"
"if th > 2*pi"
"    th = th - 2*pi;"
"end"
"% ---- 电流幅值指令 ----"
"if mode < 0.5"
"    iampp = iamp_cmd;"
"else"
"    ipv = G*Iph - I0*(exp(vdc/nVT) - 1.0);"
"    pacc = pacc + vdc*ipv; pn = pn + 1;"
"    if mod(cnt, 20) == 0"
"        err = vdc - vref;"
"        o = kpv*err + vint;"
"        if ~((o >= imax && err > 0) || (o <= imin && err < 0))"
"            vint = vint + kiv*err*20*Ts;"
"        end"
"        iampp = kpv*err + vint;"
"        if iampp > imax, iampp = imax; end"
"        if iampp < imin, iampp = imin; end"
"    end"
"    if mod(cnt, 2000) == 0 && pn > 0"
"        pavg = pacc/pn;"
"        if lastp >= 0"
"            if pavg - lastp < 0"
"                dirp = -dirp;"
"            end"
"            vref = vref + dirp*dv;"
"            if vref > vmax, vref = vmax; end"
"            if vref < vmin, vref = vmin; end"
"        end"
"        lastp = pavg; pacc = 0; pn = 0;"
"    end"
"end"
"iamp = iampp;"
"% ---- 准PR 电流环 + 电网前馈 + 死区补偿 ----"
"iref = iamp*sin(th);"
"e = iref - il;"
"y = b0*e + b2*e2 - a1*y1 - a2*y2;"
"e2 = e1; e1 = e; y2 = y1; y1 = y;"
"u = kppr*e + y + vg;"
"u = u + 2*fsw*td*vdc*(1 - 2*(il < 0));"
"vdcs = vdc;"
"if vdcs < 10, vdcs = 10; end"
"lim = mlim*vdcs;"
"if u > lim, u = lim; end"
"if u < -lim, u = -lim; end"
"m = u/vdcs;"
"cnt = cnt + 1;"
"if cnt >= 2000"
"    cnt = 0;"
"end"
], newline);
end
