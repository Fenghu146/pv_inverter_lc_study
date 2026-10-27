function [sin_ref, cos_ref, Uamp, st, sat] = pll_step(ug, st, cfg)
%PLL_STEP 单相T/4延时PLL单步更新
%
%   用 u_g(t-T/4) 构造正交分量，使 u_beta = U*cos(theta)：
%     u_delay = U*sin(theta-pi/2) = -U*cos(theta)  ->  u_beta = -u_delay
%   鉴相器 vq = u_alpha*cos(th) - u_beta*sin(th) = U*sin(theta-th)
%   锁定后 th = theta，sin_ref = sin(theta) 与电网电压同相。
%
%   注意：buffer 为长度 N4 的循环队列，先读旧值再写当前值，
%   因此读到的是恰好 N4 拍之前的 u_g。
%
%   %#codegen

N4 = numel(st.buf);
udel = st.buf(st.idx);          % N4 拍之前的 u_g
st.buf(st.idx) = ug;
st.idx = st.idx + 1;
if st.idx > N4
    st.idx = 1;
end

ubeta = -udel;                  % = U*cos(theta)
vq = ug*cos(st.th) - ubeta*sin(st.th);
sat_vq = abs(vq) >= cfg.vq_max;

% 暂态误差限幅（防止启动/畸变时甩锁）
if vq > cfg.vq_max
    vq = cfg.vq_max;
elseif vq < -cfg.vq_max
    vq = -cfg.vq_max;
end

st.wint = st.wint + cfg.Ki*vq*cfg.Ts;
if st.wint > cfg.wint_max
    st.wint = cfg.wint_max;
elseif st.wint < -cfg.wint_max
    st.wint = -cfg.wint_max;
end

w = cfg.w0 + cfg.Kp*vq + st.wint;

% 先用当前采样时刻的角度输出参考，再推进到下一拍。
% 若先推进再输出，sin_ref 会超前电网 1 个控制周期（50 Hz/20 kHz = 0.9°）。
sin_ref = sin(st.th);
cos_ref = cos(st.th);
Uamp = sqrt(ug*ug + ubeta*ubeta);
sat = sat_vq || (abs(st.wint) >= cfg.wint_max);

st.th = st.th + w*cfg.Ts;
if st.th >= 2*pi
    st.th = st.th - 2*pi;
elseif st.th < 0
    st.th = st.th + 2*pi;
end
end
