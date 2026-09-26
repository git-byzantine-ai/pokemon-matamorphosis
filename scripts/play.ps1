param([switch]$Preview)
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $project
if (!(Test-Path build/firered-metamorphosis.gba)) { throw 'Build the ROM first: scripts/build.ps1' }
if (!(Test-Path .tools/mGBA-0.10.5-win64/mGBA.exe)) { & $PSScriptRoot/setup-emulator.ps1 }
$python = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
if (!(Test-Path $python)) { $python = (Get-Command python -ErrorAction Stop).Source }
if (Test-Path build/pending-update/READY) {
    if (Get-Process mGBA -ErrorAction SilentlyContinue) {
        throw 'A game update is ready. Save through the game menu and close mGBA, then run this launcher again.'
    }
    & $python scripts/apply_pending_update.py
    if ($LASTEXITCODE -ne 0) { throw 'Game update failed; see the error above.' }
}
$alive = $false
$status = $null
try { $status = Invoke-RestMethod http://127.0.0.1:8766/api/status -TimeoutSec 2; $alive = $status.provider -ne $null } catch {}
$protocol = (Get-Content build/bridge.json -Raw | ConvertFrom-Json).protocol
if ($alive -and $status.protocol -ne $protocol) {
    if (Get-Process mGBA -ErrorAction SilentlyContinue) {
        throw 'Save through the game menu and close mGBA before upgrading the companion.'
    }
    if (!(Test-Path runtime/companion.pid)) { throw 'An older companion is running. Close that companion, then run this launcher again.' }
    $companionPid = [int](Get-Content runtime/companion.pid)
    $oldCompanion = Get-CimInstance Win32_Process -Filter "ProcessId = $companionPid"
    if (!$oldCompanion -or $oldCompanion.CommandLine -notmatch 'companion\.server' -or $oldCompanion.ExecutablePath -ne $python) {
        throw 'Could not identify the older companion safely. Close it, then run this launcher again.'
    }
    Stop-Process -Id $companionPid
    Wait-Process -Id $companionPid -ErrorAction SilentlyContinue
    $alive = $false
}
if (!$alive) {
    New-Item -ItemType Directory -Force runtime | Out-Null
    $config = if (Test-Path config.local.json) { 'config.local.json' } else { 'config.example.json' }
    $arguments = @('-m', 'companion.server', '--config', $config)
    if ($Preview) { $arguments += '--preview' }
    $companion = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $project -WindowStyle Hidden -RedirectStandardOutput runtime/companion.stdout.log -RedirectStandardError runtime/companion.stderr.log -PassThru
    $companion.Id | Set-Content runtime/companion.pid
    $ready = $false
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        Start-Sleep -Milliseconds 250
        try { $ready = (Invoke-RestMethod http://127.0.0.1:8766/api/status -TimeoutSec 1).protocol -eq $protocol } catch {}
        if ($ready) { break }
        if ($companion.HasExited) { break }
    }
    if (!$ready) { throw 'Companion failed to start. See runtime/companion.stderr.log.' }
}
Write-Host 'In mGBA: Tools > Scripting > File > Load script, then choose build/metamorphosis.lua.'
Write-Host 'Load the script once per emulator session. Dashboard: http://127.0.0.1:8766'
& .tools/mGBA-0.10.5-win64/mGBA.exe build/firered-metamorphosis.gba
