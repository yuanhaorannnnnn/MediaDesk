param([Parameter(Mandatory=$true)][string]$RuntimeRoot,[string]$PayloadReceipt='')
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$root=(Resolve-Path -LiteralPath $RuntimeRoot).Path.TrimEnd('\')
$owner=Get-Content -LiteralPath (Join-Path $root 'runtime-owner.json') -Raw | ConvertFrom-Json
if ($owner.Product -ne 'MediaDesk runtime' -or $owner.Root -ne $root -or $owner.State -ne 'ready') {throw 'Runtime is not ready or not owned by MediaDesk'}
$manifestPath=Join-Path $root 'install-manifest.json'
$files=[Collections.Generic.List[object]]::new()
if ($PayloadReceipt) {
    # Preserve the payload receipt hashes for uninstall; never adopt current file contents.
    $payload=Get-Content -LiteralPath $PayloadReceipt -Raw | ConvertFrom-Json
    if ($payload.schema -ne 1) {throw 'Invalid payload receipt'}
    foreach ($entry in $payload.files) {
        $relative=([string]$entry.path).Replace('/','\')
        if ([IO.Path]::IsPathRooted($relative) -or $relative -match '(^|[\\/])\.\.([\\/]|$)' -or $relative.Contains(':') -or $entry.sha256 -notmatch '^[a-fA-F0-9]{64}$') {throw 'Unsafe payload receipt'}
        $files.Add([PSCustomObject]@{Path=$relative;SHA256=$entry.sha256})
    }
    foreach ($name in @('runtime-owner.json','payload-receipt.json')) {
        $files.Add([PSCustomObject]@{Path=$name;SHA256=(Get-FileHash -LiteralPath (Join-Path $root $name) -Algorithm SHA256).Hash})
    }
    [PSCustomObject]@{Product='MediaDesk runtime';Schema=1;Root=$root;Files=$files.ToArray();Shortcuts=@()} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
    Write-Output ('Runtime ownership inventory from payload receipt: '+$files.Count+' files')
    return
}
$pending=[Collections.Generic.Queue[string]]::new();$pending.Enqueue($root)
while ($pending.Count) {
    $current=$pending.Dequeue()
    foreach ($item in Get-ChildItem -LiteralPath $current -Force) {
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {continue}
        if ($item.PSIsContainer) {$pending.Enqueue($item.FullName);continue}
        if ($item.FullName -eq $manifestPath) {continue}
        try {$hash=(Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256 -ErrorAction Stop).Hash}
        catch {Write-Output ('Untracked runtime file retained: '+$item.FullName);continue}
        $files.Add([PSCustomObject]@{Path=$item.FullName.Substring($root.Length+1);SHA256=$hash})
    }
}
[PSCustomObject]@{Product='MediaDesk runtime';Schema=1;Root=$root;Files=$files.ToArray();Shortcuts=@()} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
Write-Output ('Runtime ownership inventory: '+$files.Count+' files')
