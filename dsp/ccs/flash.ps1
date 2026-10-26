# 一键下载固件到 LAUNCHXL-F28379D（板载 XDS110）
# 用法:  .\flash.ps1             # 构建 + 烧写 + 校验 + 复位运行
#        .\flash.ps1 -SkipBuild  # 跳过构建，直接烧写现有 build\pv_inverter.out
param([switch]$SkipBuild)
$ErrorActionPreference = 'Stop'
$ccsDir = $PSScriptRoot
$dslite = 'C:\ti\ccs2101\ccs\ccs_base\DebugServer\bin\DSLite.exe'
if (-not (Test-Path $dslite)) { throw "未找到 DSLite: $dslite" }

if (-not $SkipBuild) { & (Join-Path $ccsDir 'build.ps1') }
$out = Join-Path $ccsDir 'build\pv_inverter.out'
if (-not (Test-Path $out)) { throw "未找到固件: $out（先运行 .\build.ps1）" }

# -f 加载 -v 校验 -u 结束后复位运行（擦除由加载器按扇区自动完成）
& $dslite flash --config (Join-Path $ccsDir 'pv_inverter_flash.ccxml') -f -v -u $out
if ($LASTEXITCODE -ne 0) { throw "DSLite 烧写失败（exit $LASTEXITCODE）" }
Write-Output "`nFLASH OK: 固件已下载并复位运行。首次上板请按 README 的验证顺序执行。"
