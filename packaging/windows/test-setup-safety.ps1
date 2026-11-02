# Exercises installer trust boundaries without downloading a runtime or using user data.
$ErrorActionPreference='Stop'
$testRoot=Join-Path $env:TEMP ('md-setup-safety-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot | Out-Null
function Assert-True($value,$message) {if (-not $value) {throw $message}}
. (Join-Path $PSScriptRoot 'common.ps1')
$empty=Join-Path $testRoot 'empty-app'
New-Item -ItemType Directory -Path $empty | Out-Null
Assert-MediaDeskInstallRootAvailable $empty
Assert-True (Test-Path -LiteralPath $empty) 'Availability check removed empty directory'
$hidden=Join-Path $empty 'hidden.txt'
Set-Content -LiteralPath $hidden 'keep'
[IO.File]::SetAttributes($hidden,[IO.FileAttributes]::Hidden)
$failed=$false
try {Assert-MediaDeskInstallRootAvailable $empty} catch {$failed=$true}
Assert-True ($failed -and (Get-Content -LiteralPath $hidden) -eq 'keep') 'Hidden file was ignored or removed'
$plain=Join-Path $testRoot 'plain-file';Set-Content -LiteralPath $plain 'keep'
$failed=$false
try {Assert-MediaDeskInstallRootAvailable $plain} catch {$failed=$true}
Assert-True ($failed -and (Get-Content -LiteralPath $plain) -eq 'keep') 'Plain file was accepted or removed'
$external=Join-Path $testRoot 'external-empty';New-Item -ItemType Directory -Path $external | Out-Null
$junction=Join-Path $testRoot 'junction-app'
New-Item -ItemType Junction -Path $junction -Target $external | Out-Null
$failed=$false
try {Assert-MediaDeskInstallRootAvailable $junction} catch {$failed=$true}
Assert-True ($failed -and (Test-Path -LiteralPath $junction) -and (Test-Path -LiteralPath $external)) 'Empty reparse point was accepted or removed'
$runtime=Join-Path $testRoot 'unowned'
New-Item -ItemType Directory -Path $runtime | Out-Null
$sentinel=Join-Path $runtime 'keep.txt';Set-Content $sentinel 'keep'
$failed=$false
try {& "$PSScriptRoot\prepare-runtime.ps1" -RuntimeRoot $runtime} catch {$failed=$true}
Assert-True ($failed -and (Get-Content $sentinel) -eq 'keep') 'Unowned runtime was changed'
$failed=$false
try {& "$PSScriptRoot\setup.ps1" -SourceRoot (Join-Path $testRoot 'missing-source') -RuntimeRoot (Join-Path $testRoot 'not-created') -InstallRoot (Join-Path $testRoot 'app')} catch {$failed=$true}
Assert-True ($failed -and -not (Test-Path (Join-Path $testRoot 'not-created'))) 'Missing source started runtime preparation'
$owned=Join-Path $testRoot 'owned'
New-Item -ItemType Directory -Path $owned | Out-Null
$known=Join-Path $owned 'known.txt';Set-Content $known 'known'
$changed=Join-Path $owned 'changed.txt';Set-Content $changed 'before'
$files=@($known,$changed | ForEach-Object {[PSCustomObject]@{Path=(Split-Path $_ -Leaf);SHA256=(Get-FileHash $_).Hash}})
[PSCustomObject]@{Product='MediaDesk runtime';Schema=1;Root=$owned;Files=$files;Shortcuts=@()} | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $owned 'install-manifest.json')
Set-Content $changed 'after'
$unknown=Join-Path $owned 'unknown.txt';Set-Content $unknown 'keep'
& "$PSScriptRoot\uninstall.ps1" -InstallRoot $owned -Runtime
Assert-True (-not (Test-Path $known)) 'Owned unchanged file retained'
Assert-True ((Get-Content $changed) -eq 'after' -and (Test-Path $unknown)) 'Changed or unknown file removed'
Write-Output ('PASS: unowned runtime refused, missing source refused before download, runtime uninstall preserves changed/unknown files. Evidence: '+$testRoot)
