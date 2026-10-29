function cfg = deadtime_comp_mis_cfg()
%DEADTIME_COMP_MIS_CFG 自动生成；0.027 是旧版计数 bug 下的拟合值，仅用于补偿失配敏感性；i_sat=0 为 sign。
%#codegen
cfg = struct('td_norm',0.027, 'i_sat',0, 'm_max',0.94999999999999996);
end
