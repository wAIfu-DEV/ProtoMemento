@ECHO OFF

REM Can be either py or python, depends on the system
SET PY_PATH=py
SET CWD=%~dp0

ECHO Creating venv...
CALL %PY_PATH% -m venv venv
ECHO Created venv.

ECHO Installing deps...
REM CALL %CWD%/venv/Scripts/pip.exe install -r torch_req.txt
CALL %CWD%/venv/Scripts/pip.exe install -r requirements.txt
ECHO Installed deps.

IF NOT EXIST "%CWD%/.env" (
    ECHO Creating .env file
    ECHO OPENAI_API_KEY= > %CWD%/.env
)

PAUSE
