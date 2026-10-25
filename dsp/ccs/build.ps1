# build.ps1 -- command-line build for the F28379D project (no CCS GUI)
#
# Usage:  .\build.ps1
#         .\build.ps1 -Clean
#
# Auto-discovers CCS, ti-cgt-c2000 and C2000Ware under C:\ti.

param([switch]$Clean)

$ErrorActionPreference = 'Stop'

# cl2000 writes warnings to stderr; PowerShell would treat that as a
# terminating error. Route native stderr into the normal stream instead.
$PSNativeCommandUseErrorActionPreference = $false

# ---------- discover CCS + compiler ----------
$ccsRoot = Get-ChildItem 'C:\ti' -Directory -Filter 'ccs*' -ErrorAction SilentlyContinue |
           Sort-Object Name -Descending | Select-Object -First 1
if (-not $ccsRoot) { throw "CCS not found under C:\ti" }

$cc = Get-ChildItem (Join-Path $ccsRoot.FullName 'ccs\tools\compiler') -Directory -Filter 'ti-cgt-c2000*' -ErrorAction SilentlyContinue |
      Sort-Object Name -Descending | Select-Object -First 1
if (-not $cc) { throw "ti-cgt-c2000 not found under $($ccsRoot.FullName)\ccs\tools\compiler" }

$cl2000 = Join-Path $cc.FullName 'bin\cl2000.exe'
$hex2000 = Join-Path $cc.FullName 'bin\hex2000.exe'
$ccInc  = Join-Path $cc.FullName 'include'

# ---------- discover C2000Ware ----------
$ware = Get-ChildItem 'C:\ti' -Directory -Filter 'C2000Ware_*' -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending | Select-Object -First 1
if (-not $ware) {
    Write-Host ""
    Write-Host "ERROR: C2000Ware not found under C:\ti" -ForegroundColor Red
    Write-Host "  Install: CCS -> View -> Resource Explorer -> C2000Ware -> Install"
    exit 1
}
$w = $ware.FullName

$dspInc   = Join-Path $w 'device_support\f2837xd\common\include'
$hdrInc   = Join-Path $w 'device_support\f2837xd\headers\include'
$devSrc   = Join-Path $w 'device_support\f2837xd\common\source'
$dlibSrc  = Join-Path $w 'driverlib\f2837xd\driverlib'
$dlibInc  = Join-Path $dlibSrc 'inc'
$dlibLib  = Join-Path $dlibSrc 'ccs\Debug\driverlib_eabi.lib'
$rtsLib   = Join-Path $cc.FullName 'lib'
$linkCmd  = Join-Path $PSScriptRoot '2837xD_FLASH_lnk_cpu1.cmd'

foreach ($p in @($dspInc, $hdrInc, $devSrc, $dlibInc, $dlibLib, $linkCmd)) {
    if (-not (Test-Path $p)) { throw "Missing: $p" }
}

# C2000Ware device support + driverlib compiled directly -- avoids ABI
# and library-format mismatches between prebuilt .libs and our toolchain.
$wsSrcFiles = @(
    (Join-Path $devSrc 'device.c'),
    (Join-Path $devSrc 'F2837xD_CodeStartBranch.asm'),
    (Join-Path $devSrc 'F2837xD_usDelay.asm'),
    (Join-Path $devSrc 'F2837xD_DefaultISR.c'),
    (Join-Path $devSrc 'F2837xD_SysCtrl.c'),
    (Join-Path $devSrc 'F2837xD_Gpio.c'),
    (Join-Path $devSrc 'F2837xD_PieCtrl.c'),
    (Join-Path $devSrc 'F2837xD_PieVect.c')
) | ForEach-Object { $_ }

$dlibSrcFiles = @(
    'adc.c','cmpss.c','cputimer.c','epwm.c','gpio.c','interrupt.c',
    'sci.c','sysctl.c','xbar.c','dma.c','memcfg.c','asysctl.c'
) | ForEach-Object { Join-Path $dlibSrc $_ }

foreach ($s in ($wsSrcFiles + $dlibSrcFiles)) {
    if (-not (Test-Path $s)) { throw "Missing C2000Ware source: $s" }
}

