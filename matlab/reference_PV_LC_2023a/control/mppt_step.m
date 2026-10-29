function [Im, Vref, vdc_f, P, st] = mppt_step(vdc, ipv, st, cfg)
%MPPT_STEP P&O 电压参考 + 5-10 Hz 直流电压 PI（DSP 同款）
%
%   1) 10 ms 滑动平均滤除单相并网固有的 100 Hz 母线纹波；
%   2) P&O 每 cfg.Np 拍（0.5 s）判决一次，步长 cfg.dV；
%      判决周期约为电压环调节时间（~0.1 s）的 5 倍；
%   3) 电压 PI：err = vdc_f - Vref（母线高于参考时增大并网电流），
%      输出 Im 限幅 [0, Im_max]，饱和时条件冻结积分；
%   4) Vref 限幅 [Vmin, Vmax]，下限 58 V。
%
%   %#codegen

% ---- 10 ms 滑动平均 ----
if st.first
    st.vbuf(:) = vdc;
    st.ibuf(:) = ipv;
    st.vsum = vdc*cfg.Nma;
    st.isum = ipv*cfg.Nma;
    st.first = false;
end
oldv = st.vbuf(st.idx);
oldi = st.ibuf(st.idx);
st.vbuf(st.idx) = vdc;
st.ibuf(st.idx) = ipv;
st.vsum = st.vsum - oldv + vdc;
st.isum = st.isum - oldi + ipv;
st.idx = st.idx + 1;
if st.idx > cfg.Nma
    st.idx = 1;
end
vdc_f = st.vsum/cfg.Nma;
ipv_f = st.isum/cfg.Nma;
P = vdc_f*ipv_f;

% ---- P&O 电压参考 ----
st.cnt = st.cnt + 1;
if st.cnt >= cfg.Np
    if P < st.Pprev
        st.dir = -st.dir;
    end
    st.Vref = st.Vref + st.dir*cfg.dV;
    if st.Vref > cfg.Vmax
        st.Vref = cfg.Vmax;
        st.dir = -1;
    elseif st.Vref < cfg.Vmin
        st.Vref = cfg.Vmin;
        st.dir = 1;
    end
    st.Pprev = P;
    st.cnt = 0;
end
Vref = st.Vref;

% ---- 直流电压 PI ----
err = vdc_f - Vref;                 % 母线高于参考 -> 增大 Im
integ = st.integ + cfg.Ki*err*cfg.Ts;
if integ > cfg.Im_max
    integ = cfg.Im_max;
elseif integ < 0
    integ = 0;
end
Im_raw = cfg.Kp*err + integ;
if Im_raw > cfg.Im_max
    Im = cfg.Im_max;
    if err > 0, integ = st.integ; end      % 仍在往上推 -> 冻结
elseif Im_raw < 0
    Im = 0;
    if err < 0, integ = st.integ; end      % 仍在往下推 -> 冻结
else
    Im = Im_raw;
end
st.integ = integ;
end
