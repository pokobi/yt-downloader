@echo off
rem Run from source without building the exe (no console window)
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" run.pyw
