# Sample GPU memory for the RX 9070 XT adapter and one process until a stop file
# appears or the process exits. Appends one CSV row per sample (flushes each row,
# so the file can be read while sampling runs). Sends nothing to any server.
#
# usage: powershell -File memsample.ps1 -ProcId <pid> -OutCsv <file> -StopFile <file> [-IntervalMs 500]
param([int]$ProcId, [string]$OutCsv, [string]$StopFile, [int]$IntervalMs = 500)
$adapter = '*15c57*'   # RX 9070 XT LUID on this machine (see logs/RUNLOG.md)
"t,ad_ded_mib,ad_sh_mib,p_ded_mib,p_sh_mib" | Set-Content -Encoding ascii $OutCsv
while (-not (Test-Path $StopFile)) {
  $alive = Get-Process -Id $ProcId -ErrorAction SilentlyContinue
  $ad = (Get-Counter "\GPU Adapter Memory(*)\Dedicated Usage","\GPU Adapter Memory(*)\Shared Usage").CounterSamples |
        Where-Object { $_.InstanceName -like $adapter }
  $d = ($ad | Where-Object { $_.Path -like '*dedicated usage' } | Measure-Object CookedValue -Sum).Sum
  $s = ($ad | Where-Object { $_.Path -like '*shared usage' } | Measure-Object CookedValue -Sum).Sum
  $pd = 0; $ps = 0
  if ($alive) {
    try {
      $pc = (Get-Counter "\GPU Process Memory(pid_$($ProcId)_*)\Dedicated Usage","\GPU Process Memory(pid_$($ProcId)_*)\Shared Usage" -ErrorAction Stop).CounterSamples |
            Where-Object { $_.InstanceName -like $adapter }
      $pd = ($pc | Where-Object { $_.Path -like '*dedicated usage' } | Measure-Object CookedValue -Sum).Sum
      $ps = ($pc | Where-Object { $_.Path -like '*shared usage' } | Measure-Object CookedValue -Sum).Sum
    } catch {}
  }
  "{0},{1},{2},{3},{4}" -f (Get-Date).ToString("HH:mm:ss.fff"), [math]::Round($d/1MB), [math]::Round($s/1MB),
    [math]::Round($pd/1MB), [math]::Round($ps/1MB) | Add-Content -Encoding ascii $OutCsv
  if (-not $alive) { break }
  Start-Sleep -Milliseconds $IntervalMs
}
