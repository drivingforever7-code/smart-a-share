$ErrorActionPreference = "Stop"

$projectRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
Set-Location -LiteralPath $projectRoot

Write-Host "正在检查运行环境..." -ForegroundColor Cyan

$nodeCommand = Get-Command node -ErrorAction SilentlyContinue
$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $nodeCommand -or -not $npmCommand) {
    Write-Host "没有找到 Node.js。请先安装 Node.js 20 或更高版本：" -ForegroundColor Yellow
    Write-Host "https://nodejs.org/"
    Read-Host "安装后重新运行本脚本，按回车键关闭"
    exit 1
}

$venvPython = Join-Path $projectRoot "backend\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        Write-Host "没有找到 Python。请先安装 Python 3.11 或 3.12：" -ForegroundColor Yellow
        Write-Host "https://www.python.org/downloads/windows/"
        Write-Host "安装时请勾选 Add Python to PATH。"
        Read-Host "安装后重新运行本脚本，按回车键关闭"
        exit 1
    }
    Write-Host "正在建立项目专用 Python 环境..."
    & $pythonCommand.Source -m venv "backend\.venv"
}

Write-Host "正在安装 Python 数据与接口依赖..."
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r "backend\requirements.txt"

Write-Host "正在安装网页依赖..."
& $npmCommand.Source install

Write-Host ""
Write-Host "安装完成。现在可以运行“启动网站.bat”。" -ForegroundColor Green
Read-Host "按回车键关闭"
