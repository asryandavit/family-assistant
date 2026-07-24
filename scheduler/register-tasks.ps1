# Registers three daily tasks in Windows Task Scheduler.
# Run in an ELEVATED PowerShell (Run as administrator).
# Edit $Repo and $Python to match your machine, then run:  .\register-tasks.ps1

$Repo   = "C:\family-assistant"
$Python = "C:\Users\YOU\AppData\Local\Programs\Python\Python312\python.exe"

# job name -> "HH:mm" start time (staggered so they don't overlap)
$Jobs = @{
  "FamilyAssistant-Travel"   = @{ Script = "jobs\travel_scan.py"; Time = "08:00" }
  "FamilyAssistant-Training" = @{ Script = "jobs\training.py";    Time = "06:30" }
  "FamilyAssistant-Meals"    = @{ Script = "jobs\meals.py";       Time = "07:00" }
}

foreach ($name in $Jobs.Keys) {
  $j = $Jobs[$name]
  $action = New-ScheduledTaskAction -Execute $Python `
            -Argument "`"$Repo\$($j.Script)`"" -WorkingDirectory $Repo
  $trigger = New-ScheduledTaskTrigger -Daily -At $j.Time
  # Wake the machine if asleep; run even on battery
  $settings = New-ScheduledTaskSettingsSet -WakeToRun `
              -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
              -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

  Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger `
    -Settings $settings -RunLevel Limited -Force
  Write-Host "Registered $name at $($j.Time)"
}

Write-Host "`nDone. View them in Task Scheduler, or test one now with:"
Write-Host "  Start-ScheduledTask -TaskName 'FamilyAssistant-Travel'"
