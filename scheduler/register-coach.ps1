# Registers the plan messages (decision 085) in Windows Task Scheduler:
#   FamilyAssistant-Coach-Morning   daily 07:30   jobs\coach_brief.py --morning
#   FamilyAssistant-Coach-Week      Sunday 18:00  jobs\coach_brief.py --week
# Same logon setup as the travel task (register-tasks.ps1): runs as you, wakes the PC,
# runs on battery. No catch-up start: a late morning message is dropped by the job anyway
# (after 10:00, COACH_SPEC section 12).
# Run in an ELEVATED PowerShell:  .\scheduler\register-coach.ps1
# Optional: -Python "C:\path\to\pythonw.exe" (default: pythonw.exe next to `python` on PATH)

param([string]$Python = "")

$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Python) {
  $py = (Get-Command python -ErrorAction Stop).Source
  $Python = Join-Path (Split-Path -Parent $py) "pythonw.exe"
}
if (-not (Test-Path $Python)) { throw "Python not found: $Python" }

$Jobs = @(
  @{ Name = "FamilyAssistant-Coach-Morning"; Arg = "--morning";
     Trigger = (New-ScheduledTaskTrigger -Daily -At "07:30") },
  @{ Name = "FamilyAssistant-Coach-Week"; Arg = "--week";
     Trigger = (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "18:00") }
)

foreach ($j in $Jobs) {
  $action = New-ScheduledTaskAction -Execute $Python `
            -Argument "`"$Repo\jobs\coach_brief.py`" $($j.Arg)" -WorkingDirectory $Repo
  $settings = New-ScheduledTaskSettingsSet -WakeToRun `
              -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
              -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
  Register-ScheduledTask -TaskName $j.Name -Action $action -Trigger $j.Trigger `
    -Settings $settings -RunLevel Limited -Force | Out-Null
  Write-Host "Registered $($j.Name)  ($($j.Arg))"
}

Write-Host "`nTest one now (sends to both chats):"
Write-Host "  Start-ScheduledTask -TaskName 'FamilyAssistant-Coach-Morning'"
