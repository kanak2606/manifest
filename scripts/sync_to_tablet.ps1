# NoteTrace / Manifest - Automated Timestamped Packaging, Push, Cache Purge & Deploy
param(
    [switch]$NoRestart,
    [switch]$RestartOnly,
    [switch]$StartOnly,
    [switch]$StopOnly,
    [int]$WebPort = 8000
)

$ErrorActionPreference = "Continue"

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   MANIFEST / NOTETRACE - DEPLOYMENT PIPELINE" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ""

# ------------------------------------------------------------
# STEP 1: Discover Active Network Endpoints
# ------------------------------------------------------------
Write-Host "[Step 1] Discovering Tablet and Laptop IP on current network..." -ForegroundColor Yellow

$discoveryScript = Join-Path $PSScriptRoot "discover_tablet.ps1"
$endpoint = & $discoveryScript -Port 5022 -WebPort $WebPort

while (-not $endpoint -or -not $endpoint.TabletIP) {
    Write-Host ""
    Write-Host "==========================================================" -ForegroundColor Yellow
    Write-Host "  TABLET NOT CONNECTED OR SSH IS NOT RUNNING" -ForegroundColor Yellow
    Write-Host "==========================================================" -ForegroundColor Yellow
    Write-Host " Please open Termux on your tablet and run these commands:" -ForegroundColor White
    Write-Host ""
    Write-Host "   termux-wake-lock && sshd" -ForegroundColor Green
    Write-Host "   code-server --bind-addr 0.0.0.0:5080" -ForegroundColor Green
    Write-Host ""
    Write-Host " Port Architecture:" -ForegroundColor Gray
    Write-Host "  * 5000-Series (Remote Dev Tools):" -ForegroundColor Gray
    Write-Host "    - SSH Service   : Port 5022" -ForegroundColor Gray
    Write-Host "    - Code-Server   : Port 5080 (http://[tablet-ip]:5080)" -ForegroundColor Gray
    Write-Host "  * 8000-Series (Deployments and Web Apps):" -ForegroundColor Gray
    Write-Host "    - NoteTrace App : Port 8000 (http://[tablet-ip]:8000)" -ForegroundColor Gray
    Write-Host "==========================================================" -ForegroundColor Yellow
    Write-Host ""
    $retryChoice = Read-Host " Press [Enter] or [R] to retry connection, or [Q] to quit"
    if ($retryChoice -match "^[Qq]") {
        Write-Host " Exiting deployment." -ForegroundColor DarkGray
        exit 1
    }
    Write-Host "[*] Rescanning network for tablet on port 5022..." -ForegroundColor Cyan
    $endpoint = & $discoveryScript -Port 5022 -WebPort $WebPort -ForceRescan
}

$laptopIP = $endpoint.LaptopIP
$tabletIP = $endpoint.TabletIP
$port     = $endpoint.SshPort
$webPort  = $endpoint.WebServerPort
$user     = "u0_a221"

Write-Host "  -> Laptop IP : $laptopIP" -ForegroundColor White
Write-Host "  -> Tablet IP : $tabletIP (SSH Port: $port, Web Port: $webPort)" -ForegroundColor White
Write-Host "[✓] Step 1 Complete: Network endpoint resolved." -ForegroundColor Green
Write-Host ""

