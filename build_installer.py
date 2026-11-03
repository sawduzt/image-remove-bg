"""Build RemoveBG-Setup.bat — a single-file, self-extracting installer.

The .bat embeds every payload as base64, decodes them with certutil into
%LOCALAPPDATA%\\RemoveBG, then runs setup.ps1 (venv + rembg + registry).
Hand someone the one .bat; the tool persists after they delete it.

Usage: python build_installer.py
Output: RemoveBG-Setup.bat next to this script
"""

import base64
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "RemoveBG-Setup.bat")

# ---------------------------------------------------------------- payloads
# The proven worker, verified on this machine.
with open(os.path.join(HERE, "remove_bg.py"), "r", encoding="utf-8") as f:
    REMOVE_BG_PY = f.read()

MAKE_REG_PY = r'''"""Generate remove-bg-submenu.reg for THIS folder (self-locating)."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PYW = os.path.join(HERE, "venv", "Scripts", "pythonw.exe")
PY = os.path.join(HERE, "remove_bg.py")

EXTS = ["jpg", "jpeg", "png", "bmp", "gif", "webp", "tif", "tiff", "heic", "heif", "avif"]
PRESETS = [("u2netp", "Fast"), ("u2net", "Balanced"), ("bria-rmbg", "HQ")]
ROOT = r"HKEY_CURRENT_USER\Software\Classes\SystemFileAssociations"


def cmd(model):
    s = '"%s" "%s" "%%1" %s' % (PYW, PY, model)
    return s.replace("\\", "\\\\").replace('"', '\\"')


lines = ["Windows Registry Editor Version 5.00", "", "; Remove Background submenu", ""]
for ext in EXTS:
    base = r"%s\.%s\shell\RemoveBG" % (ROOT, ext)
    lines += ["[-%s]" % base, "[%s]" % base,
              '"MUIVerb"="Remove Background"', '"subcommands"=""',
              "[%s\\shell]" % base]
    for model, label in PRESETS:
        sub = "%s\\shell\\%s" % (base, label)
        lines += ["[%s]" % sub, '@="%s"' % label,
                  "[%s\\command]" % sub, '@="%s"' % cmd(model)]
    lines.append("")

with open(os.path.join(HERE, "remove-bg-submenu.reg"), "w", newline="") as f:
    f.write("\n".join(lines))
print("  registry file written")
'''

