@ECHO OFF

SET PY_PATH=py
SET CWD=%~dp0

ECHO Running...
CALL %CWD%/venv/Scripts/python.exe main.py

PAUSE
