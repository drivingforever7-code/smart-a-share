$ErrorActionPreference = "Stop"

$projectRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$pythonPath = Join-Path $projectRoot "backend\.venv\Scripts\python.exe"
$vitePath = Join-Path $projectRoot "node_modules\vite\bin\vite.js"
$nodeCommand = Get-Command node -ErrorAction SilentlyContinue

if (-not (Test-Path -LiteralPath $pythonPath)) {
    Write-Host "还没有安装 Python 后端依赖。" -ForegroundColor Yellow
    Write-Host "请先运行：安装依赖.ps1"
    Read-Host "按回车键关闭"
    exit 1
}

if (-not $nodeCommand -or -not (Test-Path -LiteralPath $vitePath)) {
    Write-Host "还没有安装前端依赖。" -ForegroundColor Yellow
    Write-Host "请先运行：安装依赖.ps1"
    Read-Host "按回车键关闭"
    exit 1
}

$backendProcess = $null
$frontendProcess = $null

try {
    Write-Host ""
    Write-Host "正在启动智选 A 股..." -ForegroundColor Cyan

    $backendArguments = @("-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", "127.0.0.1", "--port", "8710")
    $backendProcess = Start-Process -FilePath $pythonPath -ArgumentList $backendArguments -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru

    $frontendArguments = @($vitePath, "--host", "127.0.0.1", "--port", "5173")
    $frontendProcess = Start-Process -FilePath $nodeCommand.Source -ArgumentList $frontendArguments -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru

    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 500
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:5173" -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                $ready = $true
                break
            }
        } catch {
            # 服务仍在启动，继续等待。
        }
    }

    if (-not $ready) {
        throw "网站启动超时，请检查 5173 和 8710 端口是否被其他程序占用。"
    }

    Write-Host "网站已启动：http://127.0.0.1:5173" -ForegroundColor Green
    Write-Host "第一次更新全市场数据可能需要几十秒，请耐心等待。" -ForegroundColor DarkGray
    Start-Process "http://127.0.0.1:5173"
    Write-Host ""
    Read-Host "使用结束后，在这里按回车键停止网站"
}
catch {
    Write-Host ""
    Write-Host "启动失败：$($_.Exception.Message)" -ForegroundColor Red
    Read-Host "按回车键关闭"
}
finally {
    if ($frontendProcess -and -not $frontendProcess.HasExited) {
        Stop-Process -Id $frontendProcess.Id -Force -ErrorAction SilentlyContinue
    }
    if ($backendProcess -and -not $backendProcess.HasExited) {
        Stop-Process -Id $backendProcess.Id -Force -ErrorAction SilentlyContinue
    }
    Write-Host "本地服务已停止。" -ForegroundColor DarkGray
}
