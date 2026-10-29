function cfg = deadtime_cfg()
%DEADTIME_CFG 自动生成，请勿手改；由 make_cfg_const.m 从 project_params 生成。
%#codegen
% 全桥双极性：每个换流两个桥臂都有死区，Δm=2*Td/Tsw
cfg = struct('td_norm',0.040000000000000001, 'm_max',0.94999999999999996);
end
