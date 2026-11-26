# NoteTrace / Manifest - Dynamic Network Discovery & Endpoint Resolver
param(
    [int]$Port = 5022,
    [int]$WebPort = 8000,
    [switch]$Quiet,
    [switch]$ForceRescan
)

$CacheFile = Join-Path $PSScriptRoot "..\.tablet_ip"
$SshConfigFile = Join-Path $env:USERPROFILE ".ssh\config"

function Get-LaptopAdapter {
    $adapter = Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
        $_.InterfaceAlias -notmatch "vEthernet|WSL|Virtual|Loopback|Pseudo|Bluetooth" -and
        $_.IPAddress -notmatch "^169\.254\." -and
        $_.IPAddress -notmatch "^127\."
    } | Select-Object -First 1

    return $adapter
}

function Test-TcpPort {
    param([string]$IP, [int]$PortNum, [int]$TimeoutMs = 250)
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $iar = $client.BeginConnect($IP, $PortNum, $null, $null)
        $success = $iar.AsyncWaitHandle.WaitOne($TimeoutMs, $false) -and $client.Connected
        if ($success) { $client.EndConnect($iar) }
        $client.Close()
        return $success
    } catch {
        return $false
    }
}

function Test-SshPort {
    param([string]$IP)
    if (Test-TcpPort -IP $IP -PortNum 5022 -TimeoutMs 200) { return 5022 }
    if (Test-TcpPort -IP $IP -PortNum 8022 -TimeoutMs 200) { return 8022 }
    return $null
}

# 1. Detect Laptop IP & Subnet
$laptopAdapter = Get-LaptopAdapter
if (-not $laptopAdapter) {
    Write-Host "[!] Error: No active Wi-Fi or Ethernet connection detected on Laptop." -ForegroundColor Red
    exit 1
}

$laptopIP = $laptopAdapter.IPAddress
$subnetPrefix = $laptopIP.Substring(0, $laptopIP.LastIndexOf('.'))

if (-not $Quiet) {
    Write-Host "==========================================================" -ForegroundColor Cyan
    Write-Host " NoteTrace / Manifest - Device & Network IP Discovery" -ForegroundColor Cyan
    Write-Host "==========================================================" -ForegroundColor Cyan
    Write-Host " Laptop IP   : $laptopIP (Interface: $($laptopAdapter.InterfaceAlias))" -ForegroundColor White
    Write-Host " Subnet      : $subnetPrefix.*" -ForegroundColor Gray
}

# 2. Check Cached IP first (fastest path: ~50ms)
$tabletIP = $null
if ((-not $ForceRescan) -and (Test-Path $CacheFile)) {
    $cached = (Get-Content $CacheFile -Raw).Trim()
    if ($cached -and $cached.StartsWith($subnetPrefix)) {
        $foundPort = Test-SshPort -IP $cached
        if ($foundPort) {
            $tabletIP = $cached
            $Port = $foundPort
            if (-not $Quiet) {
                Write-Host " Tablet IP   : $tabletIP [Cached Hit - Instant] (SSH Port $Port)" -ForegroundColor Green
            }
        }
    }
}

# 3. If cache miss, check ARP table (~200ms)
if (-not $tabletIP) {
    if (-not $Quiet) {
        Write-Host " Scanning local ARP table for tablet..." -ForegroundColor Yellow
    }
    
    $arpIps = (arp -a | Select-String -Pattern "$subnetPrefix\.(\d+)" | ForEach-Object {
        if ($_ -match "($subnetPrefix\.\d+)") { $matches[1] }
    }) | Where-Object { $_ -ne $laptopIP -and $_ -ne "$subnetPrefix.1" -and $_ -ne "$subnetPrefix.255" } | Select-Object -Unique

    foreach ($ip in $arpIps) {
        $foundPort = Test-SshPort -IP $ip
        if ($foundPort) {
            $tabletIP = $ip
            $Port = $foundPort
            if (-not $Quiet) {
                Write-Host " Tablet IP   : $tabletIP [Found via ARP] (SSH Port $Port)" -ForegroundColor Green
            }
            break
        }
    }
}