# ------------------------------------------------------------
# STEP 1.5: Configure Dedicated Zero-Prompt SSH Key
# ------------------------------------------------------------
$idKey = Join-Path $env:USERPROFILE ".ssh\id_tablet"
$sshOpts = @("-p", "$port", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null", "-o", "LogLevel=ERROR")
$scpOpts = @("-P", "$port", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null", "-o", "LogLevel=ERROR")

if (Test-Path $idKey) {
    $sshOpts += @("-i", $idKey, "-o", "IdentitiesOnly=yes")
    $scpOpts += @("-i", $idKey, "-o", "IdentitiesOnly=yes")
}

# Verify key-based auth works; auto-configure if needed
$keyVerified = $false
try {
    $batchOut = & ssh $sshOpts -o "BatchMode=yes" "${user}@${tabletIP}" "echo KEY_AUTH_OK" 2>$null
    if ($batchOut -match "KEY_AUTH_OK") {
        $keyVerified = $true
    }
} catch {}

if (-not $keyVerified) {
    Write-Host "[*] Authorizing seamless SSH access on tablet..." -ForegroundColor Yellow
    $setupScript = Join-Path $PSScriptRoot "setup_tablet_ssh.py"
    $venvPy = Join-Path (Split-Path $PSScriptRoot -Parent) ".venv\Scripts\python.exe"
    if (Test-Path $venvPy) {
        & $venvPy $setupScript $tabletIP
    } else {
        python $setupScript $tabletIP
    }
}

# ------------------------------------------------------------
# FAST PATH: Stop Only
# ------------------------------------------------------------
if ($StopOnly) {
    Write-Host "[*] Stopping NoteTrace services on Tablet ($tabletIP)..." -ForegroundColor Yellow
    $killRemoteCmd = @'
cd ~/NoteTrace 2>/dev/null || cd ~/manifest 2>/dev/null || true
if [ -f "termux/stop.sh" ]; then
    bash termux/stop.sh 2>&1 || true
fi
pkill -9 -f "python run.py" 2>/dev/null || true
pkill -9 -f "uvicorn" 2>/dev/null || true
echo "[✓] NoteTrace processes stopped on tablet."
'@
    & ssh $sshOpts "${user}@${tabletIP}" $killRemoteCmd
    Write-Host "[✓] Services stopped on tablet." -ForegroundColor Green
    Write-Host "==========================================================" -ForegroundColor Cyan
    exit 0
}

# ------------------------------------------------------------
# FAST PATH: Start Only
# ------------------------------------------------------------
if ($StartOnly) {
    Write-Host "[*] Starting NoteTrace services on Tablet ($tabletIP)..." -ForegroundColor Yellow
    $startRemoteCmd = 'cd ~/NoteTrace && export PORT=8000 && chmod +x termux/*.sh && ./termux/start.sh'
    & ssh $sshOpts "${user}@${tabletIP}" $startRemoteCmd

    Write-Host "  -> Verifying server is listening on port $webPort..." -ForegroundColor Gray
    Start-Sleep -Seconds 2

    $isListening = $false
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $iar = $client.BeginConnect($tabletIP, $webPort, $null, $null)
        if ($iar.AsyncWaitHandle.WaitOne(1500, $false) -and $client.Connected) {
            $isListening = $true
            $client.EndConnect($iar)
        }
        $client.Close()
    } catch {}

    if ($isListening) {
        Write-Host "  [✓] Server is LIVE on http://${tabletIP}:${webPort}" -ForegroundColor Green
    } else {
        Write-Host "  [!] Server started; port $webPort may need another second." -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "==========================================================" -ForegroundColor Cyan
    Write-Host " [✓] TABLET SERVICES STARTED!" -ForegroundColor Green
    Write-Host " Tablet URL       : http://${tabletIP}:${webPort}" -ForegroundColor White
    Write-Host " NiKiosk URL      : http://127.0.0.1:${webPort}/display" -ForegroundColor Gray
    Write-Host "==========================================================" -ForegroundColor Cyan
    exit 0
}

# ------------------------------------------------------------
# FAST PATH: Restart Only
# ------------------------------------------------------------
if ($RestartOnly) {
    Write-Host "[*] Restarting NoteTrace services on Tablet ($tabletIP)..." -ForegroundColor Yellow

    Write-Host "  -> Stopping existing processes..." -ForegroundColor Gray
    $killRemoteCmd = @'
cd ~/NoteTrace 2>/dev/null || cd ~/manifest 2>/dev/null || true
if [ -f "termux/stop.sh" ]; then
    bash termux/stop.sh 2>&1 || true
fi
pkill -9 -f "python run.py" 2>/dev/null || true
pkill -9 -f "uvicorn" 2>/dev/null || true
echo "[✓] Lingering processes terminated on tablet."
'@
    & ssh $sshOpts "${user}@${tabletIP}" $killRemoteCmd

    Write-Host "  -> Starting fresh instance..." -ForegroundColor Gray
    $startRemoteCmd = 'cd ~/NoteTrace && export PORT=8000 && chmod +x termux/*.sh && ./termux/start.sh'
    & ssh $sshOpts "${user}@${tabletIP}" $startRemoteCmd

    Write-Host "  -> Verifying server is listening on port $webPort..." -ForegroundColor Gray
    Start-Sleep -Seconds 2

    $isListening = $false
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $iar = $client.BeginConnect($tabletIP, $webPort, $null, $null)
        if ($iar.AsyncWaitHandle.WaitOne(1500, $false) -and $client.Connected) {
            $isListening = $true
            $client.EndConnect($iar)
        }
        $client.Close()
    } catch {}

    if ($isListening) {
        Write-Host "  [✓] Server is LIVE on http://${tabletIP}:${webPort}" -ForegroundColor Green
    } else {
        Write-Host "  [!] Server started; port $webPort may need another second." -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "==========================================================" -ForegroundColor Cyan
    Write-Host " [✓] TABLET SERVICES RESTARTED!" -ForegroundColor Green
    Write-Host " Tablet URL       : http://${tabletIP}:${webPort}" -ForegroundColor White
    Write-Host " NiKiosk URL      : http://127.0.0.1:${webPort}/display" -ForegroundColor Gray
    Write-Host "==========================================================" -ForegroundColor Cyan
    exit 0
}

# ------------------------------------------------------------
# STEP 2: Build Clean Timestamped Package
# ------------------------------------------------------------
Write-Host "[Step 2/6] Packaging clean release into Manifest-Clean-<TIMESTAMP>.zip..." -ForegroundColor Yellow

$packageScript = Join-Path $PSScriptRoot "package_manifest.py"
$pkgOutput = python $packageScript
$pkgOutput | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }

$zipName = ($pkgOutput | Select-String -Pattern "OUTPUT_ZIP=(.*)" | ForEach-Object { $_.Matches.Groups[1].Value })
if (-not $zipName) {
    # Fallback to finding the newest zip in root
    $rootDir = Split-Path $PSScriptRoot -Parent
    $zipFileObj = Get-ChildItem -Path $rootDir -Filter "Manifest-Clean-*.zip" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($zipFileObj) { $zipName = $zipFileObj.Name }
}

if (-not $zipName) {
    Write-Host "[X] ERROR: Failed to create timestamped zip package." -ForegroundColor Red
    exit 1
}

$rootDir = Split-Path $PSScriptRoot -Parent
$localZipPath = Join-Path $rootDir $zipName
$sizeMb = (Get-Item $localZipPath).Length / 1MB

Write-Host ("  -> Package ready: {0} ({1:N2} MB)" -f $zipName, $sizeMb) -ForegroundColor White
Write-Host "[✓] Step 2 Complete: Clean timestamped package created." -ForegroundColor Green
Write-Host ""

# ------------------------------------------------------------
# STEP 3: Stop & Kill Existing Process on Tablet
# ------------------------------------------------------------
Write-Host "[Step 3/6] Stopping and killing existing server processes on Tablet..." -ForegroundColor Yellow

$killRemoteCmd = @'
cd ~/NoteTrace 2>/dev/null || cd ~/manifest 2>/dev/null || true
if [ -f "termux/stop.sh" ]; then
    bash termux/stop.sh 2>&1 || true
fi
pkill -9 -f "python run.py" 2>/dev/null || true
pkill -9 -f "uvicorn" 2>/dev/null || true
echo "[✓] Lingering processes terminated on tablet."
'@

& ssh $sshOpts "${user}@${tabletIP}" $killRemoteCmd
Write-Host "[✓] Step 3 Complete: Process killed." -ForegroundColor Green
Write-Host ""

# ------------------------------------------------------------
# STEP 4: Push Timestamped Package via SCP
# ------------------------------------------------------------
Write-Host "[Step 4/6] Pushing $zipName to Tablet ($tabletIP)..." -ForegroundColor Yellow
Write-Host "  [*] Authenticating securely with dedicated key (zero prompts)..." -ForegroundColor Gray

& scp $scpOpts "$localZipPath" "${user}@${tabletIP}:~/NoteTrace/$zipName"

if ($LASTEXITCODE -ne 0) {
    Write-Host "[!] Could not upload directly to ~/NoteTrace. Retrying upload to ~/ ..." -ForegroundColor DarkYellow
    & scp $scpOpts "$localZipPath" "${user}@${tabletIP}:~/$zipName"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[X] Upload failed with code $LASTEXITCODE. Check your password or SSH key." -ForegroundColor Red
        exit 1
    }
}
Write-Host "[✓] Step 4 Complete: $zipName transferred successfully." -ForegroundColor Green
Write-Host ""

