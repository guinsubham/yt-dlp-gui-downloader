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
$maximumArchiveSize = 512MB
$maximumMemberSize = 300MB
$maximumExtractedSize = 600MB
$requiredNames = @(
    "Install-YT-DLP-GUI.bat"
    "LICENSE"
    "THIRD_PARTY_NOTICES.md"
    "Uninstall-YT-DLP-GUI.bat"
    "YT-DLP-GUI.exe"
)

function Write-Step {
    param([Parameter(Mandatory)][string]$Message)

    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Test-DownloadUri {
    param([Parameter(Mandatory)][uri]$Uri)

    $allowedHosts = @(
        "github.com"
        "objects.githubusercontent.com"
        "release-assets.githubusercontent.com"
    )
    if ($Uri.Scheme -ne "https" -or $Uri.Host -notin $allowedHosts -or $Uri.UserInfo) {
        throw "The package address did not pass the security policy."
    }
}

function Save-VerifiedSizeDownload {
    param(
        [Parameter(Mandatory)][uri]$Uri,
        [Parameter(Mandatory)][string]$Destination,
        [Parameter(Mandatory)][long]$ExpectedSize,
        [Parameter(Mandatory)][long]$MaximumSize
    )

    Add-Type -AssemblyName System.Net.Http
    $handler = [System.Net.Http.HttpClientHandler]::new()
    $handler.AllowAutoRedirect = $false
    $client = [System.Net.Http.HttpClient]::new($handler)
    $client.DefaultRequestHeaders.UserAgent.ParseAdd("YT-DLP-GUI-Installer")
    $currentUri = $Uri
    $response = $null

    try {
        for ($redirectCount = 0; $redirectCount -le 5; $redirectCount++) {
            Test-DownloadUri -Uri $currentUri
            $response = $client.GetAsync(
                $currentUri,
                [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead
            ).GetAwaiter().GetResult()

            if ([int]$response.StatusCode -in @(301, 302, 303, 307, 308)) {
                if ($redirectCount -eq 5 -or $null -eq $response.Headers.Location) {
                    throw "The package download exceeded the redirect limit."
                }
                $nextUri = if ($response.Headers.Location.IsAbsoluteUri) {
                    $response.Headers.Location
                }
                else {
                    [uri]::new($currentUri, $response.Headers.Location)
                }
                Test-DownloadUri -Uri $nextUri
                $response.Dispose()
                $response = $null
                $currentUri = $nextUri
                continue
            }

            [void]$response.EnsureSuccessStatusCode()
            if ($response.Content.Headers.ContentLength -and $response.Content.Headers.ContentLength -ne $ExpectedSize) {
                throw "The package server reported an unexpected file size."
            }

            $source = $response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
            $destinationStream = [System.IO.File]::Create($Destination)
            try {
                $buffer = New-Object byte[] (1MB)
                [long]$downloaded = 0
                while (($read = $source.Read($buffer, 0, $buffer.Length)) -gt 0) {
                    $downloaded += $read
                    if ($downloaded -gt $ExpectedSize -or $downloaded -gt $MaximumSize) {
                        throw "The package download exceeded its verified size."
                    }
                    $destinationStream.Write($buffer, 0, $read)
                }
                if ($downloaded -ne $ExpectedSize) {
                    throw "The downloaded package size did not match GitHub metadata."
                }
            }
            finally {
                $destinationStream.Dispose()
                $source.Dispose()
            }
            return
        }
    }
    finally {
        if ($null -ne $response) {
            $response.Dispose()
        }
        $client.Dispose()
        $handler.Dispose()
    }
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

    $reportedSize = [long]$asset.size
    if ($reportedSize -le 0 -or $reportedSize -gt $maximumArchiveSize) {
        throw "GitHub reported an invalid package size."
    }

    $downloadUri = [uri]$asset.browser_download_url
    Test-DownloadUri -Uri $downloadUri

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
    Save-VerifiedSizeDownload -Uri $downloadUri -Destination $archivePath -ExpectedSize $reportedSize -MaximumSize $maximumArchiveSize

    Write-Step "Verifying the downloaded package..."
    $actualHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash
    if ($actualHash -ne $expectedHash) {
        throw "The downloaded package failed SHA-256 verification. Installation was stopped."
    }

    Write-Step "Preparing the installer..."
    New-Item -ItemType Directory -Path $packageDirectory | Out-Null
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($archivePath)
    try {
        $selectedEntries = @{}
        [long]$totalExtractedSize = 0
        foreach ($name in $requiredNames) {
            $matches = @($archive.Entries | Where-Object { $_.FullName -eq $name -and $_.Name })
            if ($matches.Count -ne 1) {
                throw "The verified package must contain exactly one $name file."
            }
            $entry = $matches[0]
            if ($entry.Length -lt 0 -or $entry.Length -gt $maximumMemberSize) {
                throw "The verified package contains an oversized $name file."
            }
            $totalExtractedSize += $entry.Length
            if ($totalExtractedSize -gt $maximumExtractedSize) {
                throw "The verified package exceeded the extraction limit."
            }
            $selectedEntries[$name] = $entry
        }

        $buffer = New-Object byte[] (1MB)
        foreach ($name in $requiredNames) {
            $entry = $selectedEntries[$name]
            $destinationPath = Join-Path $packageDirectory $name
            $source = $entry.Open()
            $destination = [System.IO.File]::Create($destinationPath)
            try {
                [long]$copied = 0
                while (($read = $source.Read($buffer, 0, $buffer.Length)) -gt 0) {
                    $copied += $read
                    if ($copied -gt $entry.Length -or $copied -gt $maximumMemberSize) {
                        throw "The extracted $name file exceeded its verified size."
                    }
                    $destination.Write($buffer, 0, $read)
                }
                if ($copied -ne $entry.Length) {
                    throw "The extracted $name file did not match its archive metadata."
                }
            }
            finally {
                $destination.Dispose()
                $source.Dispose()
            }
        }
    }
    finally {
        $archive.Dispose()
    }

    $installerPath = Join-Path $packageDirectory "Install-YT-DLP-GUI.bat"
    $requiredFiles = $requiredNames | ForEach-Object { Join-Path $packageDirectory $_ }

    foreach ($requiredFile in $requiredFiles) {
        if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
            throw "The verified package is incomplete: $(Split-Path -Leaf $requiredFile) is missing."
        }
    }

    if ($VerifyOnly) {
        $env:YT_DLP_GUI_VERIFY_ONLY = "1"
        try {
            & $installerPath
            if ($LASTEXITCODE -ne 0) {
                throw "The packaged installer fingerprint check exited with code $LASTEXITCODE."
            }
        }
        finally {
            Remove-Item Env:YT_DLP_GUI_VERIFY_ONLY -ErrorAction SilentlyContinue
        }
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
