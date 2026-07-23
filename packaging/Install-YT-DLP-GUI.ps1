[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$appName = "YT-DLP GUI Downloader"
$appVersion = "__APP_VERSION__"
$expectedHash = "__EXPECTED_HASH__"
$packageDirectory = $PSScriptRoot
$sourceExecutable = Join-Path $packageDirectory "YT-DLP-GUI.exe"
$sourceUninstaller = Join-Path $packageDirectory "Uninstall-YT-DLP-GUI.bat"
$sourceUninstallerScript = Join-Path $packageDirectory "Uninstall-YT-DLP-GUI.ps1"
$sourceLicense = Join-Path $packageDirectory "LICENSE"
$sourceNotices = Join-Path $packageDirectory "THIRD_PARTY_NOTICES.md"
$sourceThirdPartyLicenses = Join-Path $packageDirectory "third_party_licenses"
$installDirectory = Join-Path $env:LOCALAPPDATA "Programs\YT-DLP-GUI"
$installParent = Split-Path -Parent $installDirectory
$installedExecutable = Join-Path $installDirectory "YT-DLP-GUI.exe"
$startMenuDirectory = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\YT-DLP GUI Downloader"
$transactionId = [guid]::NewGuid().ToString("N")
$stagingDirectory = "$installDirectory.staging-$transactionId"
$backupDirectory = "$installDirectory.backup-$transactionId"
$activated = $false
$hadExistingInstallation = $false
$transactionComplete = $false
$requiredLicenseNames = @(
    "brotli-LICENSE.txt",
    "certifi-LICENSE.txt",
    "charset-normalizer-LICENSE.txt",
    "idna-LICENSE.md",
    "Pillow-LICENSE.txt",
    "pycryptodomex-LICENSE.rst",
    "pyinstaller-COPYING.txt",
    "requests-LICENSE.txt",
    "requests-NOTICE.txt",
    "urllib3-LICENSE.txt",
    "websockets-LICENSE.txt",
    "yt-dlp-ejs-LICENSE.txt",
    "yt-dlp-UNLICENSE.txt"
)

function Assert-File {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "The package is missing $(Split-Path -Leaf $Path)."
    }
}

function New-Link {
    param(
        [Parameter(Mandatory)][object]$Shell,
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Target
    )
    $link = $Shell.CreateShortcut($Path)
    $link.TargetPath = $Target
    $link.WorkingDirectory = $installDirectory
    $link.IconLocation = $installedExecutable
    $link.Save()
}

