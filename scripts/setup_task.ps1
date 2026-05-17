# Windows Task Scheduler 에 'BlogMaker\Cycle' 작업을 등록한다.
# 사용자 로그온 시 실행 + 매일 지정한 시각에 실행 (기본 매일 09:00).
#
# 사용 예:
#   pwsh -ExecutionPolicy Bypass -File .\scripts\setup_task.ps1
#   pwsh -ExecutionPolicy Bypass -File .\scripts\setup_task.ps1 -At "21:00"
#
# 주의: 사용자가 로그온되어 있어야 동작한다 — Claude Code CLI 세션이
# 사용자 컨텍스트에 묶여 있기 때문. "로그온 여부와 관계없이 실행"은 사용 불가.

param(
    [string]$At = '09:00',                      # HH:mm
    [string]$TaskName = 'BlogMaker\Cycle',
    [switch]$Remove
)

$ErrorActionPreference = 'Stop'

# 작업 제거 모드
if ($Remove) {
    if (Get-ScheduledTask -TaskName 'Cycle' -TaskPath '\BlogMaker\' -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName 'Cycle' -TaskPath '\BlogMaker\' -Confirm:$false
        Write-Output "[OK] 작업 제거: $TaskName"
    } else {
        Write-Output "[--] 등록된 작업 없음: $TaskName"
    }
    exit 0
}

$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$ScriptPath = Join-Path $RepoRoot 'scripts\run_cycle.ps1'

if (-not (Test-Path $ScriptPath)) {
    Write-Error "run_cycle.ps1 가 없음: $ScriptPath"
}

# 액션: PowerShell 로 run_cycle.ps1 실행
$Action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""

# 트리거: 매일 지정 시각
$Trigger = New-ScheduledTaskTrigger -Daily -At $At

# 설정: 절전 해제 후 실행 OK, AC 전원 제한 해제, 사용자 로그온 시 한정
$Principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -WakeToRun `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 90) `
    -MultipleInstances IgnoreNew

# 이미 등록돼 있으면 갱신
if (Get-ScheduledTask -TaskName 'Cycle' -TaskPath '\BlogMaker\' -ErrorAction SilentlyContinue) {
    Set-ScheduledTask -TaskName 'Cycle' -TaskPath '\BlogMaker\' `
        -Action $Action -Trigger $Trigger -Settings $Settings | Out-Null
    Write-Output "[OK] 작업 갱신: $TaskName (매일 $At)"
} else {
    Register-ScheduledTask -TaskName 'Cycle' -TaskPath '\BlogMaker\' `
        -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal | Out-Null
    Write-Output "[OK] 작업 등록: $TaskName (매일 $At)"
}

Write-Output ""
Write-Output "다음으로 확인:"
Write-Output "  schtasks /query /tn `"$TaskName`""
Write-Output "  Get-ScheduledTask -TaskName 'Cycle' -TaskPath '\BlogMaker\'"
Write-Output ""
Write-Output "수동 1회 트리거:"
Write-Output "  Start-ScheduledTask -TaskName 'Cycle' -TaskPath '\BlogMaker\'"
