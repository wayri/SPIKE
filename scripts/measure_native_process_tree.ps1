# SPDX-License-Identifier: Apache-2.0
[CmdletBinding(DefaultParameterSetName = 'Pid')]
param(
  [Parameter(Mandatory, ParameterSetName = 'Pid')][int]$RootPid,
  [Parameter(Mandatory, ParameterSetName = 'Launch')][string]$Executable,
  [Parameter(ParameterSetName = 'Launch')][string[]]$ProcessArgument = @(),
  [Parameter(Mandatory)][string]$OutputPath,
  [ValidateRange(1, 86400)][int]$DurationSeconds = 180,
  [ValidateRange(100, 60000)][int]$IntervalMilliseconds = 1000,
  [ValidateRange(2, 10000)][int]$SteadySamples = 15
)

$ErrorActionPreference = 'Stop'
$launched = $null
if ($PSCmdlet.ParameterSetName -eq 'Launch') {
  $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
  $startInfo.FileName = $Executable
  $startInfo.UseShellExecute = $false
  foreach ($argument in $ProcessArgument) { [void]$startInfo.ArgumentList.Add($argument) }
  $launched = [System.Diagnostics.Process]::Start($startInfo)
  $RootPid = $launched.Id
}

$output = [System.IO.Path]::GetFullPath($OutputPath)
$directory = [System.IO.Path]::GetDirectoryName($output)
[System.IO.Directory]::CreateDirectory($directory) | Out-Null
$samples = [System.Collections.Generic.List[object]]::new()
$started = [DateTimeOffset]::UtcNow
$deadline = $started.AddSeconds($DurationSeconds)

while ([DateTimeOffset]::UtcNow -lt $deadline) {
  $processRows = @(Get-CimInstance Win32_Process -Property ProcessId,ParentProcessId,Name -ErrorAction Stop)
  $children = @{}
  foreach ($row in $processRows) {
    $parent = [int]$row.ParentProcessId
    if (-not $children.ContainsKey($parent)) { $children[$parent] = [System.Collections.Generic.List[int]]::new() }
    $children[$parent].Add([int]$row.ProcessId)
  }
  $ids = [System.Collections.Generic.HashSet[int]]::new()
  $queue = [System.Collections.Generic.Queue[int]]::new()
  $queue.Enqueue($RootPid)
  while ($queue.Count) {
    $id = $queue.Dequeue()
    if (-not $ids.Add($id)) { continue }
    if ($children.ContainsKey($id)) { foreach ($child in $children[$id]) { $queue.Enqueue($child) } }
  }
  $working = [int64]0
  $private = [int64]0
  $alive = [System.Collections.Generic.List[object]]::new()
  foreach ($id in $ids) {
    try {
      $process = Get-Process -Id $id -ErrorAction Stop
      $working += [int64]$process.WorkingSet64
      $private += [int64]$process.PrivateMemorySize64
      $alive.Add([ordered]@{ pid = $id; name = $process.ProcessName; working_set_bytes = [int64]$process.WorkingSet64; private_bytes = [int64]$process.PrivateMemorySize64 })
    } catch { }
  }
  if ($alive.Count -eq 0) { break }
  $gpuShared = [int64]0
  $gpuDedicated = [int64]0
  $gpuStatus = 'available'
  try {
    $gpuRows = @(Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUProcessMemory -Property Name,SharedUsage,DedicatedUsage -ErrorAction Stop)
    foreach ($gpu in $gpuRows) {
      if ([string]$gpu.Name -match '^pid_(\d+)_') {
        $gpuPid = [int]$Matches[1]
        if ($ids.Contains($gpuPid)) {
          $gpuShared += [int64]$gpu.SharedUsage
          $gpuDedicated += [int64]$gpu.DedicatedUsage
        }
      }
    }
  } catch { $gpuStatus = "unavailable:$($_.Exception.GetType().Name)" }
  $freePhysical = $null
  try {
    $os = Get-CimInstance Win32_OperatingSystem -Property FreePhysicalMemory -ErrorAction Stop
    $freePhysical = [int64]$os.FreePhysicalMemory * 1024
  } catch { }
  $now = [DateTimeOffset]::UtcNow
  $samples.Add([ordered]@{
    elapsed_seconds = [Math]::Round(($now - $started).TotalSeconds, 3)
    timestamp_utc = $now.ToString('o')
    process_count = $alive.Count
    working_set_bytes = $working
    private_bytes = $private
    gpu_shared_bytes = $gpuShared
    gpu_dedicated_bytes = $gpuDedicated
    gpu_telemetry = $gpuStatus
    os_free_physical_bytes = $freePhysical
    processes = @($alive)
  })
  Start-Sleep -Milliseconds $IntervalMilliseconds
}

