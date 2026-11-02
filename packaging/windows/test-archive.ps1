$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$test=Join-Path $env:TEMP ('md-archive-test-'+[guid]::NewGuid().ToString('N'))
$payload=Join-Path $test 'payload';$flat=Join-Path $test 'flat'
New-Item -ItemType Directory -Path $payload,$flat -Force | Out-Null
function Assert-True($condition,$message) {if (-not $condition) {throw $message}}
$names=@('bin\python.exe','bin\pythonw.exe','bin\yt-dlp.exe','vlc\libvlc.dll','tools\ffmpeg\bin\ffmpeg.exe','tools\ffmpeg\bin\ffprobe.exe','tools\node\node.exe')
$files=@($names | ForEach-Object {
 $path=Join-Path $flat $_;New-Item -ItemType Directory -Path (Split-Path $path -Parent) -Force | Out-Null
 Set-Content -LiteralPath $path -Value ('synthetic:'+$_) -Encoding ASCII
 [PSCustomObject]@{path=$_;bytes=(Get-Item $path).Length;sha256=(Get-FileHash $path).Hash}
})
[PSCustomObject]@{schema=1;files=$files} | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $payload 'runtime-files.json')
$archive=Join-Path $payload 'runtime.zip'
function New-Archive([string]$Extra='',[switch]$Link) {
 if (Test-Path $archive) {Remove-Item -LiteralPath $archive}
 $zip=[IO.Compression.ZipFile]::Open($archive,[IO.Compression.ZipArchiveMode]::Create)
 try {
  foreach ($name in $names) {
   $entry=[IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip,(Join-Path $flat $name),$name.Replace('\','/'))
   if ($Link -and $name -eq $names[0]) {$entry.ExternalAttributes=[int]0xA1FF0000}
  }
  if ($Extra) {
   $entry=$zip.CreateEntry($Extra);$writer=[IO.StreamWriter]::new($entry.Open());$writer.Write('do-not-write');$writer.Dispose()
  }
 } finally {$zip.Dispose()}
 [PSCustomObject]@{schema=1;archive='runtime.zip';sha256=(Get-FileHash $archive).Hash;manifest_sha256=(Get-FileHash (Join-Path $payload 'runtime-files.json')).Hash;bytes=(Get-Item $archive).Length} | ConvertTo-Json | Set-Content (Join-Path $payload 'runtime-archive.json')
}
New-Archive
$bytes=[IO.File]::ReadAllBytes($archive);$bytes[10]=$bytes[10] -bxor 1;[IO.File]::WriteAllBytes($archive,$bytes)
$root=Join-Path $test 'bad-hash';$failed=$false
try {& "$PSScriptRoot\install-runtime-payload.ps1" -PayloadRoot $payload -RuntimeRoot $root} catch {$failed=$true}
Assert-True ($failed -and -not (Test-Path ($root+'.partial'))) 'Corrupt archive was not refused before staging'
New-Archive -Extra '../outside.txt'
$outside=Join-Path $test 'outside.txt';Set-Content $outside 'keep'
$root=Join-Path $test 'traversal';$failed=$false
try {& "$PSScriptRoot\install-runtime-payload.ps1" -PayloadRoot $payload -RuntimeRoot $root} catch {$failed=$true}
Assert-True ($failed -and -not (Test-Path $root) -and (Get-Content $outside) -eq 'keep') 'Archive traversal was accepted'
New-Archive -Extra 'bin/python.exe'
$root=Join-Path $test 'duplicate';$failed=$false
try {& "$PSScriptRoot\install-runtime-payload.ps1" -PayloadRoot $payload -RuntimeRoot $root} catch {$failed=$true}
Assert-True ($failed -and -not (Test-Path $root)) 'Duplicate archive entry was accepted'
New-Archive -Extra 'unexpected.txt'
$root=Join-Path $test 'unknown';$failed=$false
try {& "$PSScriptRoot\install-runtime-payload.ps1" -PayloadRoot $payload -RuntimeRoot $root} catch {$failed=$true}
Assert-True ($failed -and -not (Test-Path $root)) 'Unknown archive entry was accepted'
New-Archive -Link
$root=Join-Path $test 'link';$failed=$false
try {& "$PSScriptRoot\install-runtime-payload.ps1" -PayloadRoot $payload -RuntimeRoot $root} catch {$failed=$true}
Assert-True ($failed -and -not (Test-Path $root)) 'Archive symlink was accepted'
New-Archive
$root=Join-Path $test 'valid'
& "$PSScriptRoot\install-runtime-payload.ps1" -PayloadRoot $payload -RuntimeRoot $root
& "$PSScriptRoot\runtime-manifest.ps1" -RuntimeRoot $root -PayloadReceipt (Join-Path $root 'payload-receipt.json')
foreach ($file in $files) {Assert-True ((Get-FileHash (Join-Path $root $file.path)).Hash -eq $file.sha256) 'Extracted bytes differ'}
& "$PSScriptRoot\uninstall.ps1" -InstallRoot $root -Runtime
Assert-True (-not (Test-Path $root)) 'Clean archive payload uninstall left owned files'
Write-Output ('PASS: corrupt SHA before staging, traversal/link rejection, native extraction + test-side byte comparison, clean uninstall. Evidence: '+$test)
