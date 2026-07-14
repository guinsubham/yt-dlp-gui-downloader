[CmdletBinding()]
param(
    [switch]$VerifyOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$repository = "guinsubham/yt-dlp-gui-downloader"
$assetName = "YT-DLP-GUI-Windows.zip"
$apiUrl = "https://api.github.com/repos/$repository/releases/latest"
$headers = @{
    Accept = "application/vnd.github+json"
    "User-Agent" = "YT-DLP-GUI-Installer"
    "X-GitHub-Api-Version" = "2022-11-28"
}
$tempDirectory = Join-Path ([System.IO.Path]::GetTempPath()) ("YT-DLP-GUI-" + [guid]::NewGuid().ToString("N"))

function Write-Step {
    param([Parameter(Mandatory)][string]$Message)

    Write-Host "==> $Message" -ForegroundColor Cyan
}

try {
    # Windows PowerShell 5.1 may otherwise negotiate an obsolete TLS version.
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

    Write-Step "Finding the latest YT-DLP GUI Downloader release..."
    $release = Invoke-RestMethod -Uri $apiUrl -Headers $headers
    $asset = @($release.assets) | Where-Object { $_.name -eq $assetName } | Select-Object -First 1

    if ($null -eq $asset) {
        throw "The latest release does not contain $assetName."
    }

    $digest = if ($null -ne $asset.PSObject.Properties["digest"]) { [string]$asset.digest } else { "" }
    $digestMatch = [regex]::Match($digest, "^sha256:([0-9a-fA-F]{64})$")
    if (-not $digestMatch.Success) {
        throw "GitHub did not provide a valid SHA-256 digest for $assetName."
    }

    $expectedHash = $digestMatch.Groups[1].Value.ToUpperInvariant()
    New-Item -ItemType Directory -Path $tempDirectory | Out-Null
    $archivePath = Join-Path $tempDirectory $assetName
    $packageDirectory = Join-Path $tempDirectory "package"

    Write-Step "Downloading version $($release.tag_name)..."
    Invoke-WebRequest -Uri $asset.browser_download_url -Headers $headers -OutFile $archivePath -UseBasicParsing

    Write-Step "Verifying the downloaded package..."
    $actualHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash
    if ($actualHash -ne $expectedHash) {
        throw "The downloaded package failed SHA-256 verification. Installation was stopped."
    }

    Write-Step "Preparing the installer..."
    Expand-Archive -LiteralPath $archivePath -DestinationPath $packageDirectory -Force
    $installerPath = Join-Path $packageDirectory "Install-YT-DLP-GUI.bat"
    $requiredFiles = @(
        $installerPath
        (Join-Path $packageDirectory "Uninstall-YT-DLP-GUI.bat")
        (Join-Path $packageDirectory "YT-DLP-GUI.exe")
    )

    foreach ($requiredFile in $requiredFiles) {
        if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
            throw "The verified package is incomplete: $(Split-Path -Leaf $requiredFile) is missing."
        }
    }

    if ($VerifyOnly) {
        Write-Host "Version $($release.tag_name) was downloaded and verified successfully." -ForegroundColor Green
        return
    }

    Write-Step "Installing for the current Windows user..."
    & $installerPath
    if ($LASTEXITCODE -ne 0) {
        throw "The packaged installer exited with code $LASTEXITCODE."
    }

    Write-Host "YT-DLP GUI Downloader is ready." -ForegroundColor Green
}
catch {
    Write-Host "Installation failed: $($_.Exception.Message)" -ForegroundColor Red
    throw
}
finally {
    if (Test-Path -LiteralPath $tempDirectory) {
        Remove-Item -LiteralPath $tempDirectory -Recurse -Force -ErrorAction SilentlyContinue
    }
}
