$ErrorActionPreference = "Stop"
$startupFolder = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupFolder "智选A股.lnk"
if (Test-Path -LiteralPath $shortcutPath) {
    Remove-Item -LiteralPath $shortcutPath -Force
    Write-Host "已取消开机自动启动。" -ForegroundColor Green
} else {
    Write-Host "当前没有安装开机启动项。" -ForegroundColor Yellow
}
Start-Sleep -Seconds 2