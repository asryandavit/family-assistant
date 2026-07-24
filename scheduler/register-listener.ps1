# Registers the listener to start at logon and restart if it dies.
# Run in an ELEVATED PowerShell, then it also starts it immediately.

$Repo    = "D:\Claude\family-assistant"
$Pythonw = "C:\Users\davoa\AppData\Local\Programs\Python\Python314\pythonw.exe"

$action    = New-ScheduledTaskAction -Execute $Pythonw -Argument "`"$Repo\listener.py`"" -WorkingDirectory $Repo
$trigger   = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
             -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
             -ExecutionTimeLimit (New-TimeSpan -Days 3650)

Register-ScheduledTask -TaskName "FamilyAssistant-Listener" -Action $action -Trigger $trigger `
  -Principal $principal -Settings $settings -Force

Start-ScheduledTask -TaskName "FamilyAssistant-Listener"
Write-Host "Listener registered and started. Send /status to the bot to verify."
