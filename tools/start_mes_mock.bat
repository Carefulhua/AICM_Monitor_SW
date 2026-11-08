@echo off
chcp 65001 >nul
rem 双击启动本地 MES 桩（模拟工厂 MES，接收 04 并回显内容）
cd /d "%~dp0.."
set "PY=C:\ProgramData\anaconda3\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" tools\mes_mock_server.py --port 8090 %*
pause
