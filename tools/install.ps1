[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$Source,
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "Programs\ppt-agent"),
    [switch]$NoPath
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$packageExe = Join-Path $PSScriptRoot "ppt-agent.exe"
if (-not $Source) {
    if (Test-Path -LiteralPath $packageExe -PathType Leaf) {
        $Source = $packageExe
        $projectRoot = $PSScriptRoot
    } else {
        $Source = Join-Path $projectRoot "dist\ppt-agent.exe"
    }
}
$sourcePath = [System.IO.Path]::GetFullPath($Source)
$installPath = [System.IO.Path]::GetFullPath($InstallDir)
$targetExe = Join-Path $installPath "ppt-agent.exe"
$defaultBase = [System.IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA "Programs"))

if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
    throw "Source executable not found: $sourcePath"
}
if ([System.IO.Path]::GetExtension($sourcePath) -ne ".exe") {
    throw "Install source must be an .exe file: $sourcePath"
}
if (-not $installPath.StartsWith($defaultBase + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "InstallDir must be inside the current user's Programs directory: $defaultBase"
}

if ($PSCmdlet.ShouldProcess($targetExe, "Install ppt-agent")) {
    New-Item -ItemType Directory -Path $installPath -Force | Out-Null
    Copy-Item -LiteralPath $sourcePath -Destination $targetExe -Force

    foreach ($name in @("README.md", "CHANGELOG.md", "THIRD_PARTY_NOTICES.md", "LICENSE")) {
        $item = Join-Path $projectRoot $name
        if (Test-Path -LiteralPath $item -PathType Leaf) {
            Copy-Item -LiteralPath $item -Destination (Join-Path $installPath $name) -Force
        }
    }

    $pathAdded = $false
    if (-not $NoPath) {
        $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
        $entries = @($userPath -split ";" | Where-Object { $_ -and $_.Trim() })
        $alreadyPresent = $entries | Where-Object {
            $_.Trim().Trim('"').TrimEnd('\') -ieq $installPath.TrimEnd('\')
        }
        if (-not $alreadyPresent) {
            $newPath = (@($entries) + $installPath) -join ";"
            [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
            $pathAdded = $true
        }
    }

    $metadata = [ordered]@{
        installed_at = [DateTimeOffset]::Now.ToString("o")
        executable = $targetExe
        path_entry = $installPath
        path_added = $pathAdded
        sha256 = (Get-FileHash -LiteralPath $targetExe -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $metadata | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $installPath "install.json") -Encoding utf8

    $version = & $targetExe --version
    if ($LASTEXITCODE -ne 0) {
        throw "The executable was copied but its version smoke test failed with exit code $LASTEXITCODE"
    }
    Write-Output "ppt-agent $version installed at $targetExe"
    if ($pathAdded) {
        Write-Output "The user PATH was updated. Open a new terminal before invoking ppt-agent."
    }
}
