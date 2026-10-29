function [g, st] = pwm_bipolar(m, st, cfg)
%PWM_BIPOLAR 双极性 SPWM 载波比较 + 可选死区（DSP 同款）
%
%   载波：三角波，周期 Tsw=1/fsw，在 ph=0 处为峰值 +1，ph=0.5 处为谷值 -1。
%   控制周期 Tsc=1/fsw，因此每个控制节拍正好落在载波峰值上；
%   电流在峰值处同步采样即为开关周期平均值（无需 2 kHz 低通）。
%
%   门极顺序与 Universal Bridge 一致：[S1;S2;S3;S4]。
%   正半周 S1/S4 导通 -> [1;0;0;1]；负半周 S2/S3 -> [0;1;1;0]。
%   死区：命令变化时先关断，blanking Nd 拍后开通目标器件；期间两管全关。
%   死区需要反并联二极管续流，L5 模型使用 IGBT/Diodes；L3 取 Nd=0。
%
%   cfg: Ts, Tsw, Nd
%   %#codegen

st.ph = st.ph + cfg.Ts/cfg.Tsw;
if st.ph >= 1
    st.ph = st.ph - 1;
end
if st.ph < 0.5
    tri = 1 - 4*st.ph;
else
    tri = 4*st.ph - 3;
end
s = m > tri;                    % 期望的高边状态

if cfg.Nd <= 0
    st.gh = s;
    st.gl = ~s;
    st.cnt = 0;
    st.s_cmd = s;
else
    % 只在“目标状态 s_cmd”改变时启动死区计时。
    % 旧代码用 s ~= st.gh 判断：开通上管等待期间 gh 一直为 false，
    % 每一步都满足条件、计数器被反复重置，Nd>=2 时上管永远开不了。
    % 计数：换流这一步本身就是第 1 个封锁拍，所以 cnt=Nd-1；
    % 之后 cnt>0 的每一步再封锁，cnt 到 0 的下一步才开通目标管。
    % 这样每次换流正好封锁 Nd 拍（Nd=4 -> 1 us @ 0.25 us）。
    if s ~= st.s_cmd
        st.s_cmd = s;
        st.gh = false;
        st.gl = false;
        st.cnt = cfg.Nd - 1;
    elseif st.cnt > 0
        st.cnt = st.cnt - 1;
    else
        if st.s_cmd
            st.gh = true;
        else
            st.gl = true;
        end
    end
end

if st.gh
    g = [1;0;0;1];
elseif st.gl
    g = [0;1;1;0];
else
    g = [0;0;0;0];
end
end
