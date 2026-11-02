param([Parameter(Mandatory=$true)][string]$RuntimeRoot,[switch]$KeepCache)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath($RuntimeRoot).TrimEnd('\')
$ownerPath=Join-Path $root 'runtime-owner.json'
if (Test-Path -LiteralPath $root) {
    if (-not (Test-Path -LiteralPath $ownerPath)) {throw 'RuntimeRoot already exists without a MediaDesk ownership marker; not changing it'}
    $owner=Get-Content -LiteralPath $ownerPath -Raw | ConvertFrom-Json
    if ($owner.Product -ne 'MediaDesk runtime' -or $owner.Root -ne $root) {throw 'Invalid runtime ownership marker'}
} else {
    New-Item -ItemType Directory -Path $root | Out-Null
    [PSCustomObject]@{Product='MediaDesk runtime';Root=$root;State='preparing'} | ConvertTo-Json | Set-Content -LiteralPath $ownerPath -Encoding UTF8
}
$baseUrl='https://github.com/msys2/msys2-installer/releases/download/2026-09-27/msys2-base-x86_64-20260927.sfx.exe'
$expected='ad336cccfda47758b5e15cda993fbba421115cb0b126697daef1ee4dfe37209f'
$archive=Join-Path $root 'msys2-base.sfx.exe'
$msys=Join-Path $root 'msys64'
if (-not (Test-Path -LiteralPath (Join-Path $msys 'usr\bin\bash.exe'))) {
    [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
    $ProgressPreference='SilentlyContinue'
    Write-Output 'Downloading MSYS2 base from the official distribution server...'
    if (-not (Test-Path -LiteralPath $archive) -or (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLower() -ne $expected) {
        Invoke-WebRequest -UseBasicParsing -Uri $baseUrl -OutFile ($archive+'.partial')
        if ((Get-FileHash -LiteralPath ($archive+'.partial') -Algorithm SHA256).Hash.ToLower() -ne $expected) {throw 'MSYS2 base checksum mismatch; partial file retained for inspection'}
        Move-Item -LiteralPath ($archive+'.partial') -Destination $archive -Force
    }
    [PSCustomObject]@{Url=$baseUrl;SHA256=$expected} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $root 'base-source.json') -Encoding UTF8
    & $archive '-y' ('-o'+$root)
    if ($LASTEXITCODE -ne 0) {throw 'MSYS2 base extraction failed'}
}
$bash=Join-Path $msys 'usr\bin\bash.exe'
if (Test-Path -LiteralPath (Join-Path $msys 'var\lib\pacman\db.lck')) {throw 'Runtime package manager is busy or was interrupted. Wait for the other setup; if it ended, inspect the retained log and lock before retrying. The lock was not removed.'}
# Restore the caller environment even when a download/package transaction fails.
$environment=@{}
foreach ($name in @('MSYSTEM','MSYS2_PATH_TYPE','HOME','CHERE_INVOKING')) {$environment[$name]=[Environment]::GetEnvironmentVariable($name,'Process')}
try {
$env:MSYSTEM='UCRT64';$env:MSYS2_PATH_TYPE='minimal';$env:HOME='/home/mediadesk';$env:CHERE_INVOKING='1'
function Invoke-RuntimeCommand([string]$Command) {
    & $bash --login -c $Command
    if ($LASTEXITCODE -ne 0) {throw ('Runtime command failed; rerun setup to resume: '+$Command)}
}
# First login initializes this private root and its package-signing keyring.
Invoke-RuntimeCommand 'true'
Invoke-RuntimeCommand 'pacman -Syu --noconfirm'
Invoke-RuntimeCommand 'pacman -Syu --noconfirm'
$packages=@('python','gtk3','python-gobject','python-requests','python-google-auth-oauthlib','yt-dlp','yt-dlp-ejs','ffmpeg','nodejs') | ForEach-Object {'mingw-w64-ucrt-x86_64-'+$_}
Invoke-RuntimeCommand ('pacman -S --needed --noconfirm '+($packages -join ' '))
Invoke-RuntimeCommand 'pacman -Q > /package-versions.txt; pacman -Qi > /package-metadata.txt'
if (-not $KeepCache) {Invoke-RuntimeCommand 'pacman -Scc --noconfirm'}
$prefix=Join-Path $msys 'ucrt64'
foreach ($name in @('python.exe','pythonw.exe','ffmpeg.exe','ffprobe.exe','yt-dlp.exe','node.exe')) {
    if (-not (Test-Path -LiteralPath (Join-Path $prefix ('bin\'+$name)))) {throw ('Missing managed runtime component: '+$name)}
}

[PSCustomObject]@{Product='MediaDesk runtime';Root=$root;State='ready';Prefix=$prefix;Packages=$packages} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $ownerPath -Encoding UTF8
Write-Output ('Prepared private runtime: '+$root)

} finally {
    foreach ($name in $environment.Keys) {[Environment]::SetEnvironmentVariable($name,$environment[$name],'Process')}
}
