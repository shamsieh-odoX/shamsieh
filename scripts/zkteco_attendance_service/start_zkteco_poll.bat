@echo off
REM ZKTeco poll bridge — keep Attendance Management disconnected while this runs.
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m app.main
) else (
  python -m app.main
)