SETUP_PS1 = r'''$ErrorActionPreference = 'Continue'
$root = $PSScriptRoot
$log = Join-Path $root 'setup.log'

function Log($m) {
    try { ("{0}  {1}" -f (Get-Date -Format 'HH:mm:ss'), $m) | Add-Content -LiteralPath $log } catch {}
}
function Say($m) { Write-Host "  $m"; Log $m }
function Fail($code, $msg) {
    Log "FAIL RBG-$code  $msg"
    Write-Host ""
    Write-Host "  ---------------------------------------------" -ForegroundColor Red
    Write-Host "   INSTALL FAILED      error code:  RBG-$code" -ForegroundColor Red
    Write-Host "  ---------------------------------------------" -ForegroundColor Red
    Write-Host ""
    Write-Host "   $msg"
    Write-Host ""
    Write-Host "   Log file:  $log"
    Write-Host "   Send the error code above to whoever gave you this tool."
    Write-Host ""
    exit $code
}

Write-Host ""
Write-Host "  Remove BG - setup" -ForegroundColor Cyan
Write-Host "  installing to $root"
Write-Host ""
Log "=== install started ==="
try {
    $os = Get-CimInstance Win32_OperatingSystem
    Log ("os: {0} build {1} / {2} / PS {3}" -f $os.Caption, $os.BuildNumber,
         $env:PROCESSOR_ARCHITECTURE, $PSVersionTable.PSVersion)
    $free = [math]::Round((Get-PSDrive ($root.Substring(0,1))).Free / 1GB, 1)
    Log "free disk: $free GB"
    if ($free -lt 1.5) { Say "WARNING: only $free GB free - needs about 1 GB" }
} catch { Log "env probe failed: $_" }

# --- 1. find a usable Python (rembg needs >=3.11; onnxruntime has no 3.14 wheels yet) ---
$okVers = @('3.12','3.13','3.11')
$found = @()
$pyExe = $null; $pyArgs = @()

function PyVer($exe, $extra) {
    try {
        $out = & $exe @($extra + @('-V')) 2>&1
        if ($LASTEXITCODE -eq 0 -and ($out -join ' ') -match 'Python\s+(\d+)\.(\d+)') {
            return "$($Matches[1]).$($Matches[2])"
        }
    } catch {}
    return $null
}
# A candidate is only usable if it can actually build a venv (embedded runtimes
# bundled with games/apps report a version but ship no venv/pip).
function PyUsable($exe, $extra) {
    try {
        & $exe @($extra + @('-m','venv','--help')) 2>&1 | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}
function Pick($exe, $extra, $ver, $label) {
    if ($okVers -notcontains $ver) { return $false }
    if (-not (PyUsable $exe $extra)) { Log "skip $label ($ver): no venv module"; return $false }
    $script:pyExe = $exe; $script:pyArgs = $extra
    return $true
}

# a) explicit override:  set RBG_PYTHON=C:\path\to\python.exe
if ($env:RBG_PYTHON -and (Test-Path $env:RBG_PYTHON)) {
    $v = PyVer $env:RBG_PYTHON @()
    if ($v) { $found += "RBG_PYTHON ($v)"; Pick $env:RBG_PYTHON @() $v 'RBG_PYTHON' | Out-Null }
}
# b) py launcher, preferred versions
if (-not $pyExe) {
    foreach ($v in $okVers) {
        $got = PyVer 'py' @("-$v")
        if ($got) { $found += "py -$v ($got)"; if (Pick 'py' @("-$v") $got "py -$v") { break } }
    }
}
# c) whatever py / python / python3 default to
if (-not $pyExe) {
    foreach ($c in @('py','python','python3')) {
        $got = PyVer $c @()
        if ($got) { $found += "$c ($got)"; if (Pick $c @() $got $c) { break } }
    }
}
# d) common install folders (python.org, all-users). Skip runtimes bundled
#    inside other apps - they look fine but cannot create a venv.
if (-not $pyExe) {
    $roots = @("$env:LOCALAPPDATA\Programs\Python", "$env:ProgramFiles\Python*",
               "${env:ProgramFiles(x86)}\Python*", "C:\Python3*")
    foreach ($f in (Get-ChildItem -Path $roots -Filter 'python.exe' -Recurse -Depth 2 -ErrorAction SilentlyContinue)) {
        if ($f.FullName -match '(?i)\\(Steam|GOG|Epic|Battle\.net|cache|WindowsApps|node_modules|venv)\\') { continue }
        $got = PyVer $f.FullName @()
        if ($got) { $found += "$($f.FullName) ($got)"; if (Pick $f.FullName @() $got $f.FullName) { break } }
    }
}

$list = if ($found.Count) { $found -join ', ' } else { 'none detected' }
Log "python candidates: $list"
try { Log ("py --list: " + ((& py --list 2>$null) -join ' | ')) } catch {}

if (-not $pyExe) {
    Say "no compatible Python yet."
    Say "found: $list"
    Say "needed: 3.11, 3.12 or 3.13"
    Say "trying winget (installs 3.12 alongside, leaves your other versions alone)..."
    $wg = $false
    try {
        & winget install --id Python.Python.3.12 -e --silent `
            --accept-package-agreements --accept-source-agreements 2>&1 | ForEach-Object { Log $_ }
        if ($LASTEXITCODE -eq 0) { $wg = $true }
    } catch { Log "winget threw: $_" }
    $got = PyVer 'py' @('-3.12')
    if ($got -and $okVers -contains $got) { $pyExe='py'; $pyArgs=@('-3.12') }
    if (-not $pyExe -and $wg) {
        Fail 11 ("Python 3.12 was just installed, but this window cannot see it yet.`n" +
                 "   Close this window and run the installer again - it will finish.")
    }
}
if (-not $pyExe) {
    Fail 10 ("Python 3.11, 3.12 or 3.13 is required (3.14 is not supported yet).`n" +
             "   Detected on this PC: $list`n`n" +
             "   Install 3.12 from https://www.python.org/downloads/release/python-3129/`n" +
             "   and tick 'Add python.exe to PATH', then run this installer again.`n" +
             "   It installs alongside any version you already have.")
}
Say "python: $pyExe $pyArgs"

# --- 2. venv ---
$venv = Join-Path $root 'venv'
$vpy = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path $vpy)) {
    Say "creating venv..."
    & $pyExe @($pyArgs + @('-m','venv',$venv)) 2>&1 | ForEach-Object { Log $_ }
}
if (-not (Test-Path $vpy)) {
    Fail 20 "Could not create the Python environment. See the log for details."
}

# --- 3. deps (the slow bit) ---
Say "installing rembg + onnxruntime (~400 MB, a few minutes)..."
& $vpy -m pip install --disable-pip-version-check --upgrade pip 2>&1 | ForEach-Object { Log $_ }
& $vpy -m pip install --disable-pip-version-check "rembg[cpu]" 2>&1 | ForEach-Object { Log $_ }
if ($LASTEXITCODE -ne 0) {
    Fail 30 ("Download/install of rembg failed - usually no internet or a`n" +
             "   firewall blocking pip. See the log for the exact error.")
}
& $vpy -c "import rembg" 2>&1 | ForEach-Object { Log $_ }
if ($LASTEXITCODE -ne 0) {
    Fail 31 "rembg installed but will not load. See the log for details."
}

# --- 4. register the context menu (per-user, no admin) ---
Say "registering right-click menu..."
& $vpy (Join-Path $root 'make_reg.py') 2>&1 | ForEach-Object { Log $_ }
$regFile = Join-Path $root 'remove-bg-submenu.reg'
if (-not (Test-Path $regFile)) { Fail 40 "Could not build the registry file." }
& reg import $regFile 2>&1 | ForEach-Object { Log $_ }
if ($LASTEXITCODE -ne 0) {
    Fail 41 "Windows refused the registry change (a work/school policy can block this)."
}

# --- 5. pre-download the default model so first use is quick ---
Write-Host "  fetching default model (~170 MB, one time)..."
try { & $vpy -c "from rembg import new_session; new_session('u2net')" 2>$null | Out-Null } catch {}

Write-Host ""
Write-Host "  Done." -ForegroundColor Green
Write-Host "  Right-click any image -> Remove Background -> Fast / Balanced / HQ"
Write-Host "  Output lands next to the original as <name>_bgremoved.png"
Write-Host ""
Write-Host "  Fast     ~1s   clean subjects"
Write-Host "  Balanced ~5s   default, good with hair/fur"
Write-Host "  HQ       ~30s  best edges (downloads a 1 GB model on first use)"
Write-Host ""
Write-Host "  If the menu does not appear, restart Explorer or sign out and back in."
Write-Host "  To remove: run uninstall.bat in $root"
Write-Host ""
'''

