function st = ctrl_init()
%CTRL_INIT 电流控制器全部显式状态（PLL + 准PR）
%   %#codegen
st = struct('pll', pll_init(), 'pr', pr_init());
end
