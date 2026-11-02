param(
    [string]$InstallRoot=(Join-Path $env:LOCALAPPDATA 'Programs\MediaDesk'),
    [string]$RuntimeRoot=(Join-Path $env:LOCALAPPDATA 'Programs\MediaDesk-runtime'),
    [string]$SourceRoot=(Split-Path (Split-Path $PSScriptRoot -Parent) -Parent),
    [string]$PayloadRoot='',
    [string]$ShortcutRoot=(Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\MediaDesk'),
    [switch]$NoShortcut
)
. (Join-Path $PSScriptRoot 'common.ps1')
if (-not [Environment]::Is64BitOperatingSystem) {throw 'This installer requires Windows x64'}
$InstallRoot=[IO.Path]::GetFullPath($InstallRoot).TrimEnd('\')
$RuntimeRoot=[IO.Path]::GetFullPath($RuntimeRoot).TrimEnd('\')
if ($InstallRoot -eq $RuntimeRoot -or $InstallRoot.StartsWith($RuntimeRoot+'\',[StringComparison]::OrdinalIgnoreCase) -or $RuntimeRoot.StartsWith($InstallRoot+'\',[StringComparison]::OrdinalIgnoreCase)) {throw 'Application and runtime directories must be separate'}
Assert-MediaDeskInstallRootAvailable $InstallRoot
if (-not (Test-Path -LiteralPath (Join-Path $SourceRoot 'mediadesk\__main__.py'))) {throw 'Missing application source; extract the complete MediaDesk package before running setup.'}
if (-not $PayloadRoot) {$PayloadRoot=Join-Path $SourceRoot 'runtime-payload'}
if (-not (Test-Path -LiteralPath (Join-Path $PayloadRoot 'runtime-files.json'))) {throw 'Missing prebuilt runtime payload. Download the complete MediaDesk installer package; no development environment is required.'}
$log=Join-Path $env:TEMP ('MediaDesk-setup-'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'.log')
Start-Transcript -Path $log | Out-Null
try {
    Write-Output 'MediaDesk setup: verifying and copying the included application runtime. No additional software download is required.'
    & (Join-Path $PSScriptRoot 'install-runtime-payload.ps1') -PayloadRoot $PayloadRoot -RuntimeRoot $RuntimeRoot
    if (-not (Test-Path -LiteralPath (Join-Path $RuntimeRoot 'install-manifest.json'))) {
        & (Join-Path $PSScriptRoot 'runtime-manifest.ps1') -RuntimeRoot $RuntimeRoot -PayloadReceipt (Join-Path $RuntimeRoot 'payload-receipt.json')
    }
    Write-Output 'MediaDesk stage: installing application files and Start menu entries'
    $bin=Join-Path $RuntimeRoot 'bin'
    & (Join-Path $PSScriptRoot 'install.ps1') -RuntimeBin $bin -VlcDir (Join-Path $RuntimeRoot 'vlc') -VlcPluginPath (Join-Path $RuntimeRoot 'vlc\plugins') -ManagedRuntimeRoot $RuntimeRoot -ToolDirectories @($bin,(Join-Path $RuntimeRoot 'tools\ffmpeg\bin'),(Join-Path $RuntimeRoot 'tools\node')) -SourceRoot $SourceRoot -InstallRoot $InstallRoot -ShortcutRoot $ShortcutRoot -NoShortcut:$NoShortcut
    Write-Output 'MediaDesk setup completed. Launch MediaDesk from the Start menu.'
} finally {
    Stop-Transcript | Out-Null
    Write-Output ('Setup log: '+$log)
}