UNINSTALL_BAT = r'''@echo off
title Remove BG - uninstall
echo.
echo   Removing the "Remove Background" right-click menu...
for %%E in (jpg jpeg png bmp gif webp tif tiff heic heif avif) do (
  reg delete "HKCU\Software\Classes\SystemFileAssociations\.%%E\shell\RemoveBG" /f >nul 2>&1
)
echo   Menu removed.
echo.
echo   To reclaim disk space, delete these yourself:
echo     this folder        %~dp0
echo     model cache        %USERPROFILE%\.rembg
echo.
pause
'''

# ---------------------------------------------------------------- builder
def b64_lines(text: str, width: int = 76):
    raw = text.replace("\r\n", "\n").encode("utf-8")
    b = base64.b64encode(raw).decode("ascii")
    return [b[i:i + width] for i in range(0, len(b), width)]


def emit(payload_name: str, text: str, target: str):
    """Emit .bat lines that rebuild `text` at `target` via certutil."""
    out = [f'echo   unpacking {payload_name}...']
    tmp = f'"%TMPB64%"'
    out.append(f'if exist {tmp} del {tmp}')
    for line in b64_lines(text):
        out.append(f'>>{tmp} echo {line}')
    out.append(f'certutil -f -decode {tmp} "{target}" >nul 2>&1')
    out.append(f'if errorlevel 1 goto :failed')
    out.append(f'del {tmp}')
    return out


bat = [
    "@echo off",
    "setlocal",
    "title Remove BG - Setup",
    "echo.",
    "echo   ===============================================",
    "echo     Remove BG  -  right-click background remover",
    "echo   ===============================================",
    "echo.",
    "rem  Optional first arg = install dir (default: %LOCALAPPDATA%\\RemoveBG)",
    'set "INSTALL=%~1"',
    'if "%INSTALL%"=="" set "INSTALL=%LOCALAPPDATA%\\RemoveBG"',
    'set "TMPB64=%TEMP%\\_rbg_payload.b64"',
    'if not exist "%INSTALL%" mkdir "%INSTALL%" 2>nul',
    'if not exist "%INSTALL%" (',
    '  echo   ERROR: cannot create "%INSTALL%"',
    "  pause",
    "  exit /b 1",
    ")",
    "echo   target: %INSTALL%",
    "echo.",
]
bat += emit("worker", REMOVE_BG_PY, "%INSTALL%\\remove_bg.py")
bat += emit("registry builder", MAKE_REG_PY, "%INSTALL%\\make_reg.py")
bat += emit("setup script", SETUP_PS1, "%INSTALL%\\setup.ps1")
bat += emit("uninstaller", UNINSTALL_BAT, "%INSTALL%\\uninstall.bat")
bat += [
    "echo.",
    'powershell -NoProfile -ExecutionPolicy Bypass -File "%INSTALL%\\setup.ps1"',
    "if errorlevel 1 goto :failed",
    "pause",
    "exit /b 0",
    "",
    ":failed",
    "echo.",
    "echo   Setup failed - see the messages above.",
    "pause",
    "exit /b 1",
]

with open(OUT, "w", newline="\r\n", encoding="ascii") as f:
    f.write("\n".join(bat) + "\n")

print(f"wrote {OUT}")
print(f"  {len(bat)} lines, {os.path.getsize(OUT) // 1024} KB")
