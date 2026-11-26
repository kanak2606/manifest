# NoteTrace / Manifest - 1-Time Passwordless SSH Key Installer
$ErrorActionPreference = "Stop"

$pubKeyFile = "$env:USERPROFILE\.ssh\id_ed25519.pub"
if (-not (Test-Path $pubKeyFile)) {
    Write-Host "[*] Generating Ed25519 SSH Key..." -ForegroundColor Cyan
    ssh-keygen -t ed25519 -N '""' -f "$env:USERPROFILE\.ssh\id_ed25519" -q
}

$pubKey = (Get-Content $pubKeyFile -Raw).Trim()

# Discover current tablet endpoint
$discoveryScript = Join-Path $PSScriptRoot "discover_tablet.ps1"
$endpoint = & $discoveryScript

if (-not $endpoint -or -not $endpoint.TabletIP) {
    Write-Host "[X] Tablet discovery failed. Ensure Termux is running with 'sshd' on port 5022." -ForegroundColor Red
    exit 1
}

$tabletIP = $endpoint.TabletIP
$port = $endpoint.SshPort

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " 1-TIME SETUP: Authorize Windows SSH Key on Tablet" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "This will allow 1-Click login without typing a password." -ForegroundColor Yellow
Write-Host ""
Write-Host "Connecting to Tablet at $tabletIP:$port..." -ForegroundColor White
Write-Host "Enter your Termux password if prompted (ONE TIME ONLY):" -ForegroundColor White
Write-Host ""

$remoteCmd = "mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo '$pubKey' >> ~/.ssh/authorized_keys && sort -u ~/.ssh/authorized_keys -o ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && echo '[OK] Public key installed successfully!'"

& ssh -p $port -o StrictHostKeyChecking=no "u0_a221@$tabletIP" $remoteCmd

Write-Host ""
Write-Host "----------------------------------------------------------" -ForegroundColor Gray
Write-Host "Alternatively, you can copy-paste this one line directly inside Termux:" -ForegroundColor Yellow
Write-Host "echo '$pubKey' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan
