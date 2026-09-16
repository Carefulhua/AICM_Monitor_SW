@echo off
rem  One-click launcher for the packaged AICM-NT4K DV monitor.
rem  Locates the exe under dist\ by pattern so this file stays pure
rem  ASCII: cmd decodes .bat files with the active code page (GBK by
rem  default), so any non-ASCII path written here would be corrupted.
setlocal
set "EXE="
for /d %%d in ("%~dp0dist\*") do (
    if /i not "%%~nxd"=="can_monitor" (
        for %%f in ("%%d\*.exe") do set "EXE=%%f"
    )
)
if not defined EXE (
    echo [ERROR] exe not found under %~dp0dist
    echo         Run build.bat first, then try again.
    pause
    exit /b 1
)
start "" "%EXE%"
endlocal
