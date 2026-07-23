[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$installDirectory = Join-Path $env:LOCALAPPDATA "Programs\YT-DLP-GUI"
$installedExecutable = Join-Path $installDirectory "YT-DLP-GUI.exe"
$startMenuDirectory = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\YT-DLP GUI Downloader"
$systemPowerShell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"

try {
    Write-Host "Uninstalling YT-DLP GUI Downloader..." -ForegroundColor Cyan
    $targets = @(
        Get-CimInstance Win32_Process -Filter "Name = 'YT-DLP-GUI.exe'" -ErrorAction SilentlyContinue |
            Where-Object {
                $_.ExecutablePath -and
                [StringComparer]::OrdinalIgnoreCase.Equals($_.ExecutablePath, $installedExecutable)
            }
    )

    foreach ($target in $targets) {
        $process = Get-Process -Id $target.ProcessId -ErrorAction SilentlyContinue
        if ($null -ne $process) {
            [void]$process.CloseMainWindow()
        }
    }

    $deadline = [DateTime]::UtcNow.AddSeconds(3)
    while ([DateTime]::UtcNow -lt $deadline) {
        $remaining = @($targets | Where-Object { Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue })
        if ($remaining.Count -eq 0) {
            break
        }
        Start-Sleep -Milliseconds 100
    }
    foreach ($target in $targets) {
        Stop-Process -Id $target.ProcessId -Force -ErrorAction SilentlyContinue
    }

    $desktop = [Environment]::GetFolderPath("Desktop")
    Remove-Item -LiteralPath (Join-Path $desktop "YT-DLP GUI Downloader.lnk") -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $startMenuDirectory -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\YT-DLP-GUI" -Recurse -Force -ErrorAction SilentlyContinue

    $cleanupCommand = "Start-Sleep -Seconds 2; Remove-Item -LiteralPath '" +
        $installDirectory.Replace("'", "''") +
        "' -Recurse -Force -ErrorAction SilentlyContinue"
    $encodedCleanupCommand = [Convert]::ToBase64String(
        [Text.Encoding]::Unicode.GetBytes($cleanupCommand)
    )
    Start-Process -FilePath $systemPowerShell -WindowStyle Hidden -ArgumentList @(
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-EncodedCommand",
        $encodedCleanupCommand
    )
    Write-Host "YT-DLP GUI Downloader was removed." -ForegroundColor Green
    exit 0
}
catch {
    Write-Host "Uninstallation failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
