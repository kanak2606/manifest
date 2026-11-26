$wscript = New-Object -ComObject WScript.Shell
$desktop = [System.Environment]::GetFolderPath('Desktop')
$targetBat = Join-Path $PSScriptRoot "..\1-Click-Tablet.bat"
$targetBat = [System.IO.Path]::GetFullPath($targetBat)
$workDir = [System.IO.Path]::GetDirectoryName($targetBat)

$shortcutPath = Join-Path $desktop "Manifest - Tablet Dev.lnk"
$shortcut = $wscript.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $targetBat
$shortcut.WorkingDirectory = $workDir
$shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,14"
$shortcut.Description = "1-Click Auto-Discovery, Main Server & SSH for Samsung Tablet"
$shortcut.Save()

Write-Host "[✓] Desktop Shortcut created successfully:" -ForegroundColor Green
Write-Host "    $shortcutPath" -ForegroundColor Cyan