if ($samples.Count -eq 0) { throw "The root process $RootPid and its descendants were not observable." }
$tailCount = [Math]::Min($SteadySamples, $samples.Count)
$tail = @($samples | Select-Object -Last $tailCount)
$firstTail = $tail[0]
$lastTail = $tail[-1]
$tailSeconds = [Math]::Max(0.001, $lastTail.elapsed_seconds - $firstTail.elapsed_seconds)
$workingValues = @($samples | ForEach-Object { [int64]$_['working_set_bytes'] })
$privateValues = @($samples | ForEach-Object { [int64]$_['private_bytes'] })
$processValues = @($samples | ForEach-Object { [int]$_['process_count'] })
$tailWorkingValues = @($tail | ForEach-Object { [int64]$_['working_set_bytes'] })
$tailPrivateValues = @($tail | ForEach-Object { [int64]$_['private_bytes'] })
$gpuSharedValues = @($samples | ForEach-Object { [int64]$_['gpu_shared_bytes'] })
$gpuDedicatedValues = @($samples | ForEach-Object { [int64]$_['gpu_dedicated_bytes'] })
$result = [ordered]@{
  contract = 'spike/native-process-memory/v1'
  root_pid = $RootPid
  launched_by_sampler = $null -ne $launched
  started_at_utc = $started.ToString('o')
  interval_milliseconds = $IntervalMilliseconds
  requested_duration_seconds = $DurationSeconds
  sample_count = $samples.Count
  peak = [ordered]@{
    working_set_bytes = [int64](($workingValues | Measure-Object -Maximum).Maximum)
    private_bytes = [int64](($privateValues | Measure-Object -Maximum).Maximum)
    gpu_shared_bytes = [int64](($gpuSharedValues | Measure-Object -Maximum).Maximum)
    gpu_dedicated_bytes = [int64](($gpuDedicatedValues | Measure-Object -Maximum).Maximum)
    process_count = [int](($processValues | Measure-Object -Maximum).Maximum)
  }
  steady = [ordered]@{
    sample_count = $tailCount
    working_set_mean_bytes = [int64](($tailWorkingValues | Measure-Object -Average).Average)
    private_mean_bytes = [int64](($tailPrivateValues | Measure-Object -Average).Average)
    working_set_delta_bytes = [int64]($lastTail.working_set_bytes - $firstTail.working_set_bytes)
    private_delta_bytes = [int64]($lastTail.private_bytes - $firstTail.private_bytes)
    working_set_slope_bytes_per_second = [Math]::Round(($lastTail.working_set_bytes - $firstTail.working_set_bytes) / $tailSeconds, 3)
    private_slope_bytes_per_second = [Math]::Round(($lastTail.private_bytes - $firstTail.private_bytes) / $tailSeconds, 3)
  }
  samples = @($samples)
}
[System.IO.File]::WriteAllText($output, ($result | ConvertTo-Json -Depth 8), [System.Text.UTF8Encoding]::new($false))
[ordered]@{ contract = $result.contract; root_pid = $result.root_pid; sample_count = $result.sample_count; peak = $result.peak; steady = $result.steady } | ConvertTo-Json -Depth 5
