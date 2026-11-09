@echo off
REM Windows batch script to start the FastAPI server with Psycopg-compatible loops.

setlocal enabledelayedexpansion

REM Activate venv
call .venv\Scripts\activate.bat

.venv\Scripts\python.exe run_server.py

endlocal
