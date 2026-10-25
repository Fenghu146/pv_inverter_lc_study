%% run_sim_tasks_matlab.m —— Simulink 侧 S4 仿真任务 (3 功率点 x L/LC)
%  与 python/sim/run_sim_tasks.py 的 s4() 同工况、同 CSV 列名、同指标口径。
%  输出:
%    data/sim_results_matlab/S4_<PP>_<L|LC>.csv
%    results/tables/sim_summary_matlab.csv
%    matlab/run_sim_tasks_matlab.log (纯 ASCII 进度)
%
%  用法: run_sim_tasks_matlab           (t_end = 0.55 s, 取末 200 ms 做 FFT)
%        run_sim_tasks_matlab(0.3)      (快速验证, 窗口不足会跳过指标)
function run_sim_tasks_matlab(t_end)
    if nargin < 1, t_end = 0.55; end

    here = fileparts(mfilename('fullpath'));
    root = fileparts(here);
    P = jsondecode(fileread(fullfile(root, 'params', 'params.json')));
    mdl = 'pv_inverter_L_LC';
    if ~bdIsLoaded(mdl), load_system(fullfile(here, [mdl '.slx'])); end

    outdir = fullfile(root, 'data', 'sim_results_matlab');
    tabdir = fullfile(root, 'results', 'tables');
    if ~exist(outdir, 'dir'), mkdir(outdir); end
    if ~exist(tabdir, 'dir'), mkdir(tabdir); end

    logf = fopen(fullfile(here, 'run_sim_tasks_matlab.log'), 'w');
    cleanup = onCleanup(@() fclose(logf));

    fs = 1 / 2.5e-6;      % To Workspace 采样率 400 kHz, 与 Python switched 一致
    set_param(mdl, 'StopTime', num2str(t_end));

    rows = struct('power_point', {}, 'irradiance', {}, 'structure', {}, ...
        'P_W_approx', {}, 'thd_pct', {}, 'fund_amp', {}, 'ripple_pp_A', {}, ...
        'ripple_rms_A', {}, 'sw40k_amp', {}, 'sw40k_pct_fund', {}, ...
        'p_out_W', {}, 'i_rms_A', {}, 'vdc_mean_V', {});

    for ip = 1:numel(P.power_points)
        pp = P.power_points(ip);
        iamp = sqrt(2) * pp.P_W_approx / P.rating.U_g_Vrms;
        set_param([mdl '/IrrG'], 'Value', num2str(pp.irradiance));
        set_param([mdl '/IampCmd'], 'Value', num2str(iamp, 8));
        set_param([mdl '/ModeSel'], 'Value', '0');   % fixed_i 模式, 排除 MPPT 扰动

        for st = {'L', 'LC'}
            structure = st{1};
            % 旁路: 电容支路串联开关, 5 V = 导通(LC), 0 V = 断开(L)
            if strcmp(structure, 'LC'), bp = 5; else, bp = 0; end
            set_param([mdl '/BypassCmd'], 'Value', num2str(bp));

            t0 = tic;
            try
                out = sim(mdl, 'ReturnWorkspaceOutputs', 'on');
            catch e
                fprintf(logf, 'SIM FAIL %s/%s: %s\n', pp.id, structure, e.message);
                continue
            end
            wall = toc(t0);

            t  = out.get('sim_iL').Time;
            ig = out.get('sim_ig').Data;
            iL = out.get('sim_iL').Data;
            vdc = out.get('sim_vdc').Data;
            vc = out.get('sim_vc').Data;
            ia = out.get('sim_iamp').Data;

            csv = fullfile(outdir, sprintf('S4_%s_%s.csv', pp.id, structure));
            write_csv(csv, t, ig, iL, vdc, vc, ia, fs);

            n200 = round(0.2 * fs);
            r = struct('power_point', pp.id, 'irradiance', pp.irradiance, ...
                'structure', structure, 'P_W_approx', pp.P_W_approx, ...
                'thd_pct', NaN, 'fund_amp', NaN, 'ripple_pp_A', NaN, ...
                'ripple_rms_A', NaN, 'sw40k_amp', NaN, 'sw40k_pct_fund', NaN, ...
                'p_out_W', NaN, 'i_rms_A', NaN, 'vdc_mean_V', NaN);
            if numel(ig) >= n200
                m = thd_metrics([], ig, fs);
                r.thd_pct = m.thd_pct;
                r.fund_amp = m.fund_amp;
                r.ripple_pp_A = m.ripple_pp;
                r.ripple_rms_A = m.ripple_rms;
                r.sw40k_amp = m.sw40k_amp;
                r.sw40k_pct_fund = m.sw40k_pct_fund;
                tail = ig(end - n200 + 1:end);
                r.i_rms_A = sqrt(mean(tail.^2));
                r.p_out_W = P.rating.U_g_Vrms * r.i_rms_A;
                r.vdc_mean_V = mean(vdc(end - n200 + 1:end));
            end
            rows(end + 1) = r; %#ok<AGROW>

            fprintf(logf, '%-4s %-2s  wall=%5.0fs  thd=%6.2f%%  pp=%7.4fA  a40k=%.5fA (%.4f%%)\n', ...
                pp.id, structure, wall, r.thd_pct, r.ripple_pp_A, ...
                r.sw40k_amp, r.sw40k_pct_fund);
        end
    end

    % ---- 汇总表 ----
    fcsv = fullfile(tabdir, 'sim_summary_matlab.csv');
    fid = fopen(fcsv, 'w');
    fprintf(fid, 'task,key,value\n');
    for k = 1:numel(rows)
        r = rows(k);
        fprintf(fid, 'S4,%s/%s,"%s"\n', r.power_point, r.structure, ...
            strrep(jsonencode(rmfield(r, {})), '"', '""'));
    end
    fclose(fid);

    fprintf(logf, '\n');
    fprintf(logf, '%-4s %-2s %8s %9s %9s %9s\n', 'PP', 'ST', 'THD%', 'ripplePP', 'a40k', 'P_W');
    for k = 1:numel(rows)
        r = rows(k);
        fprintf(logf, '%-4s %-2s %8.2f %9.4f %9.5f %9.2f\n', ...
            r.power_point, r.structure, r.thd_pct, r.ripple_pp_A, r.sw40k_amp, r.p_out_W);
    end
    fprintf(logf, 'DONE -> %s\n', fcsv);
end

function write_csv(path, t, ig, iL, vdc, vc, ia, fs)
    % i_amp 记录在 5e-5 步长上, 需按零阶保持重采样到 400 kHz 主网格
    t = t(:);
    if numel(ia) ~= numel(t)
        ia = interp1((0:numel(ia) - 1)' * 5e-5, ia(:), t, 'previous', 'extrap');
    end
    n = numel(t);
    M = [t, ig(:), iL(:), vdc(:), vc(:), ia(:), repmat(fs, n, 1)];
    fid = fopen(path, 'w');
    fprintf(fid, 't_s,i_g_A,i_L_A,v_dc_V,v_c_V,i_amp_A,fs_Hz\n');
    fmt = [repmat('%.9g,', 1, 6), '%.9g\n'];
    fprintf(fid, fmt, M.');
    fclose(fid);
end
