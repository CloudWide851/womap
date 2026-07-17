@echo off
setlocal

set "ROOT=%~dp0"
set "LAUNCHER=%ROOT%scripts\launcher.ps1"

if not exist "%LAUNCHER%" (
  echo [WOMAP] Launcher not found: %LAUNCHER%
  exit /b 1
)

if "%~1"=="" (
  where wt.exe >nul 2>nul
  if not errorlevel 1 (
    wt.exe new-tab --title "WOMAP Workbench" powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%LAUNCHER%" run
    exit /b %ERRORLEVEL%
  )

  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%LAUNCHER%" run
  exit /b %ERRORLEVEL%
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%LAUNCHER%" %*
exit /b %ERRORLEVEL%
