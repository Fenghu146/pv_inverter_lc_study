function m_eff = deadtime_step(m, iL, cfg)
%DEADTIME_STEP 全桥双极性调制的平均死区电压误差（功率级侧）
%
%   每个开关周期换流时两个桥臂都有死区，平均电压误差：
%       ΔV = 2 * Td/Tsw * Vdc * sign(i_L)
%   归一化到调制比：
%       m_eff = m - 2*Td/Tsw * sign(i_L)
%   本项目 Td=1 us, Tsw=50 us, Vdc=80 V -> Δm=0.04, ΔV=3.2 V。
%
%   注意：这是**功率级/桥臂**的效应，不放在电流控制器里。
%   控制器输出 m 保持干净；若把死区写进控制器，生成 DSP 代码会主动
%   注入畸变。真实的逐开关门极 blanking 见报告“局限”一节。
%
%   cfg.td_norm = 2*Td/Tsw
%   %#codegen

m_eff = m - cfg.td_norm*sign(iL);
end
