function st = pll_init()
%PLL_INIT 单相T/4延时PLL的显式状态
%   控制周期 50 us（20 kHz）时 T/4 = 5 ms = 100 拍。
%   若控制频率改变，需同步修改 buf 长度。
%   %#codegen
st = struct('buf', zeros(1,100), 'idx', 1, 'th', 0, 'wint', 0);
end
