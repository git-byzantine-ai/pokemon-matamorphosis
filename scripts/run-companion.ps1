param([switch]$Preview)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$python = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
if (!(Test-Path $python)) { $python = (Get-Command python -ErrorAction Stop).Source }
$config = if (Test-Path config.local.json) { 'config.local.json' } else { 'config.example.json' }
if ($Preview) { & $python -m companion.server --config $config --preview }
else { & $python -m companion.server --config $config }
