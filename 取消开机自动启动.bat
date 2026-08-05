@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0取消开机自动启动.ps1"
if errorlevel 1 pause