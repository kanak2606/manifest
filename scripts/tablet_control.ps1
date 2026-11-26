# NoteTrace / Manifest - Tablet Orchestrator & 1-Click Session Launcher
param(
    [string]$Action = "auto",
    [switch]$ForceRescan
)

$ErrorActionPreference = "Continue"

# 1. Discover IPs and update ~/.ssh/config
$discoveryScript = Join-Path $PSScriptRoot "discover_tablet.ps1"
$endpoint = & $discoveryScript -ForceRescan:$ForceRescan

if (-not $endpoint -or -not $endpoint.TabletIP) {
    Write-Host "[X] Error: Could not resolve Tablet IP on the current network." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

$laptopIP = $endpoint.LaptopIP
$tabletIP = $endpoint.TabletIP
$webPort  = $endpoint.WebServerPort
$webUrl   = $endpoint.WebUrl
$isRunning = $endpoint.WebServerRunning

function Start-TabletServer {
    Write-Host "[*] Starting NoteTrace / Manifest server on Android Tablet..." -ForegroundColor Yellow
    ssh -o ConnectTimeout=5 tablet "cd ~/NoteTrace && chmod +x termux/*.sh && ./termux/start.sh"
    Start-Sleep -Seconds 1
}

function Restart-TabletServer {
    Write-Host "[*] Restarting NoteTrace / Manifest server on Android Tablet..." -ForegroundColor Yellow
    & ssh -o ConnectTimeout=5 tablet "cd ~/NoteTrace 2>/dev/null || true; chmod +x termux/*.sh 2>/dev/null || true; ./termux/stop.sh 2>/dev/null || true; pkill -9 -f 'python run.py' 2>/dev/null || true; ./termux/start.sh"
    Start-Sleep -Seconds 1
}

function Open-WebBrowser {
    Write-Host "[*] Opening Web Interface in Laptop Browser: $webUrl" -ForegroundColor Green
    Start-Process $webUrl
}

function Show-Logs {
    Write-Host "[*] Streaming live logs from Android Tablet (Ctrl+C to stop)..." -ForegroundColor Cyan
    ssh -t tablet "tail -f -n 50 ~/NoteTrace/logs/notetrace.log"
}

function Open-SshTerminal {
    Write-Host "[*] Launching interactive SSH session into Termux..." -ForegroundColor Green
    ssh -t tablet "cd ~/NoteTrace; exec bash"
}

# Interactive menu selection (waits for user)
if ($Action -eq "auto") {
    Write-Host ""
    Write-Host " [1] Launch All (Start Server on Tablet + Open Browser + SSH Shell)" -ForegroundColor Green
    Write-Host " [2] Open SSH Shell Only (Termux CMD)" -ForegroundColor Cyan
    Write-Host " [3] Restart Server on Android Tablet" -ForegroundColor Yellow
    Write-Host " [4] Open Web App in Browser ($webUrl)" -ForegroundColor Magenta
    Write-Host " [5] View Live Logs from Tablet" -ForegroundColor White
    Write-Host " [6] Rescan Network (Force Re-detect IPs)" -ForegroundColor Gray
    Write-Host " [0] Exit" -ForegroundColor Red
    Write-Host ""

    $choice = ""
    while ($choice -notmatch '^[0-6]$') {
        $choice = Read-Host "Select an option [0-6]"
    }

    switch ($choice) {
        "1" {
            if (-not $isRunning) {
                Start-TabletServer
            } else {
                Write-Host "[✓] Server is already running on Tablet." -ForegroundColor Green
            }
            Open-WebBrowser
            Open-SshTerminal
        }
        "2" {
            Open-SshTerminal
        }
        "3" {
            Restart-TabletServer
            Open-WebBrowser
        }
        "4" {
            Open-WebBrowser
        }
        "5" {
            Show-Logs
        }
        "6" {
            & $discoveryScript -ForceRescan
            Read-Host "Press Enter to continue"
        }
        "0" {
            exit 0
        }
        default {
            Open-SshTerminal
        }
    }
}
elseif ($Action -eq "ssh") {
    Open-SshTerminal
}
elseif ($Action -eq "start") {
    Start-TabletServer
    Open-WebBrowser
}
elseif ($Action -eq "restart") {
    Restart-TabletServer
}
elseif ($Action -eq "logs") {
    Show-Logs
}