try {
    Write-Host "Installing $appName..." -ForegroundColor Cyan
    Assert-File $sourceExecutable
    Assert-File $sourceUninstaller
    Assert-File $sourceUninstallerScript
    Assert-File $sourceLicense
    Assert-File $sourceNotices
    if (-not (Test-Path -LiteralPath $sourceThirdPartyLicenses -PathType Container)) {
        throw "The package is missing third_party_licenses."
    }
    foreach ($licenseName in $requiredLicenseNames) {
        Assert-File (Join-Path $sourceThirdPartyLicenses $licenseName)
    }

    if ($expectedHash -notmatch "^[0-9A-Fa-f]{64}$") {
        throw "The package does not contain a valid application fingerprint."
    }
    $actualHash = (Get-FileHash -LiteralPath $sourceExecutable -Algorithm SHA256).Hash
    if ($actualHash -ne $expectedHash) {
        throw "The application fingerprint does not match this installer."
    }

    if ($env:YT_DLP_GUI_VERIFY_ONLY) {
        Write-Host "Package fingerprint verified." -ForegroundColor Green
        exit 0
    }

    $runningInstalledProcesses = @(
        Get-CimInstance Win32_Process -Filter "Name = 'YT-DLP-GUI.exe'" -ErrorAction SilentlyContinue |
            Where-Object {
                $_.ExecutablePath -and
                [StringComparer]::OrdinalIgnoreCase.Equals($_.ExecutablePath, $installedExecutable)
            }
    )
    if ($runningInstalledProcesses.Count -gt 0) {
        throw "Close every installed YT-DLP GUI Downloader window before installing."
    }

    New-Item -ItemType Directory -Path $installParent -Force | Out-Null
    New-Item -ItemType Directory -Path $stagingDirectory | Out-Null
    Copy-Item -LiteralPath $sourceExecutable -Destination (Join-Path $stagingDirectory "YT-DLP-GUI.exe")
    Copy-Item -LiteralPath $sourceUninstaller -Destination (Join-Path $stagingDirectory "Uninstall-YT-DLP-GUI.bat")
    Copy-Item -LiteralPath $sourceUninstallerScript -Destination (Join-Path $stagingDirectory "Uninstall-YT-DLP-GUI.ps1")
    Copy-Item -LiteralPath $sourceLicense -Destination (Join-Path $stagingDirectory "LICENSE")
    Copy-Item -LiteralPath $sourceNotices -Destination (Join-Path $stagingDirectory "THIRD_PARTY_NOTICES.md")
    Copy-Item -LiteralPath $sourceThirdPartyLicenses -Destination $stagingDirectory -Recurse

    foreach ($preservedName in @("runtime", "cache", "update.log")) {
        $preservedPath = Join-Path $installDirectory $preservedName
        if (Test-Path -LiteralPath $preservedPath) {
            Copy-Item -LiteralPath $preservedPath -Destination $stagingDirectory -Recurse
        }
    }

    if (Test-Path -LiteralPath $installDirectory) {
        $hadExistingInstallation = $true
        Move-Item -LiteralPath $installDirectory -Destination $backupDirectory
    }
    Move-Item -LiteralPath $stagingDirectory -Destination $installDirectory
    $activated = $true

    New-Item -ItemType Directory -Path $startMenuDirectory -Force | Out-Null
    $shell = New-Object -ComObject WScript.Shell
    $desktop = [Environment]::GetFolderPath("Desktop")
    New-Link $shell (Join-Path $desktop "YT-DLP GUI Downloader.lnk") $installedExecutable
    New-Link $shell (Join-Path $startMenuDirectory "YT-DLP GUI Downloader.lnk") $installedExecutable
    New-Link $shell (Join-Path $startMenuDirectory "Uninstall YT-DLP GUI Downloader.lnk") (Join-Path $installDirectory "Uninstall-YT-DLP-GUI.bat")

    $uninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\YT-DLP-GUI"
    New-Item -Path $uninstallKey -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name DisplayName -Value $appName -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name DisplayVersion -Value $appVersion -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name DisplayIcon -Value $installedExecutable -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name InstallLocation -Value $installDirectory -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name UninstallString -Value ('"' + (Join-Path $installDirectory "Uninstall-YT-DLP-GUI.bat") + '"') -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name NoModify -Value 1 -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name NoRepair -Value 1 -PropertyType DWord -Force | Out-Null

    $transactionComplete = $true
    Write-Host "$appName was installed successfully." -ForegroundColor Green
    if (-not $env:YT_DLP_GUI_NO_LAUNCH) {
        try {
            Start-Process -FilePath $installedExecutable -WorkingDirectory $installDirectory
        }
        catch {
            Write-Warning "The application was installed but could not be started: $($_.Exception.Message)"
        }
    }
    if (Test-Path -LiteralPath $backupDirectory) {
        Remove-Item -LiteralPath $backupDirectory -Recurse -Force -ErrorAction SilentlyContinue
    }
    exit 0
}
catch {
    if (-not $transactionComplete -and $activated -and (Test-Path -LiteralPath $installDirectory)) {
        Remove-Item -LiteralPath $installDirectory -Recurse -Force -ErrorAction SilentlyContinue
    }
    if (-not $transactionComplete -and $hadExistingInstallation -and (Test-Path -LiteralPath $backupDirectory)) {
        Move-Item -LiteralPath $backupDirectory -Destination $installDirectory -ErrorAction SilentlyContinue
    }
    Write-Host "Installation failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
finally {
    if (Test-Path -LiteralPath $stagingDirectory) {
        Remove-Item -LiteralPath $stagingDirectory -Recurse -Force -ErrorAction SilentlyContinue
    }
}