# 4. If ARP miss, perform fast parallel sweep across subnet (~1-2s)
if (-not $tabletIP) {
    if (-not $Quiet) {
        Write-Host " Network changed or tablet unlisted in ARP. Scanning subnet $subnetPrefix.*..." -ForegroundColor Yellow
    }

    $foundIP = $null
    $foundPort = 5022
    foreach ($tryPort in @($Port, 5022, 8022 | Select-Object -Unique)) {
        $res = 1..254 | ForEach-Object -Parallel {
            $candidateIP = "$using:subnetPrefix.$_"
            if ($candidateIP -eq $using:laptopIP) { return }
            try {
                $client = [System.Net.Sockets.TcpClient]::new()
                $iar = $client.BeginConnect($candidateIP, $using:tryPort, $null, $null)
                if ($iar.AsyncWaitHandle.WaitOne(200, $false) -and $client.Connected) {
                    $client.EndConnect($iar)
                    $client.Close()
                    $candidateIP
                } else {
                    $client.Close()
                }
            } catch {}
        } -ThrottleLimit 60 | Select-Object -First 1

        if ($res) {
            $foundIP = $res
            $foundPort = $tryPort
            break
        }
    }

    if ($foundIP) {
        $tabletIP = $foundIP
        $Port = $foundPort
        if (-not $Quiet) {
            Write-Host " Tablet IP   : $tabletIP [Found via Parallel Scan] (SSH Port $Port)" -ForegroundColor Green
        }
    }
}

if (-not $tabletIP) {
    Write-Host ""
    Write-Host "==========================================================" -ForegroundColor Yellow
    Write-Host "  TABLET NOT DETECTED ON WI-FI OR SSH NOT RUNNING" -ForegroundColor Yellow
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
    exit 2
}

# 5. Check if main NoteTrace / Manifest server is running on Tablet
$webServerRunning = Test-TcpPort -IP $tabletIP -PortNum $WebPort -TimeoutMs 300
if (-not $webServerRunning -and $WebPort -eq 8000) {
    if (Test-TcpPort -IP $tabletIP -PortNum 8080 -TimeoutMs 200) {
        $WebPort = 8080
        $webServerRunning = $true
    }
}

if (-not $Quiet) {
    $webStatusStr = if ($webServerRunning) { "RUNNING (Port $WebPort)" } else { "STOPPED (Needs start)" }
    $webColor = if ($webServerRunning) { "Green" } else { "DarkYellow" }
    Write-Host " Main Server : $webStatusStr on Android Tablet" -ForegroundColor $webColor
    Write-Host " Web URL     : http://${tabletIP}:${WebPort}" -ForegroundColor White
    Write-Host " Kiosk URL   : http://127.0.0.1:${WebPort}/display (Tablet NiKiosk)" -ForegroundColor Gray
    Write-Host "==========================================================" -ForegroundColor Cyan
}

# 6. Save discovered Tablet IP to cache
Set-Content -Path $CacheFile -Value $tabletIP -Force

# 7. Update ~/.ssh/config so `ssh tablet` or VS Code remote always points to right IP with dedicated key
try {
    $sshDir = Split-Path $SshConfigFile -Parent
    if (-not (Test-Path $sshDir)) {
        New-Item -ItemType Directory -Path $sshDir -Force | Out-Null
    }

    $entry = @"
Host tablet
    HostName $tabletIP
    User u0_a221
    Port $Port
    IdentityFile ~/.ssh/id_tablet
    IdentitiesOnly yes
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
    LogLevel ERROR

Host 192.168.* 10.*
    User u0_a221
    IdentityFile ~/.ssh/id_tablet
    IdentitiesOnly yes
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
    LogLevel ERROR
"@

    if (Test-Path $SshConfigFile) {
        $configContent = Get-Content $SshConfigFile -Raw
        if ($configContent -match "(?s)Host\s+tablet\b.*?(?=\r?\nHost|\Z)") {
            $configContent = $configContent -replace "(?s)Host\s+tablet\b.*?(?=\r?\nHost|\Z)", $entry.Trim()
            Set-Content -Path $SshConfigFile -Value $configContent -Force
        } else {
            Add-Content -Path $SshConfigFile -Value "`r`n$entry" -Force
        }
    } else {
        Set-Content -Path $SshConfigFile -Value $entry -Force
    }
} catch {
    # Non-fatal if config update fails
}

# Return info object for callers
return [PSCustomObject]@{
    LaptopIP          = $laptopIP
    TabletIP          = $tabletIP
    SshPort           = $Port
    WebServerPort     = $WebPort
    WebServerRunning  = $webServerRunning
    WebUrl            = "http://${tabletIP}:${WebPort}"
}
