# blogMaker 한 사이클 실행 래퍼. Task Scheduler 가 이 파일을 호출.
# 흐름: venv 활성 → .env 라인 파싱해 환경변수 주입 → python -m src.main → 로그 저장.

$ErrorActionPreference = 'Stop'

# 1) blogMaker 루트로 이동 (이 스크립트 기준)
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
Set-Location $RepoRoot

# 2) venv 활성
$VenvActivate = Join-Path $RepoRoot '.venv\Scripts\Activate.ps1'
if (-not (Test-Path $VenvActivate)) {
    Write-Error "venv 가 없음: $VenvActivate. 'python -m venv .venv' 후 'pip install -e .' 먼저 실행."
}
. $VenvActivate

# 3) .env 라인 파싱 (간단 — KEY=VALUE, # 주석/빈 줄 무시)
$EnvFile = Join-Path $RepoRoot '.env'
if (Test-Path $EnvFile) {
    Get-Content $EnvFile -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if (-not $line) { return }
        if ($line.StartsWith('#')) { return }
        $idx = $line.IndexOf('=')
        if ($idx -lt 1) { return }
        $key = $line.Substring(0, $idx).Trim()
        $val = $line.Substring($idx + 1).Trim()
        # 양쪽 따옴표 제거
        if ($val.StartsWith('"') -and $val.EndsWith('"')) {
            $val = $val.Substring(1, $val.Length - 2)
        }
        Set-Item -Path "env:$key" -Value $val
    }
}

# 4) 로그 파일 (사이클별)
$LogDir = Join-Path $RepoRoot 'logs'
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$Stamp = Get-Date -Format 'yyyyMMdd-HHmm'
$CycleLog = Join-Path $LogDir "cycle_$Stamp.log"

# 5) 사이클 실행
python -m src.main *>&1 | Tee-Object -FilePath $CycleLog
$Code = $LASTEXITCODE

Write-Output "exit_code=$Code log=$CycleLog"
exit $Code
