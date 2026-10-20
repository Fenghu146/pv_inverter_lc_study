%% process_scope_csv.m —— 实测/仿真 CSV 批处理 (统一口径 6.3/7.4)
%  输入: data 目录下 CSV (列: t_s, i_g_A, ... , fs_Hz 或由参数指定 fs)
%  输出: results/tables/thd_ripple_summary.csv + 对比图
%  用法: process_scope_csv('data/experiments', 5e6)
%  说明: 调用 thd_metrics.m, 与 python/analysis/metrics.py 同口径
function T = process_scope_csv(datadir, fs_default)
    if nargin < 2, fs_default = 5e6; end
    files = dir(fullfile(datadir, '*.csv'));
    if isempty(files)
        error('目录中无 CSV: %s', datadir);
    end
    Name = {}; THD = []; RIP = []; SW40 = []; Fund = [];
    for k = 1:numel(files)
        d = readmatrix(fullfile(files(k).folder, files(k).name));
        hdr = fileread(fullfile(files(k).folder, files(k).name));
        first = splitlines(hdr); first = first{1};
        cols = split(first, ',');
        i_g = d(:, 2);                              % 第2列固定为 i_g_A
        fs = fs_default;
        idx = find(strcmpi(strtrim(cols), 'fs_Hz'), 1);
        if ~isempty(idx), fs = d(1, idx); end
        m = thd_metrics([], i_g, fs);
        Name{end+1,1} = files(k).name;              %#ok<AGROW>
        THD(end+1,1) = m.thd_pct;                   %#ok<AGROW>
        RIP(end+1,1) = m.ripple_pp;                 %#ok<AGROW>
        SW40(end+1,1) = m.sw40k_pct_fund;           %#ok<AGROW>
        Fund(end+1,1) = m.fund_amp;                 %#ok<AGROW>
    end
    T = table(Name, THD, RIP, SW40, Fund);
    out = fullfile('..', 'results', 'tables', 'thd_ripple_summary.csv');
    writetable(T, out);
    disp(T);
    fprintf('汇总已写出: %s\n', out);
end
