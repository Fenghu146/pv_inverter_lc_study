%% compare_matlab_python.m —— Simulink(Simscape) 与 Python 开关级仿真 S4 对照
%  输出: results/tables/sim_compare_matlab_python.csv + compare.log
%  已记录差异: Python PowerStage("L") 支路无 L_g; MATLAB 按《实施方案》L/LC 均保留
%  L_g=0.5mH。故 L 结构等效串联电感 0.5mH vs 1.0mH, 纹波理论差 2 倍。
function compare_matlab_python()
    here = fileparts(mfilename('fullpath'));
    root = fileparts(here);
    f = fopen(fullfile(here, 'compare.log'), 'w');
    cleanup = onCleanup(@() fclose(f));

    py = read_csv_map(fullfile(root, 'results', 'tables', 'sim_summary.csv'), f);
    ml = read_csv_map(fullfile(root, 'results', 'tables', 'sim_summary_matlab.csv'), f);
    fprintf(f, 'py keys=%d  ml keys=%d\n\n', py.Count, ml.Count);

    out = fullfile(root, 'results', 'tables', 'sim_compare_matlab_python.csv');
    fid = fopen(out, 'w');
    fprintf(fid, 'power_point,structure,metric,python,matlab,reldiff_pct,verdict\n');

    fprintf(f, '%-5s %-3s %-14s %10s %10s %9s\n', 'PP', 'ST', 'metric', 'python', 'matlab', 'diff%');
    ks = keys(py);
    for k = 1:numel(ks)
        key = ks{k};
        if ~isKey(ml, key), continue; end
        [pp, st] = strtok(key, '/');
        st = st(2:end);
        a = py(key); b = ml(key);
        mets = {'thd_pct', 'ripple_pp_A', 'sw40k_amp', 'fund_amp', 'i_rms_A', 'p_out_W'};
        for j = 1:numel(mets)
            m = mets{j};
            if ~isfield(a, m) || ~isfield(b, m), continue; end
            va = a.(m); vb = b.(m);
            if ~isfinite(va) || ~isfinite(vb) || va == 0
                rd = NaN;
            else
                rd = 100 * (vb - va) / abs(va);
            end
            fprintf(fid, '%s,%s,%s,%.6g,%.6g,%.3f,%s\n', pp, st, m, va, vb, rd, ...
                verdict(m, st, rd));
            fprintf(f, '%-5s %-3s %-14s %10.4f %10.4f %9.2f\n', pp, st, m, va, vb, rd);
        end
    end
    fclose(fid);

    fprintf(f, '\n--- 说明 ---\n');
    fprintf(f, 'L 结构等效串联电感: python 0.5mH (无 L_g) / matlab 1.0mH (L+L_g)\n');
    fprintf(f, '  -> 开关纹波理论比约 2.0, 故 L 结构 sw40k/ripple 不按 <10%% 判定\n');
    fprintf(f, 'LC 结构两实现均含 L_g, 40kHz 抑制结论可直接对照\n');
    fprintf(f, 'DONE -> %s\n', out);
end

function v = verdict(metric, st, rd)
    if ~isfinite(rd)
        v = 'n/a';
    elseif strcmp(st, 'L') && any(strcmp(metric, {'sw40k_amp', 'ripple_pp_A', 'ripple_rms_A'}))
        v = 'topology-diff';
    elseif abs(rd) <= 10
        v = 'PASS';
    elseif abs(rd) <= 25
        v = 'WARN';
    else
        v = 'DIFF';
    end
end

function M = read_csv_map(path, f)
    M = containers.Map();
    fid = fopen(path, 'r', 'n', 'UTF-8');
    if fid < 0, error('cannot open %s', path); end
    fgetl(fid);
    while true
        ln = fgetl(fid);
        if ~ischar(ln), break; end
        [p1, rest] = strtok(ln, ',');
        if ~strcmp(p1, 'S4'), continue; end
        [key, js] = strtok(rest(2:end), ',');
        key = strrep(key, '"', '');
        js = strtrim(js(2:end));
        js = strrep(js, '""', '"');
        if numel(js) > 1 && js(1) == '"', js = js(2:end - 1); end
        try
            M(key) = jsondecode(js);
        catch e
            fprintf(f, 'parse skip %s: %s\n', key, e.message);
        end
    end
    fclose(fid);
end
