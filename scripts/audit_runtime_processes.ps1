# SPDX-License-Identifier: Apache-2.0
# Read-only Windows runtime inventory. Never stops a process or prints command arguments.
[CmdletBinding()]
param([switch]$Json, [switch]$Detailed)
$ErrorActionPreference = 'Stop'
$processes = @(Get-CimInstance Win32_Process)
$byId = @{}
foreach ($process in $processes) { $byId[[int]$process.ProcessId] = $process }
$repository = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$desktopRoots = @{}
foreach ($process in $processes) {
    if ($process.Name -eq 'spike-desktop.exe') { $desktopRoots[[int]$process.ProcessId] = $true }
}
function Find-DesktopRoot($Process) {
    $cursor = $Process
    $seen = @{}
    while ($null -ne $cursor -and -not $seen.ContainsKey([int]$cursor.ProcessId)) {
        $id = [int]$cursor.ProcessId
        $seen[$id] = $true
        if ($desktopRoots.ContainsKey($id)) { return $id }
        $parentId = [int]$cursor.ParentProcessId
        if (-not $byId.ContainsKey($parentId)) { break }
        $parent = $byId[$parentId]
        # A reused parent PID is not ownership evidence.
        if ($parent.CreationDate -gt $cursor.CreationDate) { break }
        $cursor = $parent
    }
    return $null
}
$rows = @(foreach ($process in $processes) {
    $desktopId = Find-DesktopRoot $process
    $group = $null
    if ($null -ne $desktopId) { $group = 'SPIKE desktop tree' }
    elseif ($process.Name -eq 'node.exe') {
        if ($process.ExecutablePath -match '[\\/]OpenAI[\\/]Codex[\\/]') { $group = 'Codex tooling' }
        elseif ($process.CommandLine -and $process.CommandLine.IndexOf($repository, [StringComparison]::OrdinalIgnoreCase) -ge 0) { $group = 'SPIKE development tooling' }
        else { $group = 'Other or unclassified Node' }
    }
    if ($group) {
        [pscustomobject]@{
            Group = $group
            ProcessId = [int]$process.ProcessId
            ParentId = [int]$process.ParentProcessId
            DesktopRootId = $desktopId
            Name = $process.Name
            WorkingSetMiB = [Math]::Round([double]$process.WorkingSetSize / 1MB, 1)
            Executable = $process.ExecutablePath
        }
    }
})
$summary = @($rows | Group-Object Group | ForEach-Object {
    [pscustomobject]@{ Group = $_.Name; Count = $_.Count; WorkingSetMiB = [Math]::Round(($_.Group | Measure-Object WorkingSetMiB -Sum).Sum, 1) }
})
$report = [pscustomobject]@{
    CapturedAt = (Get-Date).ToUniversalTime().ToString('o')
    Note = 'Working sets can include shared pages. This is a snapshot, not private-memory usage or proof of a leak. Missing paths remain unclassified.'
    Summary = $summary
    Processes = $rows
}
if ($Json) { $report | ConvertTo-Json -Depth 5 }
else {
    $summary | Format-Table -AutoSize
    if ($Detailed) { $rows | Sort-Object Group, DesktopRootId, ProcessId | Format-Table Group, ProcessId, ParentId, DesktopRootId, Name, WorkingSetMiB -AutoSize }
    Write-Output $report.Note
}
