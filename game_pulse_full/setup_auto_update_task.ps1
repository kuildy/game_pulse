$ErrorActionPreference = "Stop"
$Project = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Project ".venv\Scripts\python.exe"
$Updater = Join-Path $Project "scripts\update_games.py"

if (-not (Test-Path $Python)) {
    Write-Host "找不到 .venv。請先執行 start.bat 完成第一次安裝。" -ForegroundColor Yellow
    exit 1
}

$Action = New-ScheduledTaskAction `
    -Execute $Python `
    -Argument "`"$Updater`"" `
    -WorkingDirectory $Project

$Trigger = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date).AddMinutes(2) `
    -RepetitionInterval (New-TimeSpan -Hours 3) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

Register-ScheduledTask `
    -TaskName "GAME PULSE Auto Update" `
    -Action $Action `
    -Trigger $Trigger `
    -Description "每 3 小時更新 GAME PULSE 跨平台遊戲資料" `
    -Force | Out-Null

Write-Host "已建立 Windows 工作排程：GAME PULSE Auto Update" -ForegroundColor Green
Write-Host "之後每 3 小時會自動執行 scripts\update_games.py"
