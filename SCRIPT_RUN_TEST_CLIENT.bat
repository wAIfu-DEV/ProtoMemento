@ECHO OFF

REM Can be either py or python, depends on the system
SET PY_PATH=py
SET CWD=%~dp0

ECHO Running...
CALL %CWD%/venv/Scripts/python.exe test_client_main.py

PAUSE
