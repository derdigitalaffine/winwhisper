@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Build-Windows.ps1" -InstallNode
if errorlevel 1 (
  echo.
  echo Der Build ist fehlgeschlagen. Bitte die Fehlermeldung oben lesen.
  pause
  exit /b 1
)
echo.
echo Die Setup-Datei liegt im Unterordner dist.
pause
