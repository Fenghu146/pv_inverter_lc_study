function [m, m_cmd, vpr, i_ref, sin_ref, sat] = ctrl_step_LC(iL, ug, vdc, Im_ref, soft)
%CTRL_STEP_LC 供 Simulink MATLAB Function 块调用的 LC 结构包装
%   与 ctrl_step_L 唯一的区别是电容电流前馈（cfg.is_lc=true）。
%   %#codegen

persistent st mprev
if isempty(st)
    st = ctrl_init();
    mprev = 0;
end
cfg = cfg_LC();
[m_cmd, vpr, i_ref, sin_ref, ~, sat, st] = ...
    current_ctrl_step(iL, ug, vdc, Im_ref, soft, st, cfg);
m = mprev;
mprev = m_cmd;
end
