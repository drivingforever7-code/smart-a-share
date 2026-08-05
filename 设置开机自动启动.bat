@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0设置开机自动启动.ps1"
if errorlevel 1 pause