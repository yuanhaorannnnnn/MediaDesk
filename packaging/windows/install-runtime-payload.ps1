param([Parameter(Mandatory=$true)][string]$PayloadRoot,[Parameter(Mandatory=$true)][string]$RuntimeRoot)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$payload=(Resolve-Path -LiteralPath $PayloadRoot).Path.TrimEnd('\')
$root=[IO.Path]::GetFullPath($RuntimeRoot).TrimEnd('\')
$receipt=Join-Path $payload 'runtime-files.json'
$manifest=Get-Content -LiteralPath $receipt -Raw | ConvertFrom-Json
if ($manifest.schema -ne 1 -or -not $manifest.files.Count) {throw 'Invalid runtime payload manifest'}
$payloadHash=(Get-FileHash -LiteralPath $receipt -Algorithm SHA256).Hash
$archivePath=Join-Path $payload 'runtime.zip'
$archiveInfo=$null
if (Test-Path -LiteralPath (Join-Path $payload 'runtime-archive.json')) {
    $archiveInfo=Get-Content -LiteralPath (Join-Path $payload 'runtime-archive.json') -Raw | ConvertFrom-Json
    if ($archiveInfo.schema -ne 1 -or $archiveInfo.archive -ne 'runtime.zip' -or $archiveInfo.sha256 -notmatch '^[a-fA-F0-9]{64}$' -or $archiveInfo.manifest_sha256 -ne $payloadHash) {throw 'Invalid runtime archive receipt'}
}
function Assert-LocalPath([string]$Path,[string]$Boundary) {
    $cursor=$Path
    while ($cursor.Length -ge $Boundary.Length) {
        if (Test-Path -LiteralPath $cursor) {
            if ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {throw ('Refusing reparse point: '+$cursor)}
        }
        if ($cursor -eq $Boundary) {break}
        $cursor=Split-Path $cursor -Parent
    }
}
Assert-LocalPath $payload ([IO.Path]::GetPathRoot($payload).TrimEnd('\'))
if (-not ('MediaDeskPayloadIO' -as [type])) {Add-Type -Path (Join-Path $PSScriptRoot 'payload-io.cs') -ReferencedAssemblies 'System.dll','System.Core.dll','System.IO.Compression.dll','System.IO.Compression.FileSystem.dll'}
$paths=[Collections.Generic.List[object]]::new();$seen=@{}
foreach ($entry in $manifest.files) {
    $relative=([string]$entry.path).Replace('/','\')
    if ([IO.Path]::IsPathRooted($relative) -or $relative -match '(^|[\\/])\.\.([\\/]|$)' -or $relative.Contains(':') -or $entry.sha256 -notmatch '^[a-fA-F0-9]{64}$') {throw 'Unsafe runtime payload entry'}
    if ($relative.ToLower() -in @('runtime-owner.json','install-manifest.json','payload-receipt.json','runtime-files.json')) {throw 'Reserved runtime payload path'}
    $source=[IO.Path]::GetFullPath((Join-Path $payload $relative))
    if (-not $source.StartsWith($payload+'\',[StringComparison]::OrdinalIgnoreCase) -or $seen.ContainsKey($source)) {throw 'Duplicate or escaped payload entry'}
    $seen[$source]=$true
    $size=if ($entry.PSObject.Properties['bytes']) {[long]$entry.bytes} else {-1}
    $paths.Add([PSCustomObject]@{Relative=$relative;Source=$source;SHA256=$entry.sha256;Bytes=$size})
}
$requiredPaths=@('bin\python.exe','bin\pythonw.exe','bin\yt-dlp.exe','vlc\libvlc.dll','tools\ffmpeg\bin\ffmpeg.exe','tools\ffmpeg\bin\ffprobe.exe','tools\node\node.exe')
$requiredSizes=@{}
foreach ($required in $requiredPaths) {
    $entry=$paths | Where-Object {$_.Relative -eq $required}
    if (-not $entry) {throw ('Incomplete runtime payload: '+$required)}
    $requiredSizes[$required]=$entry.Bytes
}
$relativePaths=[string[]]@($paths | ForEach-Object {$_.Relative})
$hashes=[string[]]@($paths | ForEach-Object {$_.SHA256})
$verifyWatch=[Diagnostics.Stopwatch]::StartNew()
if (-not $archiveInfo) {
    [MediaDeskPayloadIO]::Verify($payload,$relativePaths,$hashes)
    Write-Output ('Runtime source verification seconds: '+$verifyWatch.Elapsed.TotalSeconds.ToString('F2'))
} else {
    Assert-LocalPath $archivePath $payload
    if ((Get-Item -LiteralPath $archivePath).Length -ne $archiveInfo.bytes) {throw 'Runtime archive size mismatch'}
    if ((Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash -ne $archiveInfo.sha256) {throw 'Runtime archive checksum mismatch'}
    Write-Output ('Archive source verification seconds: '+$verifyWatch.Elapsed.TotalSeconds.ToString('F2'))
}
Assert-LocalPath $root ([IO.Path]::GetPathRoot($root).TrimEnd('\'))
if (Test-Path -LiteralPath $root) {
    $owner=Get-Content -LiteralPath (Join-Path $root 'runtime-owner.json') -Raw | ConvertFrom-Json
    if ($owner.Product -ne 'MediaDesk runtime' -or $owner.Root -ne $root -or $owner.State -ne 'ready' -or $owner.PayloadSHA256 -ne $payloadHash) {throw 'RuntimeRoot exists with another or incomplete runtime; existing files were not changed'}
    [MediaDeskPayloadIO]::Verify($root,$relativePaths,$hashes)
    Write-Output ('Reusing verified owned runtime: '+$root)
    return
}
# Refuse before extraction when the destination cannot hold the declared payload.
if ($archiveInfo) {
    $requiredBytes=[long](($paths | Measure-Object -Property Bytes -Sum).Sum)+128MB
    $drive=[IO.DriveInfo]::new([IO.Path]::GetPathRoot($root))
    if ($drive.AvailableFreeSpace -lt $requiredBytes) {throw ('Insufficient runtime disk space: need '+$requiredBytes+' bytes including 128 MiB working reserve; available '+$drive.AvailableFreeSpace)}
}
$stage=$root+'.partial'
if ($archiveInfo -and (Test-Path -LiteralPath $stage)) {
    Write-Output ('Retaining previous interrupted staging directory: '+$stage)
    $stage=$root+'.partial-retry-'+[guid]::NewGuid().ToString('N')
}
$ownerPath=Join-Path $stage 'runtime-owner.json'
if (Test-Path -LiteralPath $stage) {
    Assert-LocalPath $stage ([IO.Path]::GetPathRoot($stage).TrimEnd('\'))
    $owner=Get-Content -LiteralPath $ownerPath -Raw | ConvertFrom-Json
    if ($owner.Product -ne 'MediaDesk runtime' -or ($owner.Root -ne $stage -and -not ($owner.Root -eq $root -and $owner.State -eq 'ready')) -or $owner.Target -ne $root -or $owner.PayloadSHA256 -ne $payloadHash) {throw 'Unrecognized runtime staging directory; nothing changed'}
} else {
    New-Item -ItemType Directory -Path $stage | Out-Null
    [PSCustomObject]@{Product='MediaDesk runtime';Root=$stage;Target=$root;State='preparing';PayloadSHA256=$payloadHash} | ConvertTo-Json | Set-Content -LiteralPath $ownerPath -Encoding UTF8
}
# Reject unknown staging files so they can never become uninstall-owned files.
$allowed=@{'runtime-owner.json'=$true;'payload-receipt.json'=$true}
foreach ($entry in $paths) {$allowed[$entry.Relative]=$true;$allowed[$entry.Relative+'.copying']=$true}
foreach ($item in Get-ChildItem -LiteralPath $stage -Force -Recurse) {
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {throw 'Runtime staging contains a reparse point'}
    if (-not $item.PSIsContainer -and -not $allowed.ContainsKey($item.FullName.Substring($stage.Length+1))) {throw ('Unknown staged file retained: '+$item.FullName)}
}
$copyWatch=[Diagnostics.Stopwatch]::StartNew()
if ($archiveInfo) {
    $sizes=[long[]]@($paths | ForEach-Object {$_.Bytes})
    [MediaDeskPayloadIO]::ExtractArchive($archivePath,$stage,$relativePaths,$sizes,$archiveInfo.sha256)
    foreach ($required in $requiredPaths) {
        $target=Join-Path $stage $required
        if ($requiredSizes[$required] -le 0 -or -not [IO.File]::Exists($target) -or ([IO.FileInfo]::new($target)).Length -ne $requiredSizes[$required]) {throw ('Missing or incomplete extracted runtime component: '+$required)}
    }
    Write-Output 'Archive checks and required component checks passed; extracted files were not individually hashed.'
} else {
    $counts=[MediaDeskPayloadIO]::CopyResume($payload,$stage,$relativePaths,$hashes)
    Write-Output ('Runtime copy seconds: '+$copyWatch.Elapsed.TotalSeconds.ToString('F2')+'; copied='+$counts[0]+'; resumed='+$counts[1])
}
Copy-Item -LiteralPath $receipt -Destination (Join-Path $stage 'payload-receipt.json')
# Write the final ownership checkpoint before atomic promotion, so interruption on either side can resume.
[PSCustomObject]@{Product='MediaDesk runtime';Root=$root;Target=$root;State='ready';PayloadSHA256=$payloadHash} | ConvertTo-Json | Set-Content -LiteralPath $ownerPath -Encoding UTF8
[IO.Directory]::Move($stage,$root)
Write-Output ('Installed runtime payload: '+$root)