# ---------- project sources ----------
$here = $PSScriptRoot
$dsp  = Split-Path -Parent $here
$srcs = @(
    (Join-Path $dsp  'app\main.c'),
    (Join-Path $here 'board.c'),
    (Join-Path $dsp  'src\control_isr.c'),
    (Join-Path $dsp  'src\pr_ctrl.c'),
    (Join-Path $dsp  'src\pi_ctrl.c'),
    (Join-Path $dsp  'src\sogi_pll.c'),
    (Join-Path $dsp  'src\protect.c'),
    (Join-Path $dsp  'src\fsm.c'),
    (Join-Path $dsp  'src\mppt_po.c'),
    (Join-Path $dsp  'src\pwm_mod.c'),
    (Join-Path $dsp  'src\app.c'),
    (Join-Path $dsp  'src\hal_c2000.c')
)
foreach ($s in $srcs) { if (-not (Test-Path $s)) { throw "Missing source: $s" } }

$all = $srcs + $wsSrcFiles + $dlibSrcFiles

# ---------- clean ----------
$out = Join-Path $here 'build'
if ($Clean -and (Test-Path $out)) { Remove-Item -Recurse -Force $out }
New-Item -ItemType Directory -Force -Path $out | Out-Null

Push-Location $out
try {
    Write-Host "== compiler: $($cc.Name)" -ForegroundColor DarkGray
    Write-Host "== C2000Ware: $($ware.Name)" -ForegroundColor DarkGray
    Write-Host "== compile ==" -ForegroundColor Cyan

    # NOTE: the project lives under a non-ASCII path. cl2000 mangles such
    # paths on its command line, so every source and include directory is
    # passed relative to the build directory -- those resolve via the OS.
    $outUri = New-Object System.Uri(($out.TrimEnd('\') + '\'))
    function RelPath([string]$p) {
        $pUri = New-Object System.Uri($p)
        return $outUri.MakeRelativeUri($pUri).ToString().Replace('/', '\')
    }

    $common = @(
        '--silicon_version=28',
        '--float_support=fpu32',
        '--abi=eabi',
        '--opt_level=2',
        '--define=__C2000__',
        '--define=CPU1',
        "--include_path=$(RelPath $ccInc)",
        "--include_path=$(RelPath $dspInc)",
        "--include_path=$(RelPath $hdrInc)",
        "--include_path=$(RelPath $dlibInc)",
        "--include_path=$(RelPath $dlibSrc)",
        "--include_path=$(RelPath (Join-Path $dsp 'include'))",
        "--include_path=$(RelPath $here)",
        "--obj_directory=$out",
        '--diag_warning=225'
    )

    $rel = @()
    foreach ($s in $all) { $rel += RelPath $s }

    # cl2000 writes warnings/advice to stderr. Windows PowerShell treats
    # native stderr as a terminating error while ErrorActionPreference is
    # Stop, so relax it for the duration of the native calls and judge
    # success purely by the exit code.
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $cl2000 @common @rel
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prevEap
    }
    if ($code -ne 0) { throw "compile failed (exit $code)" }

    Write-Host "== link ==" -ForegroundColor Cyan
    $objs = Get-ChildItem $out -Filter '*.obj' | ForEach-Object { $_.Name }
    $prevEap2 = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $cl2000 @common -z -m pv_inverter.map `
            (RelPath $linkCmd) `
            "-l=$(RelPath (Join-Path $rtsLib 'rts2800_fpu32_eabi.lib'))" `
            '--reread_libs' '--rom_model' `
            '--stack_size=0x300' '--heap_size=0x300' `
            '--output_file=pv_inverter.out' @objs
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prevEap2
    }
    if ($code -ne 0) { throw "link failed (exit $code)" }

    Write-Host "== hex ==" -ForegroundColor Cyan
    & $hex2000 -boot -sci8 -a -o pv_inverter.hex pv_inverter.out | Out-Null

    $sz = (Get-Item 'pv_inverter.out').Length
    Write-Host ""
    Write-Host "OK -> $out\pv_inverter.out ($sz bytes)" -ForegroundColor Green
}
finally {
    Pop-Location
}
