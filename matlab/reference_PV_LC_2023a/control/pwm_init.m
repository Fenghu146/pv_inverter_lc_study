function st = pwm_init()
%PWM_INIT 载波/死区状态初始化：t=0 位于载波峰值，低边导通
%   %#codegen
st = struct('ph', 0, 'gh', false, 'gl', true, 'cnt', 0, 's_cmd', false);
end
