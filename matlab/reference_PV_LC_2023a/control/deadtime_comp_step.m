function m_comp = deadtime_comp_step(m, i_ref, cfg)
%DEADTIME_COMP_STEP 死区电压误差前馈补偿（控制器正当功能）
%
%   桥臂平均误差：m_eff = m - (2*Td/Tsw)*sign(i_L)
%   补偿：       m_comp = m + (2*Td/Tsw)*s(i_ref)
%
%   两种 s(i_ref)：
%     cfg.i_sat = 0  -> s = sign(i_ref)（旧做法，电流过零处补满）
%     cfg.i_sat > 0  -> s = sat(i_ref / i_sat)（线性过零区）
%   当 |i_ref| < i_sat 时电流在一个开关周期内会改变方向，实际死区误差
%   小于满值；线性过渡可避免过补偿。i_sat 取半个开关纹波峰峰值：
%   L 结构 0.333 A、LC 结构 0.5 A（见 project_params）。
%
%   用**参考电流**而不是实测电流，避免过零噪声/抖动。
%   注意：这是控制器的一部分（与功率级平均死区模型 deadtime_step 不同）；
%   补偿量限幅到 ±m_max，防止与调制限幅叠加后越界。
%   %#codegen

if isfield(cfg,'i_sat') && cfg.i_sat > 0
    s = i_ref / cfg.i_sat;
    if s > 1
        s = 1;
    elseif s < -1
        s = -1;
    end
else
    s = sign(i_ref);
end
m_comp = m + cfg.td_norm*s;
if m_comp > cfg.m_max
    m_comp = cfg.m_max;
elseif m_comp < -cfg.m_max
    m_comp = -cfg.m_max;
end
end
