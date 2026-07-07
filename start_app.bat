@echo off

cd /d %~dp0

start "" python app.py

timeout /t 3

start "" http://127.0.0.1:5000

exit