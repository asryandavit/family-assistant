# Registers Market watch (docs/briefs/MARKET_WATCH.md, decision 087) in Windows Task Scheduler:
#   FamilyAssistant-Market-Watch     daily 01:30    jobs\market_watch.py --send
#   FamilyAssistant-Market-Tariffs   Sunday 01:00   jobs\market_tariffs.py --send
# Same logon setup as the travel and coach tasks: runs as you (the store pages open in a
# visible browser, so you must be logged on), wakes the PC, runs on battery. A missed night
# shows up as a stale last_run in the report and in the Runs tab.
# Run in an ELEVATED PowerShell:  .\scheduler\register-market.ps1
# Optional: -Python "C:\path\to\pythonw.exe" (default: pythonw.exe next to `python` on PATH)

param([string]$Python = "")

$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Python) {
  $py = (Get-Command python -ErrorAction Stop).Source
  $Python = Join-Path (Split-Path -Parent $py) "pythonw.exe"
}
if (-not (Test-Path $Python)) { throw "Python not found: $Python" }

$Jobs = @(
  @{ Name = "FamilyAssistant-Market-Watch"; Script = "market_watch.py"; Limit = 60;
     Trigger = (New-ScheduledTaskTrigger -Daily -At "01:30") },
  @{ Name = "FamilyAssistant-Market-Tariffs"; Script = "market_tariffs.py"; Limit = 15;
     Trigger = (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "01:00") }
)

foreach ($j in $Jobs) {
  $action = New-ScheduledTaskAction -Execute $Python `
            -Argument "`"$Repo\jobs\$($j.Script)`" --send" -WorkingDirectory $Repo
  $settings = New-ScheduledTaskSettingsSet -WakeToRun `
              -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
              -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes $j.Limit)
  Register-ScheduledTask -TaskName $j.Name -Action $action -Trigger $j.Trigger `
    -Settings $settings -RunLevel Limited -Force | Out-Null
  Write-Host "Registered $($j.Name)  ($($j.Script) --send)"
}

Write-Host "`nTest the nightly run now (sends to both chats):"
Write-Host "  Start-ScheduledTask -TaskName 'FamilyAssistant-Market-Watch'"
