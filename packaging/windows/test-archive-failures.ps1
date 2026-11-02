$ErrorActionPreference='Stop'
$testRoot=Join-Path $env:TEMP ('md-archive-failures-'+[guid]::NewGuid().ToString('N'))
$payload=Join-Path $testRoot 'payload'
New-Item -ItemType Directory -Path $payload -Force|Out-Null
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$names=@('bin/python.exe','bin/pythonw.exe','bin/yt-dlp.exe','vlc/libvlc.dll','tools/ffmpeg/bin/ffmpeg.exe','tools/ffmpeg/bin/ffprobe.exe','tools/node/node.exe','share/optional.dat')
$bytes=[Text.Encoding]::UTF8.GetBytes('synthetic payload only')
$sha=[Security.Cryptography.SHA256]::Create();$hash=[BitConverter]::ToString($sha.ComputeHash($bytes)).Replace('-','')
[pscustomobject]@{schema=1;files=@($names|ForEach-Object{[pscustomobject]@{path=$_;sha256=$hash;bytes=$bytes.Length}})}|ConvertTo-Json -Depth 5|Set-Content (Join-Path $payload 'runtime-files.json') -Encoding UTF8
$archive=Join-Path $payload 'runtime.zip'
function New-Archive([switch]$BadCompression) {
 if(Test-Path $archive){Remove-Item -LiteralPath $archive}
 $zip=[IO.Compression.ZipFile]::Open($archive,[IO.Compression.ZipArchiveMode]::Create)
 foreach($name in $names){$entry=$zip.CreateEntry($name,[IO.Compression.CompressionLevel]::Optimal);$stream=$entry.Open();$stream.Write($bytes,0,$bytes.Length);$stream.Dispose()};$zip.Dispose()
 if($BadCompression){
  $raw=[IO.File]::ReadAllBytes($archive)
  if([BitConverter]::ToUInt16($raw,8) -ne 8){throw 'Fixture is not a deflate entry'}
  $offset=30+[BitConverter]::ToUInt16($raw,26)+[BitConverter]::ToUInt16($raw,28)
  $raw[$offset]=($raw[$offset] -band 248) -bor 7 # Reserved deflate block type, with valid ZIP directory and updated archive SHA.
  [IO.File]::WriteAllBytes($archive,$raw)
 }
 [pscustomobject]@{schema=1;archive='runtime.zip';bytes=(Get-Item $archive).Length;sha256=(Get-FileHash $archive).Hash;manifest_sha256=(Get-FileHash (Join-Path $payload 'runtime-files.json')).Hash}|ConvertTo-Json|Set-Content (Join-Path $payload 'runtime-archive.json') -Encoding UTF8
}
function New-Case([string]$Name,[string]$AfterExtraction='') {
 $case=Join-Path $testRoot $Name;New-Item -ItemType Directory -Path $case|Out-Null
 $type='MediaDeskPayloadIO_'+$Name
 foreach($file in @('common.ps1','setup.ps1','runtime-manifest.ps1')){Copy-Item (Join-Path $PSScriptRoot $file) (Join-Path $case $file)}
 foreach($file in @('install-runtime-payload.ps1','uninstall.ps1')){(Get-Content (Join-Path $PSScriptRoot $file) -Raw).Replace('MediaDeskPayloadIO',$type)|Set-Content (Join-Path $case $file) -Encoding UTF8}
 $source=(Get-Content (Join-Path $PSScriptRoot 'payload-io.cs') -Raw).Replace('MediaDeskPayloadIO',$type)
 if($AfterExtraction){$source=$source.Replace('timer.Restart();ValidatePaths(root,paths);',$AfterExtraction+' timer.Restart();ValidatePaths(root,paths);')}
 $source|Set-Content (Join-Path $case 'payload-io.cs') -Encoding UTF8
 New-Item -ItemType Directory -Path (Join-Path $case 'mediadesk')|Out-Null
 Set-Content (Join-Path $case 'mediadesk\__main__.py') '# synthetic source'
 Set-Content (Join-Path $case 'install.ps1') ('[IO.File]::WriteAllText("'+(Join-Path $case 'APP_INSTALL_CALLED')+'","called")')
 return $case
}
function Invoke-Case([string]$Case,[string]$ExpectedError) {
 $target=Join-Path $Case 'runtime';$errorText='';$messages=[Collections.Generic.List[string]]::new()
 try{& (Join-Path $Case 'setup.ps1') -SourceRoot $Case -PayloadRoot $payload -RuntimeRoot $target -InstallRoot (Join-Path $Case 'app') -NoShortcut|ForEach-Object{$messages.Add([string]$_)}}catch{$errorText=$_.Exception.ToString()}
 if($ExpectedError){
  if(-not $errorText.Contains($ExpectedError)){throw ('Expected '+$ExpectedError+'; got '+$errorText)}
  if((Test-Path $target) -or (Test-Path (Join-Path $Case 'APP_INSTALL_CALLED'))){throw 'Failed extraction was promoted or reached app install'}
  $owner=Get-Content (Join-Path ($target+'.partial') 'runtime-owner.json') -Raw|ConvertFrom-Json
  if($owner.State -ne 'preparing' -or ($messages -match 'setup completed')){throw 'Failed extraction reported ready/success'}
 }elseif($errorText -or -not (Test-Path (Join-Path $Case 'APP_INSTALL_CALLED'))){throw ('Expected successful archive checks: '+$errorText)}
}
New-Archive -BadCompression
Invoke-Case (New-Case 'baddeflate') 'Native archive extraction failed'
New-Archive
Invoke-Case (New-Case 'missing' 'File.Delete(Path.Combine(root,"bin","python.exe"));') 'Missing or incomplete extracted runtime component'
Invoke-Case (New-Case 'truncated' 'File.WriteAllBytes(Path.Combine(root,"bin","python.exe"),new byte[1]);') 'Missing or incomplete extracted runtime component'
$case=New-Case 'unchecked' ('File.WriteAllBytes(Path.Combine(root,"share","optional.dat"),new byte['+$bytes.Length+']);')
Invoke-Case $case ''
$target=Join-Path $case 'runtime';$changed=Join-Path $target 'share\optional.dat'
if((Get-FileHash $changed).Hash -eq $hash){throw 'Content-change boundary fixture was not changed'}
$manifest=Get-Content (Join-Path $target 'install-manifest.json') -Raw|ConvertFrom-Json
if(($manifest.Files|Where-Object{$_.Path -eq 'share\optional.dat'}).SHA256 -ne $hash){throw 'Uninstall receipt adopted unchecked current bytes'}
& (Join-Path $case 'uninstall.ps1') -InstallRoot $target -Runtime
if(-not (Test-Path $changed)){throw 'Uninstall removed a changed file'}
Write-Output ('PASS: native decompression failure, missing/truncated required component refuse promotion; unchecked content is not claimed verified and uninstall retains it. Evidence: '+$testRoot)
