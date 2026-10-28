Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'Unreal|Crash' } | ForEach-Object { "{0} {1} {2:N0}MB {3}" -f $_.ProcessId, $_.Name, ($_.WorkingSetSize/1MB), $_.CommandLine }
