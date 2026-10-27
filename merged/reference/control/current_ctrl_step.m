function [m, vpr, i_ref, sin_ref, Uamp, sat, st] = current_ctrl_step(iL, ug, vdc, Im_ref, ss, st, cfg)
%CURRENT_CTRL_STEP 单相并网电流控制器单步（DSP 同款结构）
%
%   输入：
%     iL      逆变器侧电感电流采样 [A]
%     ug      电网电压采样 [V]
%     vdc     直流母线电压 [V]
%     Im_ref  并网电流峰值指令 [A]
%     ss      软启动系数 0..1
%     st      ctrl_init 产生的状态
%     cfg     ctrl_cfg 产生的配置
%   输出：
%     m       调制比指令（已限幅到 ±m_max）
%     vpr     PR 调节器输出（用于限幅监测）
%     i_ref   电流参考（含 LC 电容电流前馈）
%     sin_ref PLL 正弦参考
%     Uamp    电网电压幅值估计
%     sat     [PR限幅; 调制限幅; PLL限幅] 逻辑向量
%     st      更新后的状态
%
%   控制对象是逆变器侧电流 i_L。LC 结构额外加电容电流前馈
%   i_C ≈ wg*C*Uamp*cos(theta)，使并网电流 i_g 与指令同相；
%   电流环参数与 L 结构完全相同，只增加一个前馈项。
%
%   %#codegen

[sin_ref, cos_ref, Uamp, st.pll, sat_pll] = pll_step(ug, st.pll, cfg.pll);

i_ref = ss*Im_ref*sin_ref;
if cfg.is_lc
    i_ref = i_ref + ss*cfg.C*cfg.wg*Uamp*cos_ref;
end

e = i_ref - iL;
[vpr, st.pr, sat_pr] = pr_step(e, st.pr, cfg.pr);

vff = ss*ug/max(vdc, cfg.vdc_min);
m_raw = vpr + vff;
if m_raw > cfg.m_max
    m = cfg.m_max;
elseif m_raw < -cfg.m_max
    m = -cfg.m_max;
else
    m = m_raw;
end

sat_m = (m_raw > cfg.m_max) || (m_raw < -cfg.m_max);
sat = [sat_pr, sat_m, sat_pll];
end
