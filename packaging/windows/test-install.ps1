param([Parameter(Mandatory=$true)][string]$RuntimeBin,[Parameter(Mandatory=$true)][string]$VlcDir,[Parameter(Mandatory=$true)][string]$PythonPackages,[switch]$ExpectMissingPackages)
$ErrorActionPreference='Stop'
$source=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$testRoot=Join-Path $env:TEMP ('md-install-test-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot | Out-Null
$env:LOCALAPPDATA=Join-Path $testRoot 'local-data'
$env:APPDATA=Join-Path $testRoot 'roaming-data'
$data=Join-Path $env:LOCALAPPDATA 'MediaDesk\media'
New-Item -ItemType Directory -Force -Path $data | Out-Null
$sentinel=Join-Path $data 'synthetic-user-file.txt'
Set-Content -LiteralPath $sentinel 'keep-me' -Encoding UTF8
$hash=(Get-FileHash -LiteralPath $sentinel).Hash
$target=Join-Path $testRoot 'program'
$shortcuts=Join-Path $testRoot 'shortcuts'
$results=@{}
function Assert-True($Condition,[string]$Message) {if (-not $Condition) {throw $Message}}
# Empty runtime must fail without creating an installation directory.
$badRuntime=Join-Path $testRoot 'empty-runtime'
New-Item -ItemType Directory -Path $badRuntime | Out-Null
$failed=$false
try {& (Join-Path $PSScriptRoot 'install.ps1') -RuntimeBin $badRuntime -VlcDir $VlcDir -InstallRoot $target -SourceRoot $source -NoShortcut} catch {$failed=$true}
Assert-True ($failed -and -not (Test-Path -LiteralPath $target)) 'Incomplete dependency environment wrote an installation'
$results['missing_runtime_refused']=$true
if ($ExpectMissingPackages) {
    $failed=$false
    try {& (Join-Path $PSScriptRoot 'install.ps1') -RuntimeBin $RuntimeBin -VlcDir $VlcDir -InstallRoot $target -SourceRoot $source -NoShortcut} catch {$failed=$true}
    Assert-True ($failed -and -not (Test-Path -LiteralPath $target)) 'Missing packages were not rejected before install'
    $results['missing_packages_refused']=$true
}

New-Item -ItemType Directory -Path $target | Out-Null
& (Join-Path $PSScriptRoot 'install.ps1') -RuntimeBin $RuntimeBin -VlcDir $VlcDir -PythonPackages @($PythonPackages) -InstallRoot $target -ShortcutRoot $shortcuts -SourceRoot $source
Assert-True (Test-Path -LiteralPath (Join-Path $target 'install-manifest.json')) 'Missing install manifest'
& (Join-Path $target 'start.ps1') -CheckOnly
Assert-True ($LASTEXITCODE -eq 0) 'Installed launcher failed dependency preflight'
$results['installed_preflight']=$true
Assert-True (Test-Path -LiteralPath (Join-Path $shortcuts 'MediaDesk.lnk')) 'Missing launch shortcut'
$icon=Join-Path $target 'mediadesk.ico'
Assert-True (Test-Path -LiteralPath $icon -PathType Leaf) 'Missing installed shortcut icon'
$manifest=Get-Content -LiteralPath (Join-Path $target 'install-manifest.json') -Raw | ConvertFrom-Json
Assert-True (@($manifest.Files | Where-Object {$_.Path -eq 'mediadesk.ico' -and $_.SHA256 -eq (Get-FileHash -LiteralPath $icon -Algorithm SHA256).Hash}).Count -eq 1) 'Shortcut icon is not tracked by install manifest'
$shell=New-Object -ComObject WScript.Shell
foreach ($name in @('MediaDesk.lnk','Uninstall MediaDesk.lnk')) {
    $link=$shell.CreateShortcut((Join-Path $shortcuts $name))
    Assert-True ($link.IconLocation -eq ($icon+',0')) ('Wrong shortcut icon: '+$name)
}
$results['shortcut_icons']=$true
$failed=$false
try {& (Join-Path $PSScriptRoot 'install.ps1') -RuntimeBin $RuntimeBin -VlcDir $VlcDir -InstallRoot $target -SourceRoot $source -NoShortcut} catch {$failed=$true}
Assert-True $failed 'Existing installation was overwritten'
$results['overwrite_refused']=$true
$manifestPath=Join-Path $target 'install-manifest.json'
$originalManifest=Get-Content -LiteralPath $manifestPath -Raw
$badManifest=$originalManifest | ConvertFrom-Json
$badManifest.Files[0].Path='..\outside.txt'
$badManifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
$failed=$false
try {& (Join-Path $target 'uninstall.ps1')} catch {$failed=$true}
Assert-True ($failed -and (Test-Path -LiteralPath (Join-Path $target 'mediadesk\app.py'))) 'Unsafe manifest was not rejected before deletion'
Set-Content -LiteralPath $manifestPath $originalManifest -Encoding UTF8
$results['unsafe_manifest_refused']=$true

$uninstaller=Join-Path $target 'uninstall.ps1'
$process=Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe') -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$uninstaller+'"')) -WorkingDirectory $target -Wait -PassThru
Assert-True ($process.ExitCode -eq 0) 'Uninstall launched from program directory failed'
Assert-True (-not (Test-Path -LiteralPath $target)) 'Normal uninstall left application directory'
foreach ($name in @('MediaDesk.lnk','Uninstall MediaDesk.lnk')) {
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $shortcuts $name))) ('Shortcut not removed: '+$name)
}
Assert-True ((Get-FileHash -LiteralPath $sentinel).Hash -eq $hash) 'User data changed during uninstall'
$results['uninstall_kept_data']=$true
& (Join-Path $PSScriptRoot 'install.ps1') -RuntimeBin $RuntimeBin -VlcDir $VlcDir -PythonPackages @($PythonPackages) -InstallRoot $target -SourceRoot $source -NoShortcut
$modified=Join-Path $target 'doctor.py';Add-Content -LiteralPath $modified '# test modification'
$unknown=Join-Path $target 'unrecognized.txt';Set-Content -LiteralPath $unknown 'keep-me'
$external=Join-Path $testRoot 'external-directory'
$externalChild=Join-Path $external 'empty-child'
New-Item -ItemType Directory -Force -Path $externalChild | Out-Null
New-Item -ItemType Junction -Path (Join-Path $target 'external-link') -Target $external | Out-Null

& (Join-Path $target 'uninstall.ps1')
Assert-True ((Test-Path -LiteralPath $modified) -and (Test-Path -LiteralPath $unknown)) 'Modified or unrecognized files deleted'
Assert-True ((Get-FileHash -LiteralPath $sentinel).Hash -eq $hash) 'User data changed during second uninstall'
$results['modified_files_preserved']=$true
Assert-True (Test-Path -LiteralPath $externalChild) 'Uninstall followed a junction into external files'
$results['junction_not_followed']=$true
$results['test_root']=$testRoot
$results | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $testRoot 'results.json') -Encoding UTF8
$results | ConvertTo-Json
