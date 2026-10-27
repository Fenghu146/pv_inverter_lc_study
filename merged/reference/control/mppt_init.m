function st = mppt_init(V0)
%MPPT_INIT P&O + 直流电压 PI 的显式状态
%   V0 可选：初始电压参考（远起点测试用 62/90 V）；缺省 cfg.V0。
%   10 ms 滑动平均在 20 kHz 下为 200 点；Nma=200 与 mppt_cfg 一致。
%   %#codegen
if nargin < 1
    cfg = mppt_cfg();
    V0 = cfg.V0;
end
st = struct( ...
    'vbuf', zeros(1,200), 'ibuf', zeros(1,200), ...
    'idx', 1, 'vsum', 0, 'isum', 0, ...
    'cnt', 0, 'Vref', V0, 'dir', 1, ...
    'Pprev', -1e9, 'integ', 0, 'first', true);
end
