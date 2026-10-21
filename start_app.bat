@echo off

cd /d %~dp0

if exist "%~dp0.venv\Scripts\python.exe" (
    start "" "%~dp0.venv\Scripts\python.exe" "%~dp0app.py"
) else (
    start "" python "%~dp0app.py"
)

timeout /t 3

start "" http://127.0.0.1:5000

exit