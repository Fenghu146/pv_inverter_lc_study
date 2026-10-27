function cfg = deadtime_comp_cfg_LC()
%DEADTIME_COMP_CFG_LC 自动生成；sat(i_ref/i_sat) 补偿，i_sat=0.5 A（半个开关纹波峰峰值）。
%#codegen
cfg = struct('td_norm',0.040000000000000001, 'i_sat',0.5, 'm_max',0.94999999999999996);
end
