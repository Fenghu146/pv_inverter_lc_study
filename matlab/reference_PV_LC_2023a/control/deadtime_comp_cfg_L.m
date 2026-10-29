function cfg = deadtime_comp_cfg_L()
%DEADTIME_COMP_CFG_L 自动生成；sat(i_ref/i_sat) 补偿，i_sat=0.3333 A（半个开关纹波峰峰值）。
%#codegen
cfg = struct('td_norm',0.040000000000000001, 'i_sat',0.33333333333333331, 'm_max',0.94999999999999996);
end
