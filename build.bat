@echo off
rem Build YT Downloader -> dist\YTDownloader\YTDownloader.exe
rem (messages are ASCII only so that cmd.exe parses this file reliably)
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto :deps
echo [1/3] Creating Python virtual environment...
python -m venv .venv
if errorlevel 1 goto :error

:deps
echo [2/3] Installing requirements...
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 goto :error

echo [3/3] Building exe...
".venv\Scripts\pyinstaller.exe" --noconfirm --clean ytdownloader.spec
if errorlevel 1 goto :error

rem Put the browser extension next to the exe
robocopy extension "dist\YTDownloader\extension" /MIR /NFL /NDL /NJH /NJS >nul
if errorlevel 8 goto :error

echo.
echo Done: %~dp0dist\YTDownloader\YTDownloader.exe
exit /b 0

:error
echo Build failed.
exit /b 1
