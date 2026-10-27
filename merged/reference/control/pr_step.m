function [v, st, sat] = pr_step(e, st, cfg)
%PR_STEP 准PR调节器单步更新（biquad + 输出饱和时冻结谐振状态）
%
%   输入：e 电流误差 [A]；st 由 pr_init 产生的状态；cfg 由 pr_design 产生
%   输出：v 调节器输出（调制比）；st 更新后的状态
%
%   抗饱和策略：输出饱和时冻结谐振项状态（不用状态限幅）。
%   理由：谐振器在直流处增益为零，但对状态限幅会制造直流正反馈/假平衡；
%   冻结状态既能防止积分风up，又不会改变谐振器本身的频率特性。
%
%   %#codegen

b0 = cfg.b(1);
b1 = cfg.b(2);
b2 = cfg.b(3);
a1 = cfg.a(2);
a2 = cfg.a(3);

yres  = b0*e + st.s1;          % 谐振项输出
v_raw = cfg.Kp*e + yres;

if v_raw > cfg.vmax
    v = cfg.vmax;
elseif v_raw < -cfg.vmax
    v = -cfg.vmax;
else
    v = v_raw;
end

% 条件冻结：仅当误差仍在把输出往饱和方向推时冻结谐振状态。
% 若误差为零/反向（状态自身越限），仍推进状态，否则会死锁在限幅值。
push_hi = (v_raw > cfg.vmax) && (e > 0);
push_lo = (v_raw < -cfg.vmax) && (e < 0);
if ~(push_hi || push_lo)
    st.s1 = b1*e - a1*yres + st.s2;
    st.s2 = b2*e - a2*yres;
end

sat = (v_raw > cfg.vmax) || (v_raw < -cfg.vmax);
end
