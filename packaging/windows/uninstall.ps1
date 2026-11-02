param([string]$InstallRoot=$PSScriptRoot,[switch]$Runtime,[switch]$KeepRuntime)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath($InstallRoot).TrimEnd('\')
$manifestPath=Join-Path $root 'install-manifest.json'
$manifest=Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$expectedProduct=if ($Runtime) {'MediaDesk runtime'} else {'MediaDesk'}
if ($manifest.Product -ne $expectedProduct -or $manifest.Schema -ne 1 -or $manifest.Root -ne $root) {throw 'Invalid installation manifest; nothing removed'}
if (-not ('MediaDeskPayloadIO' -as [type])) {Add-Type -Path (Join-Path $PSScriptRoot 'payload-io.cs') -ReferencedAssemblies 'System.dll','System.Core.dll','System.IO.Compression.dll','System.IO.Compression.FileSystem.dll'}
$paths=[Collections.Generic.List[object]]::new()
foreach ($entry in $manifest.Files) {
    if ([IO.Path]::IsPathRooted($entry.Path) -or $entry.Path -match '(^|[\\/])\.\.([\\/]|$)' -or $entry.Path.Contains(':')) {throw 'Unsafe manifest path; nothing removed'}
    $path=[IO.Path]::GetFullPath((Join-Path $root $entry.Path))
    if (-not $path.StartsWith($root+'\',[StringComparison]::OrdinalIgnoreCase)) {throw 'Manifest path escaped installation; nothing removed'}
    $paths.Add([PSCustomObject]@{Path=$path;SHA256=$entry.SHA256})
}
$relativePaths=[string[]]@($paths | ForEach-Object {$_.Path.Substring($root.Length+1)})
$hashes=[string[]]@($paths | ForEach-Object {$_.SHA256})
[MediaDeskPayloadIO]::ValidatePaths($root,$relativePaths)
# Refuse uninstall while the existing application holds its lock. Do not terminate it.
$lock=Join-Path $env:LOCALAPPDATA 'MediaDesk\application.lock'
if (Test-Path -LiteralPath $lock) {
    try {$handle=[IO.File]::Open($lock,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None);$handle.Dispose()}
    catch {throw 'Close MediaDesk before uninstalling. No files removed.'}
}
if (-not $Runtime -and -not $KeepRuntime -and $manifest.PSObject.Properties['ManagedRuntimeRoot'] -and $manifest.ManagedRuntimeRoot) {
    & $PSCommandPath -InstallRoot $manifest.ManagedRuntimeRoot -Runtime
}
# Start menu shortcuts launch with this directory as cwd; Windows cannot delete it while held.
$parent=Split-Path $root -Parent
$location=Get-Location
if ($location.Provider.Name -eq 'FileSystem' -and ($location.Path -eq $root -or $location.Path.StartsWith($root+'\',[StringComparison]::OrdinalIgnoreCase))) {Set-Location -LiteralPath $parent}
$cwd=[Environment]::CurrentDirectory
if ($cwd -eq $root -or $cwd.StartsWith($root+'\',[StringComparison]::OrdinalIgnoreCase)) {[Environment]::CurrentDirectory=$parent}
$removeWatch=[Diagnostics.Stopwatch]::StartNew()
$kept=@([MediaDeskPayloadIO]::DeleteOwned($root,$relativePaths,$hashes))
Write-Output ('Owned file removal seconds: '+$removeWatch.Elapsed.TotalSeconds.ToString('F2'))
$shell=$null
foreach ($entry in $manifest.Shortcuts) {
    if (-not (Test-Path -LiteralPath $entry.Path -PathType Leaf)) {continue}
    if ([IO.Path]::GetFileName($entry.Path) -notin @('MediaDesk.lnk','Uninstall MediaDesk.lnk')) {continue}
    if ((Get-FileHash -LiteralPath $entry.Path -Algorithm SHA256).Hash -ne $entry.SHA256) {$kept+=$entry.Path;continue}
    if (-not $shell) {$shell=New-Object -ComObject WScript.Shell}
    $link=$shell.CreateShortcut($entry.Path)
    if ($link.Arguments -notlike ('*"'+$root+'\*.ps1"')) {$kept+=$entry.Path;continue}
    Remove-Item -LiteralPath $entry.Path
}
# Unknown/modified files and all user data are retained; remove only empty program directories.
[MediaDeskPayloadIO]::RemoveEmptyDirectories($root)
$remaining=@(Get-ChildItem -LiteralPath $root -Force | Where-Object {$_.FullName -ne $manifestPath})
if (-not $remaining) {Remove-Item -LiteralPath $manifestPath;Remove-Item -LiteralPath $root}
else {Write-Output 'Retained modified or unrecognized installation files; manifest kept for review.'}
Write-Output ('User data retained: '+(Join-Path $env:LOCALAPPDATA 'MediaDesk'))
foreach ($path in $kept) {Write-Output ('Retained changed file: '+$path)}
