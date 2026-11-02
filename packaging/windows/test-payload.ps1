$ErrorActionPreference='Stop'
$test=Join-Path $env:TEMP ('md-payload-test-'+[guid]::NewGuid().ToString('N'))
$payload=Join-Path $test 'payload';New-Item -ItemType Directory -Path $payload -Force | Out-Null
function Assert-True($condition,$message) {if (-not $condition) {throw $message}}
$names=@('bin\python.exe','bin\pythonw.exe','bin\yt-dlp.exe','vlc\libvlc.dll','tools\ffmpeg\bin\ffmpeg.exe','tools\ffmpeg\bin\ffprobe.exe','tools\node\node.exe')
$files=@($names | ForEach-Object {
    $path=Join-Path $payload $_;New-Item -ItemType Directory -Path (Split-Path $path -Parent) -Force | Out-Null
    Set-Content -LiteralPath $path -Value ('synthetic:'+$_) -Encoding ASCII
    [PSCustomObject]@{path=$_;bytes=(Get-Item -LiteralPath $path).Length;sha256=(Get-FileHash -LiteralPath $path).Hash}
})
$receipt=Join-Path $payload 'runtime-files.json'
[PSCustomObject]@{schema=1;files=$files} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $receipt -Encoding UTF8
$root=Join-Path $test 'runtime'
$receiptOriginal=Get-Content -LiteralPath $receipt -Raw
$unsafe=Get-Content -LiteralPath $receipt -Raw | ConvertFrom-Json
$unsafe.files+=@([PSCustomObject]@{path='..\outside.txt';sha256=('0'*64)})
$unsafe | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $receipt -Encoding UTF8
$failed=$false;try {& "$PSScriptRoot\install-runtime-payload.ps1" -PayloadRoot $payload -RuntimeRoot $root} catch {$failed=$true}
Assert-True ($failed -and -not (Test-Path $root)) 'Traversal manifest was accepted'
Set-Content -LiteralPath $receipt -Value $receiptOriginal -NoNewline -Encoding UTF8
$external=Join-Path $test 'outside';New-Item -ItemType Directory -Path $external | Out-Null
Set-Content (Join-Path $external 'external.txt') 'keep-outside'
New-Item -ItemType Junction -Path (Join-Path $payload 'alias') -Target $external | Out-Null
$linked=Get-Content -LiteralPath $receipt -Raw | ConvertFrom-Json
$linked.files+=@([PSCustomObject]@{path='alias\external.txt';sha256=(Get-FileHash (Join-Path $external 'external.txt')).Hash})
$linked | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $receipt -Encoding UTF8
$failed=$false;try {& "$PSScriptRoot\install-runtime-payload.ps1" -PayloadRoot $payload -RuntimeRoot $root} catch {$failed=$true}
Assert-True ($failed -and -not (Test-Path $root) -and (Get-Content (Join-Path $external 'external.txt')) -eq 'keep-outside') 'Source junction was followed'
Set-Content -LiteralPath $receipt -Value $receiptOriginal -NoNewline -Encoding UTF8
# Keep the synthetic junction as unlisted input; the installer never enumerates/copies unlisted source files.
$first=Join-Path $payload $names[0];$original=Get-Content $first -Raw
Add-Content $first 'corrupt'
$failed=$false;try {& "$PSScriptRoot\install-runtime-payload.ps1" -PayloadRoot $payload -RuntimeRoot $root} catch {$failed=$true}
Assert-True ($failed -and -not (Test-Path $root) -and -not (Test-Path ($root+'.partial'))) 'Corrupt payload wrote runtime files'
Set-Content -LiteralPath $first -Value $original -NoNewline -Encoding ASCII
$stage=$root+'.partial';New-Item -ItemType Directory -Path $stage | Out-Null
[PSCustomObject]@{Product='MediaDesk runtime';Root=$stage;Target=$root;State='preparing';PayloadSHA256=(Get-FileHash $receipt).Hash} | ConvertTo-Json | Set-Content (Join-Path $stage 'runtime-owner.json')
$unknown=Join-Path $stage 'unknown.txt';Set-Content $unknown 'keep'
$failed=$false;try {& "$PSScriptRoot\install-runtime-payload.ps1" -PayloadRoot $payload -RuntimeRoot $root} catch {$failed=$true}
Assert-True ($failed -and (Get-Content $unknown) -eq 'keep') 'Unknown staging file was changed'
# Remove only this known synthetic test fixture, then resume a partially copied payload.
Remove-Item $unknown
New-Item -ItemType Directory -Path (Join-Path $stage 'bin') | Out-Null
Copy-Item $first (Join-Path $stage $names[0])
& "$PSScriptRoot\install-runtime-payload.ps1" -PayloadRoot $payload -RuntimeRoot $root
Assert-True ((Test-Path $root) -and -not (Test-Path $stage)) 'Staged runtime was not promoted'
& "$PSScriptRoot\runtime-manifest.ps1" -RuntimeRoot $root -PayloadReceipt (Join-Path $root 'payload-receipt.json')
$installedManifest=Join-Path $root 'install-manifest.json';$manifestHash=(Get-FileHash $installedManifest).Hash
Set-Content (Join-Path $root 'unknown-after-install.txt') 'keep'
& "$PSScriptRoot\install-runtime-payload.ps1" -PayloadRoot $payload -RuntimeRoot $root
Assert-True ((Get-FileHash $installedManifest).Hash -eq $manifestHash) 'Runtime reuse changed ownership inventory'
Set-Content (Join-Path $root $names[0]) 'changed'
$failed=$false;try {& "$PSScriptRoot\install-runtime-payload.ps1" -PayloadRoot $payload -RuntimeRoot $root} catch {$failed=$true}
Assert-True $failed 'Modified installed runtime accepted'
$readOnly=Join-Path $root $names[1]
[IO.File]::SetAttributes($readOnly,([IO.File]::GetAttributes($readOnly) -bor [IO.FileAttributes]::ReadOnly))
& "$PSScriptRoot\uninstall.ps1" -InstallRoot $root -Runtime
Assert-True (-not (Test-Path $readOnly)) 'Unchanged readonly payload file was not removed'
Assert-True ((Get-Content (Join-Path $root $names[0])) -eq 'changed') 'Modified runtime file removed'
Assert-True (Test-Path (Join-Path $root 'unknown-after-install.txt')) 'Unknown runtime file removed'
Write-Output ('PASS: traversal and source-junction refusal, corrupt payload refusal, staging unknown preservation, partial resume, owned reuse, modified runtime refusal and safe uninstall. Evidence: '+$test)
