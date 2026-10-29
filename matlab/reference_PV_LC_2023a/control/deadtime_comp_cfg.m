function cfg = deadtime_comp_cfg()
%DEADTIME_COMP_CFG 自动生成；sign(i_ref) 补偿，i_sat=0 表示不饱和。
%#codegen
cfg = struct('td_norm',0.040000000000000001, 'i_sat',0, 'm_max',0.94999999999999996);
end
