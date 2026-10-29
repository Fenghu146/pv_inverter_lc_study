function [m, m_cmd, vpr, i_ref, sin_ref, sat] = ctrl_step_L(iL, ug, vdc, Im_ref, soft)
%CTRL_STEP_L 供 Simulink MATLAB Function 块调用的 L 结构包装
%   1 拍计算延时在包装函数内实现（m 输出上一拍计算值，m_cmd 输出本拍值），
%   避免 Simulink Unit Delay 的采样时间歧义；算法本体在 current_ctrl_step。
%   %#codegen

persistent st mprev
if isempty(st)
    st = ctrl_init();
    mprev = 0;
end
cfg = cfg_L();
[m_cmd, vpr, i_ref, sin_ref, ~, sat, st] = ...
    current_ctrl_step(iL, ug, vdc, Im_ref, soft, st, cfg);
m = mprev;
mprev = m_cmd;
end
