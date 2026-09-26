$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
New-Item -ItemType Directory -Force .tools | Out-Null
if (!(Test-Path .tools/mGBA-0.10.5-win64/mGBA.exe)) {
    Invoke-WebRequest 'https://github.com/mgba-emu/mgba/releases/download/0.10.5/mGBA-0.10.5-win64.7z' -OutFile .tools/mgba.7z
    tar -xf .tools/mgba.7z -C .tools
    if ($LASTEXITCODE -ne 0) { throw 'mGBA extraction failed' }
}
Write-Host 'mGBA 0.10.5 installed in .tools/mGBA-0.10.5-win64.'
