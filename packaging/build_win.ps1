# Deterministic Windows Release Builder for ARGUS-Desktop
$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"
$PyInstaller = Join-Path $Root ".venv\Scripts\pyinstaller.exe"
$FilesDir = Join-Path $Root "releases\files"
$IsccDefault = Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"

Set-Location $Root

Write-Host "[1/8] Checking frozen contracts..." -ForegroundColor Cyan
& $VenvPy tools\check_frozen.py
if ($LASTEXITCODE -ne 0) { throw "Frozen path integrity check failed!" }

Write-Host "[2/8] Preparing READY manifest & building React dashboard (typecheck + vite build)..." -ForegroundColor Cyan
& $VenvPy packaging\update_manifest.py --prebuild
if ($LASTEXITCODE -ne 0) { throw "Prebuild manifest prep failed!" }

Push-Location (Join-Path $Root "dashboard")
try {
    npm run typecheck
    if ($LASTEXITCODE -ne 0) { throw "Dashboard typecheck failed!" }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "Dashboard Vite build failed!" }
} finally {
    Pop-Location
}

Write-Host "[3/8] Generating ARGUS icon..." -ForegroundColor Cyan
& $VenvPy packaging\make_icon.py
if ($LASTEXITCODE -ne 0) { throw "Icon generation failed!" }

Write-Host "[4/8] Running PyInstaller (--onedir)..." -ForegroundColor Cyan
$env:OPA_BIN = "D:\opa\opa.exe"
& $PyInstaller --noconfirm --clean packaging\argus.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed!" }

$ExePath = Join-Path $Root "dist\ARGUS\ARGUS.exe"
if (-not (Test-Path $ExePath)) { throw "Expected built executable missing: $ExePath" }

Write-Host "[5/8] Running standalone .exe --smoke-test (outside .venv)..." -ForegroundColor Cyan
$SmokeLog = Join-Path $env:TEMP "argus_exe_smoke.log"
if (Test-Path $SmokeLog) { Remove-Item $SmokeLog -Force }
$Proc = Start-Process -FilePath $ExePath -ArgumentList "--smoke-test", "--smoke-log", "`"$SmokeLog`"" -Wait -PassThru -NoNewWindow
if (Test-Path $SmokeLog) { Get-Content $SmokeLog }
if ($Proc.ExitCode -ne 0) { throw "ARGUS.exe --smoke-test failed with exit code $($Proc.ExitCode)!" }

Write-Host "[6/8] Creating portable ZIP archive..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $FilesDir | Out-Null
$ZipPath = Join-Path $FilesDir "ARGUS-Desktop-v2.0.0-win64-portable.zip"
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Compress-Archive -Path (Join-Path $Root "dist\ARGUS\*") -DestinationPath $ZipPath -CompressionLevel Optimal

Write-Host "[7/8] Compiling Inno Setup Windows installer..." -ForegroundColor Cyan
$Iscc = $null
if (Test-Path $IsccDefault) {
    $Iscc = $IsccDefault
} else {
    $Cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($Cmd) { $Iscc = $Cmd.Source }
}
if (-not $Iscc) { throw "Inno Setup compiler ISCC.exe not found! Install JRSoftware.InnoSetup." }
& $Iscc (Join-Path $Root "packaging\argus_installer.iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed!" }

Write-Host "[8/8] Updating releases/manifest.json & rebuilding dashboard fallback..." -ForegroundColor Cyan
& $VenvPy packaging\update_manifest.py
if ($LASTEXITCODE -ne 0) { throw "Manifest update failed!" }

Push-Location (Join-Path $Root "dashboard")
try {
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "Dashboard rebuild failed!" }
} finally {
    Pop-Location
}

Write-Host "`nBUILD COMPLETE! Outputs:" -ForegroundColor Green
Get-ChildItem $FilesDir | Format-Table Name, Length, LastWriteTime