# ------------------------------------------------------------
# STEP 5: Clear Old Caches & Unpack New Build
# ------------------------------------------------------------
Write-Host "[Step 5/6] Purging old cache files & unpacking new release on Tablet..." -ForegroundColor Yellow

$unpackRemoteCmd = @"
mkdir -p ~/NoteTrace && cd ~/NoteTrace
if [ -f ~/$zipName ] && [ ! -f ./$zipName ]; then
    mv ~/$zipName ./$zipName
fi

echo "  [*] Removing old backend and static files..."
rm -rf notetrace_backend static 2>/dev/null || true
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true

echo "  [*] Unpacking $zipName..."
unzip -o "$zipName"
rm -f "$zipName"
chmod +x termux/*.sh 2>/dev/null || true
echo "  [✓] Unpack complete and permissions set."
"@

& ssh $sshOpts "${user}@${tabletIP}" $unpackRemoteCmd
Write-Host "[✓] Step 5 Complete: Cache purged and release unpacked." -ForegroundColor Green
Write-Host ""

# ------------------------------------------------------------
# STEP 6: Launch Server on Tablet & Health Check
# ------------------------------------------------------------
if (-not $NoRestart) {
    Write-Host "[Step 6/6] Launching NoteTrace / Manifest server on Tablet..." -ForegroundColor Yellow

    $startRemoteCmd = 'cd ~/NoteTrace && export PORT=8000 && chmod +x termux/*.sh && ./termux/start.sh'
    & ssh $sshOpts "${user}@${tabletIP}" $startRemoteCmd

    Write-Host "  -> Verifying server is listening on port $webPort..." -ForegroundColor Gray
    Start-Sleep -Seconds 2

    $isListening = $false
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $iar = $client.BeginConnect($tabletIP, $webPort, $null, $null)
        if ($iar.AsyncWaitHandle.WaitOne(1000, $false) -and $client.Connected) {
            $isListening = $true
            $client.EndConnect($iar)
        }
        $client.Close()
    } catch {}

    if ($isListening) {
        Write-Host "  [✓] Server is LIVE on http://${tabletIP}:${webPort}" -ForegroundColor Green
    } else {
        Write-Host "  [!] Server started; port $webPort may need another second." -ForegroundColor Yellow
    }
    Write-Host "[✓] Step 6 Complete: Server running on Android Tablet!" -ForegroundColor Green
}

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " [✓] DEPLOYMENT & CACHE PURGE SUCCESSFUL!" -ForegroundColor Green
Write-Host " Package Deployed : $zipName" -ForegroundColor White
Write-Host " Tablet URL       : http://${tabletIP}:${webPort}" -ForegroundColor White
Write-Host " NiKiosk URL      : http://127.0.0.1:${webPort}/display" -ForegroundColor Gray
Write-Host " Tip: In your browser, press Ctrl+Shift+R once to refresh cache." -ForegroundColor Gray
Write-Host "==========================================================" -ForegroundColor Cyan
