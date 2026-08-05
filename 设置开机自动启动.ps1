$ErrorActionPreference = "Stop"
$projectRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$launcherPath = Join-Path $projectRoot "后台启动网站.vbs"
$startupFolder = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupFolder "智选A股.lnk"
$wscriptPath = Join-Path ([Environment]::SystemDirectory) "wscript.exe"
if (-not (Test-Path -LiteralPath $launcherPath)) { throw "找不到后台启动程序：$launcherPath" }
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $wscriptPath
$shortcut.Arguments = '"' + $launcherPath + '"'
$shortcut.WorkingDirectory = $projectRoot
$shortcut.Description = "登录 Windows 后自动启动智选 A 股本地网站"
$shortcut.Save()
Write-Host "已设置开机自动启动。" -ForegroundColor Green
Write-Host "下次登录 Windows 后会自动启动：http://127.0.0.1:5173"
Start-Sleep -Seconds 2