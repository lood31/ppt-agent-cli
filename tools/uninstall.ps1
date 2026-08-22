[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "Programs\ppt-agent"),
    [switch]$RemoveState
)

$ErrorActionPreference = "Stop"

$installPath = [System.IO.Path]::GetFullPath($InstallDir)
$defaultBase = [System.IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA "Programs"))
if (-not $installPath.StartsWith($defaultBase + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to clean a path outside the current user's Programs directory: $installPath"
}

if ($PSCmdlet.ShouldProcess($installPath, "Uninstall ppt-agent")) {
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $entries = @($userPath -split ";" | Where-Object { $_ -and $_.Trim() })
    $pathWasPresent = $false
    $remaining = foreach ($entry in $entries) {
        $normalized = $entry.Trim().Trim('"').TrimEnd('\')
        if ($normalized -ine $installPath.TrimEnd('\')) {
            $entry.Trim()
        } else {
            $pathWasPresent = $true
        }
    }
    if ($pathWasPresent) {
        [Environment]::SetEnvironmentVariable("Path", ($remaining -join ";"), "User")
    }

    foreach ($name in @(
        "ppt-agent.exe",
        "README.md",
        "CHANGELOG.md",
        "THIRD_PARTY_NOTICES.md",
        "LICENSE",
        "install.json"
    )) {
        $item = Join-Path $installPath $name
        if (Test-Path -LiteralPath $item -PathType Leaf) {
            Remove-Item -LiteralPath $item -Force
        }
    }
    if ((Test-Path -LiteralPath $installPath -PathType Container) -and -not (Get-ChildItem -LiteralPath $installPath -Force)) {
        Remove-Item -LiteralPath $installPath
    }

    if ($RemoveState) {
        $statePath = [System.IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA "ppt-agent"))
        $expectedState = [System.IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA "ppt-agent"))
        if (-not [string]::Equals($statePath, $expectedState, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "State directory validation failed: $statePath"
        }
        if (Test-Path -LiteralPath $statePath -PathType Container) {
            Remove-Item -LiteralPath $statePath -Recurse -Force
        }
    }

    Write-Output "ppt-agent uninstalled. Open a new terminal to refresh PATH."
    if (-not $RemoveState) {
        Write-Output "Runtime state was preserved at $env:LOCALAPPDATA\ppt-agent. Re-run with -RemoveState to remove it explicitly."
    }
}
