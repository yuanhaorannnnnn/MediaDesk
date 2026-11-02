param([switch]$CheckOnly)
. (Join-Path $PSScriptRoot 'common.ps1')
$config=Get-Content (Join-Path $PSScriptRoot 'runtime.json') -Raw | ConvertFrom-Json
Set-MediaDeskEnvironment $config $PSScriptRoot
$python=Join-Path $config.RuntimeBin 'python.exe'
if ($CheckOnly) {
    & $python -B (Join-Path $PSScriptRoot 'doctor.py')
    exit $LASTEXITCODE
}
# Pythonw keeps the window independent of a terminal; application data stays in LOCALAPPDATA\MediaDesk.
$pythonw=Join-Path $config.RuntimeBin 'pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonw -PathType Leaf)) {throw 'Missing pythonw.exe in the configured runtime'}
& $pythonw -B -m mediadesk
exit $LASTEXITCODE
