$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $project
$python = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
if (!(Test-Path $python)) { $python = (Get-Command python -ErrorAction Stop).Source }
New-Item -ItemType Directory -Force .tools, build | Out-Null
& $python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Python dependencies failed' }
if (!(Test-Path .tools/msys64/usr/bin/bash.exe)) {
    Invoke-WebRequest 'https://repo.msys2.org/distrib/x86_64/msys2-base-x86_64-20260611.tar.xz' -OutFile .tools/msys2.tar.xz
    tar -xf .tools/msys2.tar.xz -C .tools
    if ($LASTEXITCODE -ne 0) { throw 'MSYS2 extraction failed' }
}
& .tools/msys64/usr/bin/bash.exe -lc 'pacman -Sy --noconfirm'
if ($LASTEXITCODE -ne 0) { throw 'Package index update failed' }
& .tools/msys64/usr/bin/bash.exe -lc 'pacman -S --needed --noconfirm make gcc zlib-devel git perl lua mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-libpng mingw-w64-ucrt-x86_64-arm-none-eabi-binutils'
if ($LASTEXITCODE -ne 0) { throw 'Build dependencies failed; restart this script in a fresh shell if MSYS2 updated its runtime' }
& $python scripts/prepare_rom.py --baseline
if ($LASTEXITCODE -ne 0) { throw 'Source preparation failed' }
$agbccRevision = 'da598c1d918402c42c0c0d7128ba14567f3175e9'
if (!(Test-Path .tools/agbcc-source/pret-agbcc-da598c1/build.sh)) {
    Invoke-WebRequest "https://api.github.com/repos/pret/agbcc/zipball/$agbccRevision" -OutFile .tools/agbcc.zip
    Expand-Archive .tools/agbcc.zip .tools/agbcc-source -Force
}
$unixProject = '/'+$project.Substring(0,1).ToLower()+'/'+$project.Substring(3).Replace('\','/')
if (!(Test-Path .tools/agbcc-source/pret-agbcc-da598c1/libc.a)) {
    $command = 'export PATH=/ucrt64/bin:$PATH; cd "'+$unixProject+'/.tools/agbcc-source/pret-agbcc-da598c1"; ./build.sh'
    & .tools/msys64/usr/bin/bash.exe -lc $command
    if ($LASTEXITCODE -ne 0) { throw 'agbcc compilation failed' }
}
$command = 'export PATH=/ucrt64/bin:$PATH; cd "'+$unixProject+'/.tools/agbcc-source/pret-agbcc-da598c1"; ./install.sh "'+$unixProject+'/rom/pokefirered"'
& .tools/msys64/usr/bin/bash.exe -lc $command
if ($LASTEXITCODE -ne 0) { throw 'agbcc installation failed' }
Write-Host 'Build dependencies installed. Run scripts/build.ps1 -Baseline, then scripts/build.ps1.'
