# Registers nightly housekeeping (jobs\housekeeping.py, decision 103) in Windows Task Scheduler:
#   FamilyAssistant-Housekeeping   daily 04:30   jobs\housekeeping.py --send
# 04:30 sits after Market watch (01:30, at most 60 min) and before the travel scan and the
# morning plan, so no bot browser should be open; one that is open is skipped anyway.
# It clears Chrome's caches in the bot's own profiles (.browser\*), rotates our logs, removes
# old Mini App inbox .tmp files and messages the owner if a disk is below min_free_gb
# (config_housekeeping.json). Runs as you, like the other jobs. A night the PC was off runs
# at the next start (StartWhenAvailable). Last run: .browser\housekeeping.log, selfcheck.py.
# Run in an ELEVATED PowerShell:  .\scheduler\register-housekeeping.ps1
# Optional: -Python "C:\path\to\pythonw.exe" (default: pythonw.exe next to `python` on PATH)

param([string]$Python = "")

$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Python) {
  $py = (Get-Command python -ErrorAction Stop).Source
  $Python = Join-Path (Split-Path -Parent $py) "pythonw.exe"
}
if (-not (Test-Path $Python)) { throw "Python not found: $Python" }

$Name = "FamilyAssistant-Housekeeping"
$action = New-ScheduledTaskAction -Execute $Python `
          -Argument "`"$Repo\jobs\housekeeping.py`" --send" -WorkingDirectory $Repo
$trigger = New-ScheduledTaskTrigger -Daily -At "04:30"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
            -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
            -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
Register-ScheduledTask -TaskName $Name -Action $action -Trigger $trigger `
  -Settings $settings -RunLevel Limited -Force | Out-Null
Write-Host "Registered $Name  (housekeeping.py --send, daily 04:30)"

Write-Host "`nRun it once now and read the one-line report:"
Write-Host "  Start-ScheduledTask -TaskName '$Name'; Start-Sleep 60; Get-Content .browser\housekeeping.log -Tail 1"
