$ErrorActionPreference = "Stop"
$projectRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$pythonPath = Join-Path $projectRoot "backend\.venv\Scripts\python.exe"
$vitePath = Join-Path $projectRoot "node_modules\vite\bin\vite.js"
$nodeCommand = Get-Command node -ErrorAction SilentlyContinue
$runtimeDir = Join-Path $projectRoot ".codex-runtime"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    Write-Host "还没有安装 Python 后端依赖。请先运行：安装依赖.ps1" -ForegroundColor Yellow
    Read-Host "按回车键关闭"
    exit 1
}
if (-not $nodeCommand -or -not (Test-Path -LiteralPath $vitePath)) {
    Write-Host "还没有安装前端依赖。请先运行：安装依赖.ps1" -ForegroundColor Yellow
    Read-Host "按回车键关闭"
    exit 1
}
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null

function Test-WebsiteReady {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:5173" -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -eq 200
    } catch { return $false }
}
if (Test-WebsiteReady) { Start-Process "http://127.0.0.1:5173"; exit 0 }

$backendProcess = $null
$frontendProcess = $null
try {
    Write-Host "正在后台启动智选 A 股..." -ForegroundColor Cyan
    $backendProcess = Start-Process -FilePath $pythonPath -ArgumentList @("-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", "127.0.0.1", "--port", "8710") -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimeDir "backend.out.log") -RedirectStandardError (Join-Path $runtimeDir "backend.err.log") -PassThru
    $frontendProcess = Start-Process -FilePath $nodeCommand.Source -ArgumentList @($vitePath, "--host", "127.0.0.1", "--port", "5173") -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimeDir "frontend.out.log") -RedirectStandardError (Join-Path $runtimeDir "frontend.err.log") -PassThru
    $ready = $false
    for ($attempt = 0; $attempt -lt 40; $attempt++) { Start-Sleep -Milliseconds 500; if (Test-WebsiteReady) { $ready = $true; break } }
    if (-not $ready) { throw "网站启动超时，请检查 .codex-runtime 日志。" }
    Write-Host "网站已启动：http://127.0.0.1:5173" -ForegroundColor Green
    Write-Host "窗口会自动关闭，网站仍在后台运行到关机。" -ForegroundColor DarkGray
    Start-Process "http://127.0.0.1:5173"
    Start-Sleep -Seconds 2
} catch {
    if ($frontendProcess -and -not $frontendProcess.HasExited) { Stop-Process -Id $frontendProcess.Id -Force -ErrorAction SilentlyContinue }
    if ($backendProcess -and -not $backendProcess.HasExited) { Stop-Process -Id $backendProcess.Id -Force -ErrorAction SilentlyContinue }
    Write-Host "启动失败：$($_.Exception.Message)" -ForegroundColor Red
    Read-Host "按回车键关闭"
    exit 1
}