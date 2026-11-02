$ErrorActionPreference='Stop'
$testRoot=Join-Path $env:TEMP ('md-payload-small-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot | Out-Null
Copy-Item (Join-Path $PSScriptRoot 'payload-io.cs') (Join-Path $testRoot 'payload-io.cs')
Copy-Item (Join-Path $PSScriptRoot 'install-runtime-payload.ps1') (Join-Path $testRoot 'install-runtime-payload.ps1')
Copy-Item (Join-Path $PSScriptRoot 'common.ps1') (Join-Path $testRoot 'common.ps1')
$payload=Join-Path $testRoot 'payload';New-Item -ItemType Directory -Path $payload|Out-Null
$names=@('bin/python.exe','bin/pythonw.exe','bin/yt-dlp.exe','vlc/libvlc.dll','tools/ffmpeg/bin/ffmpeg.exe','tools/ffmpeg/bin/ffprobe.exe','tools/node/node.exe')
$bytes=[Text.Encoding]::UTF8.GetBytes('synthetic payload only');$sha=[Security.Cryptography.SHA256]::Create();$hash=[BitConverter]::ToString($sha.ComputeHash($bytes)).Replace('-','')
foreach($name in $names){$path=Join-Path $payload $name;New-Item -ItemType Directory -Path (Split-Path $path -Parent) -Force|Out-Null;[IO.File]::WriteAllBytes($path,$bytes)}
[pscustomobject]@{schema=1;files=@($names|ForEach-Object{[pscustomobject]@{path=$_;sha256=$hash;bytes=$bytes.Length}})}|ConvertTo-Json -Depth 5|Set-Content (Join-Path $payload 'runtime-files.json') -Encoding UTF8
$source=Get-Content (Join-Path $testRoot 'payload-io.cs') -Raw
$source=$source.Replace('public static class MediaDeskPayloadIO {', 'public static class MediaDeskPayloadIO { public static readonly System.Threading.ManualResetEventSlim DelayedStarted=new System.Threading.ManualResetEventSlim(false); public static volatile bool DelayedCompleted;')
$source=$source.Replace('using(FileStream stream=new FileStream(path,', 'if(path.EndsWith("python.exe")) { DelayedStarted.Set(); System.Threading.Thread.Sleep(800); DelayedCompleted=true; } if(path.EndsWith("ffprobe.exe")) { if(!DelayedStarted.Wait(5000)) throw new IOException("Delayed worker did not start"); throw new IOException("MOCK read failure"); } using(FileStream stream=new FileStream(path,')
Set-Content (Join-Path $testRoot 'payload-io.cs') $source -Encoding UTF8
Copy-Item (Join-Path $PSScriptRoot 'setup.ps1') (Join-Path $testRoot 'setup.ps1')
$marker=Join-Path $testRoot 'INSTALL_WAS_CALLED'
Set-Content (Join-Path $testRoot 'install.ps1') ('[IO.File]::WriteAllText("'+$marker+'","unexpected")')
Set-Content (Join-Path $testRoot 'runtime-manifest.ps1') ('[IO.File]::WriteAllText("'+$marker+'","unexpected")')
$sourceRoot=Join-Path $testRoot 'source'
New-Item -ItemType Directory -Path (Join-Path $sourceRoot 'mediadesk')|Out-Null
Set-Content (Join-Path $sourceRoot 'mediadesk\__main__.py') '# synthetic source'
$target=Join-Path $testRoot 'failed-runtime';$app=Join-Path $testRoot 'app';$shortcuts=Join-Path $testRoot 'shortcuts'
$messages=[Collections.Generic.List[string]]::new();$failed=$false
$previousTemp=$env:TEMP;$env:TEMP=$testRoot
try {
    & (Join-Path $testRoot 'setup.ps1') -SourceRoot $sourceRoot -PayloadRoot $payload -RuntimeRoot $target -InstallRoot $app -ShortcutRoot $shortcuts | ForEach-Object {$messages.Add([string]$_)}
} catch {$failed=$_.Exception.ToString().Contains('MOCK read failure')} finally {$env:TEMP=$previousTemp}
if(-not $failed){throw 'Mock read failure did not reach setup'}
if(-not [MediaDeskPayloadIO]::DelayedCompleted){throw 'Parallel verification returned before delayed worker completed'}
if((Test-Path $target) -or (Test-Path $app) -or (Test-Path $shortcuts) -or (Test-Path $marker)){throw 'Failure promoted runtime or reached application/shortcut installation'}
if(Test-Path ($target+'.partial')){throw 'Source verification failure created a runtime stage'}
if($messages -match 'setup completed|Verified runtime files: 7/7'){throw 'Failure reported successful completion'}
$messages | Write-Output
Write-Output ('PASS: expanded-source parallel read failure joined workers; no stage/promotion/application/shortcut/success; evidence '+$testRoot)
