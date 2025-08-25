@ECHO OFF

REM Can be either py or python, depends on the system
SET PY_PATH=py
SET CWD=%~dp0

ECHO Creating venv...
CALL %PY_PATH% -m venv venv
ECHO Created venv.

ECHO Installing deps...
CALL %CWD%/venv/Scripts/pip.exe install -r requirements.txt
ECHO Installed deps.

PAUSE
