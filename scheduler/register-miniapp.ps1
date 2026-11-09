# Mini App step 0 (docs/briefs/MINI_APP.md, decision 094):
#   1. builds the web app with the PC's Windows Node (npm ci + npm run build in miniapp\web)
#   2. registers FamilyAssistant-MiniApp: at logon, runs `pythonw -m miniapp.server`
#      (127.0.0.1 only), restarts it if it dies, and starts it now
#   3. checks `tailscale funnel status` -- shows it, never changes it (setup: docs/SECRETS.md)
# Run in PowerShell from the repo:  .\scheduler\register-miniapp.ps1
# Options: -Python "C:\path\to\pythonw.exe"  (default: pythonw.exe next to `python` on PATH)
#          -SkipBuild                         (re-register only; keeps the current dist\)
# Node: `npm` on PATH, else machine.json "node_dir" (e.g. the nvm4w folder). Build time only.

param([string]$Python = "", [switch]$SkipBuild)
$ErrorActionPreference = "Stop"

$Repo = Split-Path -Parent $PSScriptRoot
$Web  = Join-Path $Repo "miniapp\web"
$Cfg  = Get-Content (Join-Path $Repo "config_miniapp.json") -Raw | ConvertFrom-Json
$MachinePath = Join-Path $Repo "machine.json"
$Machine = if (Test-Path $MachinePath) { Get-Content $MachinePath -Raw | ConvertFrom-Json } else { $null }

if (-not $Python) {
  $py = (Get-Command python -ErrorAction Stop).Source
  $Python = Join-Path (Split-Path -Parent $py) "pythonw.exe"
}
if (-not (Test-Path $Python)) { throw "Python not found: $Python" }

# ---- 1. build
if (-not $SkipBuild) {
  if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    if ($Machine -and $Machine.node_dir -and (Test-Path $Machine.node_dir)) {
      $env:Path = "$($Machine.node_dir);$env:Path"
    } else {
      throw "npm not found. Put Node on PATH or set machine.json node_dir (docs/SECRETS.md)."
    }
  }
  Write-Host "Node $(node --version), building miniapp\web ..."
  Push-Location $Web
  try {
    npm ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw "npm ci failed" }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }
  } finally { Pop-Location }
}
if (-not (Test-Path (Join-Path $Web "dist\index.html"))) { throw "miniapp\web\dist\index.html missing" }

# ---- 2. scheduled task
$Name = "FamilyAssistant-MiniApp"
$User = "$env:USERDOMAIN\$env:USERNAME"
$action    = New-ScheduledTaskAction -Execute $Python -Argument "-m miniapp.server" -WorkingDirectory $Repo
$trigger   = New-ScheduledTaskTrigger -AtLogOn -User $User
$principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Limited
$settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
             -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
             -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Days 3650)
if (Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue) {
  Stop-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
}
Register-ScheduledTask -TaskName $Name -Action $action -Trigger $trigger `
  -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName $Name
Write-Host "Registered and started $Name  ($Python -m miniapp.server)"

$Local = "http://127.0.0.1:$($Cfg.port)/"
$ok = $false
foreach ($i in 1..10) {
  Start-Sleep -Seconds 1
  try {
    $r = Invoke-WebRequest $Local -UseBasicParsing -TimeoutSec 3
    if ($r.StatusCode -eq 200) { $ok = $true; break }
  } catch { }
}
if ($ok) { Write-Host "Server answers on $Local" }
else { Write-Warning "No answer on $Local -- see .browser\miniapp.log" }

# ---- 3. tunnel (checked, never changed)
$ts = Get-Command tailscale -ErrorAction SilentlyContinue
if (-not $ts) {
  Write-Warning "tailscale not found -- the app is not reachable from Telegram (docs/SECRETS.md, Mini App)"
} else {
  $status = (& tailscale funnel status 2>&1 | Out-String).Trim()
  if ($status -match "No serve config" -or $status -notmatch "Funnel on") {
    Write-Warning "Tailscale Funnel is not serving. One-time setup: docs/SECRETS.md, Mini App section."
  } elseif ($status -notmatch "127\.0\.0\.1:$($Cfg.port)") {
    Write-Warning "Funnel is on but not pointing at 127.0.0.1:$($Cfg.port):"
  } else {
    Write-Host "Tailscale Funnel is serving the app."
  }
  Write-Host ($status -replace "https://[^\s]+", "https://<this-pc>.ts.net")
}
if (-not ($Machine -and $Machine.miniapp_public_url)) {
  Write-Warning "machine.json miniapp_public_url is not set (needed by python -m miniapp.setup_bot)."
}
Write-Host "`nNext: python -m miniapp.setup_bot   (sets the menu button in both chats)"
