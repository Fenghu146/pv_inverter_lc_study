function cfg = ctrl_cfg(p, kind)
%CTRL_CFG 控制器配置（L1 冻结参数 + 结构相关前馈）
%   kind: 'L' 或 'LC'
%   注意：死区不在控制器里建模（否则生成 DSP 代码会主动注入畸变），
%   见 control/deadtime_step.m（功率级平均电压误差）。
%   %#codegen

cfg.pr = pr_design(p.Kp_pr, p.Kr_pr, p.f_bw_pr, p.fg, p.Tsc);
cfg.pr.vmax = p.vmax_pr;

cfg.pll      = p.pll;
cfg.pll.Ts   = p.Tsc;
cfg.pll.w0   = p.wg;

cfg.is_lc  = strcmpi(kind,'LC');
cfg.C      = p.C;
cfg.wg     = p.wg;
cfg.vdc_min = 10;          % 前馈除法保护
cfg.m_max   = p.m_max;
end
