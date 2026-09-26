$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $project
New-Item -ItemType Directory -Force '.tools/models' | Out-Null
$target = Join-Path $project '.tools/models/dreamshaper8.safetensors'
$partial = Join-Path $project '.tools/models/dreamshaper8.partial'
$expected = '879db523c30d3b9017143d56705015e15a2cb5628762c11d086fed9538abd7fd'
$url = 'https://huggingface.co/Lykon/DreamShaper/resolve/228d79cb20811466f5c5710aa91f05dabd0b8a14/DreamShaper_8_pruned.safetensors?download=true'
if (!(Test-Path -LiteralPath $target)) {
    & curl.exe --fail --location --retry 2 --silent --show-error --output $partial $url
    if ($LASTEXITCODE -ne 0) { throw 'Anatomy model download failed' }
    if ((Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash.ToLower() -ne $expected) { throw 'Anatomy model checksum mismatch' }
    Move-Item -LiteralPath $partial -Destination $target
}
if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLower() -ne $expected) { throw 'Installed anatomy model checksum mismatch' }
Write-Host 'DreamShaper 8 installed and SHA-256 verified. No API key or per-image fee.'
