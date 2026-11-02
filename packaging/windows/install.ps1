param(
    [Parameter(Mandatory=$true)][string]$RuntimeBin,
    [Parameter(Mandatory=$true)][string]$VlcDir,
    [string]$VlcPluginPath='',
    [string]$ManagedRuntimeRoot='',
    [string[]]$ToolDirectories=@(),
    [string[]]$PythonPackages=@(),
    [string]$SourceRoot=(Split-Path (Split-Path $PSScriptRoot -Parent) -Parent),
    [string]$InstallRoot=(Join-Path $env:LOCALAPPDATA 'Programs\MediaDesk'),
    [string]$ShortcutRoot=(Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\MediaDesk'),
    [switch]$NoShortcut
)
. (Join-Path $PSScriptRoot 'common.ps1')
$SourceRoot=(Resolve-Path -LiteralPath $SourceRoot).Path
$RuntimeBin=(Resolve-Path -LiteralPath $RuntimeBin).Path
$VlcDir=(Resolve-Path -LiteralPath $VlcDir).Path
if ($VlcPluginPath) {$VlcPluginPath=(Resolve-Path -LiteralPath $VlcPluginPath).Path}
if ($ManagedRuntimeRoot) {
    $ManagedRuntimeRoot=(Resolve-Path -LiteralPath $ManagedRuntimeRoot).Path
    $owned=Get-Content -LiteralPath (Join-Path $ManagedRuntimeRoot 'install-manifest.json') -Raw | ConvertFrom-Json
    if ($owned.Product -ne 'MediaDesk runtime' -or $owned.Root -ne $ManagedRuntimeRoot) {throw 'Runtime ownership manifest mismatch'}
}
$InstallRoot=[IO.Path]::GetFullPath($InstallRoot).TrimEnd('\')
Assert-MediaDeskInstallRootAvailable $InstallRoot
if (-not (Test-Path -LiteralPath (Join-Path $SourceRoot 'mediadesk\__main__.py'))) {throw 'Missing MediaDesk source package'}
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'mediadesk.ico') -PathType Leaf)) {throw 'Missing MediaDesk shortcut icon'}
foreach ($dir in $PythonPackages) {if (-not (Test-Path -LiteralPath $dir -PathType Container)) {throw "Missing PythonPackages directory: $dir"}}
$ToolDirectories=@($ToolDirectories | ForEach-Object {(Resolve-Path -LiteralPath $_).Path})
if (-not $ManagedRuntimeRoot) {
foreach ($name in @('ffmpeg.exe','ffprobe.exe','yt-dlp.exe','node.exe')) {
    $command=Get-Command $name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command) {$ToolDirectories+=Split-Path $command.Source -Parent}
}
}
$ToolDirectories=@($ToolDirectories | Select-Object -Unique)
$env:PATH=(@($ToolDirectories)+@($env:PATH)) -join ';'
$yt=Get-Command 'yt-dlp.exe' -CommandType Application -ErrorAction Stop | Select-Object -First 1
$config=[PSCustomObject]@{RuntimeBin=$RuntimeBin;VlcDir=$VlcDir;VlcPluginPath=$VlcPluginPath;ToolDirectories=@($ToolDirectories);PythonPackages=@($PythonPackages);YtDlp=$yt.Source}
Set-MediaDeskEnvironment $config $SourceRoot
$python=Join-Path $RuntimeBin 'python.exe'
# Fail before writing installation files when any required external dependency is missing.
& $python -B (Join-Path $PSScriptRoot 'doctor.py')
if ($LASTEXITCODE -ne 0) {throw 'Runtime preflight failed; no application files installed. Complete the external dependencies first.'}
if (-not (Test-Path -LiteralPath (Join-Path $RuntimeBin 'pythonw.exe'))) {throw 'Missing pythonw.exe'}
$shortcutPaths=@()
if (-not $NoShortcut) {
    $ShortcutRoot=[IO.Path]::GetFullPath($ShortcutRoot)
    if ((Test-Path -LiteralPath $ShortcutRoot) -and -not (Test-Path -LiteralPath $ShortcutRoot -PathType Container)) {throw 'ShortcutRoot is not a directory'}
    foreach ($name in @('MediaDesk.lnk','Uninstall MediaDesk.lnk')) {
        if (Test-Path -LiteralPath (Join-Path $ShortcutRoot $name)) {throw "Shortcut already exists: $name"}
    }
}
$stage=$InstallRoot+'.staging-'+[guid]::NewGuid().ToString('N')
New-Item -ItemType Directory -Path $stage | Out-Null
try {
    $appTarget=Join-Path $stage 'mediadesk'
    New-Item -ItemType Directory -Path $appTarget | Out-Null
    Get-ChildItem -LiteralPath (Join-Path $SourceRoot 'mediadesk') -File -Recurse | Where-Object {$_.FullName -notmatch '[\\/]__pycache__[\\/]' -and ($_.Extension -eq '.py' -or $_.Extension -eq '.svg')} | ForEach-Object {
        $relative=$_.FullName.Substring((Join-Path $SourceRoot 'mediadesk').Length).TrimStart('\')
        $target=Join-Path $appTarget $relative
        New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $target
    }
    foreach ($name in @('common.ps1','start.ps1','uninstall.ps1','doctor.py','payload-io.cs','mediadesk.ico')) {Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $stage $name)}
    $config | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $stage 'runtime.json') -Encoding UTF8
    $files=@(Get-ChildItem -LiteralPath $stage -File -Recurse | ForEach-Object {[PSCustomObject]@{Path=$_.FullName.Substring($stage.Length+1);SHA256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash}})
    $manifest=[PSCustomObject]@{Product='MediaDesk';Schema=1;Root=$InstallRoot;Files=$files;Shortcuts=@();ManagedRuntimeRoot=$ManagedRuntimeRoot}
    $manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $stage 'install-manifest.json') -Encoding UTF8
    # Recheck immediately before commit; nonrecursive delete refuses any new contents.
    Assert-MediaDeskInstallRootAvailable $InstallRoot
    if (Test-Path -LiteralPath $InstallRoot) {[IO.Directory]::Delete($InstallRoot,$false)}
    [IO.Directory]::Move($stage,$InstallRoot)
    if (-not $NoShortcut) {
        New-Item -ItemType Directory -Path $ShortcutRoot -Force | Out-Null
        $shell=New-Object -ComObject WScript.Shell
        foreach ($entry in @(@('MediaDesk.lnk','start.ps1'),@('Uninstall MediaDesk.lnk','uninstall.ps1'))) {
            $path=Join-Path $ShortcutRoot $entry[0]
            $link=$shell.CreateShortcut($path)
            $link.TargetPath=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
            $link.Arguments='-NoProfile -ExecutionPolicy Bypass -File "'+(Join-Path $InstallRoot $entry[1])+'"'
            $link.WorkingDirectory=$InstallRoot
            $link.IconLocation=(Join-Path $InstallRoot 'mediadesk.ico')+',0'
            $link.Save();$shortcutPaths+=$path
            $manifest.Shortcuts=@($shortcutPaths | ForEach-Object {[PSCustomObject]@{Path=$_;SHA256=(Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash}})
            $manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $InstallRoot 'install-manifest.json') -Encoding UTF8
        }
    }
    Write-Output ('Installed application files: '+$InstallRoot)
    Write-Output 'User data is stored separately and is retained by uninstall.'
} catch {
    Write-Error ('Installation incomplete. Retained application/staging files at '+$InstallRoot+' or '+$stage+'. Close the application and use its uninstaller if present; otherwise rerun setup. '+$_.Exception.Message)
    throw
}
