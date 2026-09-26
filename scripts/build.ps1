param([switch]$Baseline, [int]$Jobs = 4, [string]$OutputDirectory = 'build')
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $project
$python = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
if (!(Test-Path $python)) { $python = (Get-Command python -ErrorAction Stop).Source }
if ($Baseline) { & $python scripts/prepare_rom.py --baseline } else { & $python scripts/prepare_rom.py }
if ($LASTEXITCODE -ne 0) { throw 'ROM preparation failed' }
$unixProject = '/'+$project.Substring(0,1).ToLower()+'/'+$project.Substring(3).Replace('\','/')
$command = 'export PATH=/ucrt64/bin:$PATH; cd "'+$unixProject+'/rom/pokefirered"; make -j'+$Jobs+' build/firered/sym_bss.ld build/firered/sym_common.ld build/firered/sym_ewram.ld'
& .tools/msys64/usr/bin/bash.exe -lc $command
if ($LASTEXITCODE -ne 0) { throw 'RAM layout build failed' }
& $python scripts/linker_compat.py
$command = 'export PATH=/ucrt64/bin:$PATH; cd "'+$unixProject+'/rom/pokefirered"; make -j'+$Jobs+' LD_SCRIPT=ld_script_flat.ld'
& .tools/msys64/usr/bin/bash.exe -lc $command
if ($LASTEXITCODE -ne 0) { throw 'ROM build failed' }
if ($Baseline) {
    $hash = (Get-FileHash rom/pokefirered/pokefirered.gba -Algorithm SHA1).Hash.ToLower()
    if ($hash -ne '41cb23d8dccc8ebd7c649cd8fbb58eeace6e2fdc') { throw "Baseline mismatch: $hash" }
    Copy-Item rom/pokefirered/pokefirered.gba build/firered-baseline.gba
} else {
    & $python scripts/package_build.py --output $OutputDirectory
    if ($LASTEXITCODE -ne 0) { throw 'Packaging failed' }
}
