Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
function Set-MediaDeskEnvironment($Config,[string]$AppRoot) {
    $env:PATH=(@($Config.RuntimeBin)+@($Config.ToolDirectories)+@($Config.VlcDir)+@($env:PATH)) -join ';'
    $prefix=Split-Path $Config.RuntimeBin -Parent
    $env:GDK_BACKEND='win32'
    $env:GI_TYPELIB_PATH=Join-Path $prefix 'lib\girepository-1.0'
    $env:XDG_DATA_DIRS=Join-Path $prefix 'share'
    $env:OPENSSL_MODULES=Join-Path $prefix 'lib\ossl-modules'
    $env:MEDIADESK_VLC_DIR=$Config.VlcDir
    if ($Config.PSObject.Properties['VlcPluginPath'] -and $Config.VlcPluginPath) {$env:VLC_PLUGIN_PATH=$Config.VlcPluginPath}
    else {$env:VLC_PLUGIN_PATH=Join-Path $Config.VlcDir 'plugins'}
    $env:MEDIADESK_YTDLP=$Config.YtDlp
    $env:MEDIADESK_YOUTUBE_PYTHON=Join-Path $Config.RuntimeBin 'python.exe'
    $env:PYTHONPATH=(@($AppRoot)+@($Config.PythonPackages)) -join ';'
    $env:PYTHONIOENCODING='utf-8'
    $env:PYTHONDONTWRITEBYTECODE='1'
}

function Assert-MediaDeskInstallRootAvailable([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {return}
    $item=Get-Item -LiteralPath $Path -Force
    if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {throw 'InstallRoot must be an ordinary empty directory or absent; existing path was not changed.'}
    if (@(Get-ChildItem -LiteralPath $Path -Force).Count) {throw 'InstallRoot contains files; uninstall previous program files first. Existing files and user data were not changed.'}
}
