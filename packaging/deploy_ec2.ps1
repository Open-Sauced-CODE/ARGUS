# Deploy updated ARGUS Showcase Portal + Built Windows .exe Releases to AWS EC2
$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Key = Join-Path $Root "argus-key.pem"
$HostAddr = "ubuntu@13.201.224.53"
$BundlePath = Join-Path $Root "deploy_bundle.tar.gz"
$FilesDir = Join-Path $Root "releases\files"
$Installer = Join-Path $FilesDir "ARGUS-Desktop-Setup-v2.0.0-win64.exe"
$PortableZip = Join-Path $FilesDir "ARGUS-Desktop-v2.0.0-win64-portable.zip"

if (-not (Test-Path $Key)) { throw "SSH key missing: $Key" }
if (-not (Test-Path $Installer)) { throw "Built installer missing: $Installer" }
if (-not (Test-Path $PortableZip)) { throw "Built portable zip missing: $PortableZip" }

Set-Location $Root

Write-Host "[1/4] Creating deploy_bundle.tar.gz..." -ForegroundColor Cyan
if (Test-Path $BundlePath) { Remove-Item $BundlePath -Force }
tar -czf $BundlePath `
    backend/api_server.py `
    backend/README.md `
    dashboard/dist `
    demo.py `
    deploy_dashboard.py `
    releases/manifest.json `
    releases/benchmarks.json `
    remediate `
    server.py
if ($LASTEXITCODE -ne 0) { throw "tar bundle creation failed!" }

Write-Host "[2/4] Uploading portal bundle to EC2..." -ForegroundColor Cyan
scp -i $Key -o StrictHostKeyChecking=no -o ServerAliveInterval=15 -o ServerAliveCountMax=6 $BundlePath "${HostAddr}:/home/ubuntu/deploy_bundle.tar.gz"
if ($LASTEXITCODE -ne 0) { throw "scp deploy_bundle.tar.gz failed!" }

Write-Host "[3/4] Uploading Windows .exe installer & portable .zip to EC2..." -ForegroundColor Cyan
ssh -i $Key -o StrictHostKeyChecking=no -o ServerAliveInterval=15 -o ServerAliveCountMax=6 $HostAddr "mkdir -p /home/ubuntu/argus_app/releases/files"
if ($LASTEXITCODE -ne 0) { throw "Failed creating releases/files on EC2!" }

scp -i $Key -o StrictHostKeyChecking=no -o ServerAliveInterval=15 -o ServerAliveCountMax=6 $Installer "${HostAddr}:/home/ubuntu/argus_app/releases/files/"
if ($LASTEXITCODE -ne 0) { throw "scp installer failed!" }
scp -i $Key -o StrictHostKeyChecking=no -o ServerAliveInterval=15 -o ServerAliveCountMax=6 $PortableZip "${HostAddr}:/home/ubuntu/argus_app/releases/files/"
if ($LASTEXITCODE -ne 0) { throw "scp portable zip failed!" }

Write-Host "[4/4] Extracting bundle and restarting argus.service on EC2..." -ForegroundColor Cyan
$RemoteCmd = "tar -xzf /home/ubuntu/deploy_bundle.tar.gz -C /home/ubuntu/argus_app && sudo systemctl restart argus && sleep 2 && sudo systemctl status argus --no-pager -l | head -n 20 && df -h /"
ssh -i $Key -o StrictHostKeyChecking=no -o ServerAliveInterval=15 -o ServerAliveCountMax=6 $HostAddr $RemoteCmd
if ($LASTEXITCODE -ne 0) { throw "Remote restart failed!" }
if (Test-Path $BundlePath) { Remove-Item $BundlePath -Force }

Write-Host "`nEC2 DEPLOYMENT COMPLETE!" -ForegroundColor Green
