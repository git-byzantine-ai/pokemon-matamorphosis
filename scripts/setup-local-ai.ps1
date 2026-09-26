param([switch]$OriginalModel)
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $project
New-Item -ItemType Directory -Force '.tools/models', '.tools/stable-diffusion' | Out-Null
$runtime = 'https://github.com/leejet/stable-diffusion.cpp/releases/download/master-899-28b454b/sd-master-28b454b-bin-win-vulkan-x64.zip'
$model = 'https://huggingface.co/stable-diffusion-v1-5/stable-diffusion-v1-5/resolve/451f4fe16113bff5a5d2269ed5ad43b0592e9a14/v1-5-pruned-emaonly.safetensors?download=true'
if (!(Test-Path '.tools/stable-diffusion/sd-cli.exe')) {
    Invoke-WebRequest $runtime -OutFile '.tools/sd-vulkan.zip'
    Expand-Archive '.tools/sd-vulkan.zip' '.tools/stable-diffusion' -Force
}
if ($OriginalModel -and !(Test-Path '.tools/models/sd15.safetensors')) {
    Invoke-WebRequest $model -OutFile '.tools/models/sd15.partial'
    Move-Item -LiteralPath '.tools/models/sd15.partial' -Destination '.tools/models/sd15.safetensors'
}
if (!$OriginalModel) { & $PSScriptRoot/setup-anatomy-model.ps1 }
Write-Host 'Local image model ready. No API key or per-image service fees.'
