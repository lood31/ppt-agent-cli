$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"

& $python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --name ppt-agent `
  --version-file (Join-Path $projectRoot "tools\version_info.txt") `
  --paths (Join-Path $projectRoot "src") `
  --add-data "$(Join-Path $projectRoot 'vendor\hands_on_deck');vendor\hands_on_deck" `
  (Join-Path $projectRoot "tools\entrypoint.py")
