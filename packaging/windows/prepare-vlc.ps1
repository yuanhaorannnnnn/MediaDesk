param([Parameter(Mandatory=$true)][string]$RuntimeRoot)
$ErrorActionPreference='Stop'
$root=(Resolve-Path -LiteralPath $RuntimeRoot).Path
$owner=Get-Content -LiteralPath (Join-Path $root 'runtime-owner.json') -Raw | ConvertFrom-Json
if ($owner.Product -ne 'MediaDesk runtime' -or $owner.Root -ne $root -or $owner.State -ne 'ready') {throw 'Prepare the owned runtime before VLC'}
$target=Join-Path $root 'vlc-3.0.24'
$archive=Join-Path $root 'vlc-3.0.24-win64.7z'
$url='https://download.videolan.org/pub/videolan/vlc/3.0.24/win64/vlc-3.0.24-win64.7z'
$expected='1ed59c09152e78aff84663fa76efab26057716576db74332858810e5ef54ae1f'
$complete=Join-Path $target '.mediadesk-complete'
if (-not (Test-Path $complete)) {
    [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
    $ProgressPreference='SilentlyContinue'
    if (-not (Test-Path $archive) -or (Get-FileHash $archive -Algorithm SHA256).Hash.ToLower() -ne $expected) {
        Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile ($archive+'.partial') -TimeoutSec 120
        if ((Get-FileHash ($archive+'.partial') -Algorithm SHA256).Hash.ToLower() -ne $expected) {throw 'VLC checksum mismatch; download retained'}
        Move-Item ($archive+'.partial') $archive -Force
    }
    & (Join-Path $root 'msys64\usr\bin\bsdtar.exe') -xf $archive -C $root
    if ($LASTEXITCODE -ne 0) {throw 'VLC extraction failed; rerun setup to resume'}
}
foreach ($name in @('libvlc.dll','libvlccore.dll','plugins','COPYING.txt')) {
    if (-not (Test-Path (Join-Path $target $name))) {throw ('Incomplete VLC runtime: '+$name)}
}
Set-Content -LiteralPath $complete -Value $expected -Encoding ASCII
[PSCustomObject]@{Url=$url;SHA256=$expected;ChecksumSource=$url+'.sha256'} | ConvertTo-Json | Set-Content (Join-Path $root 'vlc-source.json') -Encoding UTF8
if (Test-Path $archive) {Remove-Item $archive}
Write-Output $target
