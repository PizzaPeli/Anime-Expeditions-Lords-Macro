@echo off
setlocal
cd /d "%~dp0"

set "VENV_PYTHON=.venv\Scripts\python.exe"

if exist "%VENV_PYTHON%" goto venv_ready

echo Creating local Python virtual environment...
py -3.12 --version >nul 2>nul && goto create_with_py
python --version >nul 2>nul && goto create_with_python
goto no_python

:create_with_py
py -3.12 -m venv .venv
goto check_venv

:create_with_python
python -m venv .venv
goto check_venv

:check_venv
if errorlevel 1 goto venv_failed
if not exist "%VENV_PYTHON%" goto venv_failed

:venv_ready
echo Installing or updating automated-test dependencies...
"%VENV_PYTHON%" -m pip install -r requirements.txt -r requirements-dev.txt
if errorlevel 1 goto dependency_failed

echo.
echo Running automated tests...
"%VENV_PYTHON%" -m pytest tests
if errorlevel 1 goto tests_failed

echo.
echo Automated tests passed.
pause
exit /b 0

:no_python
echo.
echo Test run failed: Python 3.12 or newer was not found.
echo Install Python from python.org, then run this file again.
goto failed

:venv_failed
echo.
echo Test run failed while creating .venv.
goto failed

:dependency_failed
echo.
echo Test run failed while installing dependencies.
goto failed

:tests_failed
echo.
echo One or more automated tests failed. Review the output above.

:failed
pause
exit /b 1
