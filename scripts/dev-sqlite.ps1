# OquMap development demo for Windows without Docker or PostgreSQL.
# Requirements: Git, Node.js 20+, uv. Run from any directory:
#   powershell -ExecutionPolicy Bypass -File scripts\dev-sqlite.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$ApiDir = Join-Path $Root "apps\api"
$WebDir = Join-Path $Root "apps\web"
$EnvFile = Join-Path $Root ".env"

function Stop-ProcessTree([int]$ProcessId) {
    Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId" -ErrorAction SilentlyContinue | ForEach-Object {
        Stop-ProcessTree ([int]$_.ProcessId)
    }
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

foreach ($Command in @("uv", "npm")) {
    if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
        throw "Не найдена команда '$Command'. Установите uv и Node.js 20+, затем откройте новый терминал."
    }
}

if (-not (Test-Path -LiteralPath $EnvFile)) {
    Copy-Item -LiteralPath (Join-Path $Root ".env.example") -Destination $EnvFile
}

$EnvText = [System.IO.File]::ReadAllText($EnvFile)
$KeyMatch = [regex]::Match($EnvText, '(?m)^OQUMAP_GEMINI_API_KEY=(.*)$')
$ExistingKey = if ($KeyMatch.Success) { $KeyMatch.Groups[1].Value.Trim() } else { "" }
if ([string]::IsNullOrWhiteSpace($ExistingKey) -or $ExistingKey.StartsWith("<")) {
    Write-Host "Вставьте Gemini API key. Символы не отображаются и команда не попадёт в историю терминала." -ForegroundColor Yellow
    $SecureKey = Read-Host "Gemini API key" -AsSecureString
    $Pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureKey)
    try {
        $PlainKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Pointer).Trim()
        if ([string]::IsNullOrWhiteSpace($PlainKey)) { throw "Gemini API key не может быть пустым." }
        if ($KeyMatch.Success) {
            $EnvText = [regex]::Replace($EnvText, '(?m)^OQUMAP_GEMINI_API_KEY=.*$', "OQUMAP_GEMINI_API_KEY=$PlainKey")
        }
        else {
            $EnvText = $EnvText.TrimEnd() + [Environment]::NewLine + "OQUMAP_GEMINI_API_KEY=$PlainKey" + [Environment]::NewLine
        }
        [System.IO.File]::WriteAllText($EnvFile, $EnvText, [System.Text.UTF8Encoding]::new($false))
    }
    finally {
        if ($Pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Pointer) }
        $PlainKey = $null
    }
}

# Environment variables override the PostgreSQL defaults from .env only for this local process tree.
$env:OQUMAP_DATABASE_URL = "sqlite:///./oqumap-demo.db"
$env:OQUMAP_DEPLOYMENT_MODE = "dev"
$env:OQUMAP_JOB_MODE = "inline"
$env:OQUMAP_CORS_ORIGINS = '["http://localhost:5173","http://127.0.0.1:5173"]'

Push-Location $ApiDir
try {
    Write-Host "[1/4] Подготавливаю Python 3.12 и зависимости..." -ForegroundColor Cyan
    uv python install 3.12
    uv sync --python 3.12

    Write-Host "[2/4] Применяю миграции и загружаю демонстрационные данные..." -ForegroundColor Cyan
    uv run alembic upgrade head
    uv run python -m oqumap.demo.seed

    Write-Host "[3/4] Запускаю API..." -ForegroundColor Cyan
    $ApiProcess = Start-Process -PassThru -WindowStyle Hidden uv -ArgumentList @(
        "run", "uvicorn", "oqumap.main:app", "--host", "127.0.0.1", "--port", "8000"
    )
}
finally {
    Pop-Location
}

try {
    $Ready = $false
    for ($Attempt = 1; $Attempt -le 180; $Attempt++) {
        if ($ApiProcess.HasExited) {
            throw "API завершился при запуске. Запустите вручную: cd apps\api; uv run uvicorn oqumap.main:app --port 8000"
        }
        try {
            $Health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health/ready" -TimeoutSec 2
            if ($Health.status -in @("ok", "ready")) { $Ready = $true; break }
        }
        catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $Ready) { throw "API не стал готов за 90 секунд." }

    Push-Location $WebDir
    Write-Host "[4/4] Устанавливаю frontend и запускаю OquMap..." -ForegroundColor Cyan
    npm ci
    Write-Host "Откройте http://localhost:5173 и нажмите «Открыть демо». Для остановки нажмите Ctrl+C." -ForegroundColor Green
    npm run dev
}
finally {
    if ($ApiProcess -and -not $ApiProcess.HasExited) {
        Stop-ProcessTree $ApiProcess.Id
    }
    if ((Get-Location).Path -eq $WebDir) { Pop-Location }
}
