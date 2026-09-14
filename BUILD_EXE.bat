@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto use_venv
py -3.12 --version >nul 2>nul && goto use_py_launcher
python --version >nul 2>nul && goto use_python
goto no_python

:use_venv
set "PYTHON_CMD=.venv\Scripts\python.exe"
goto python_ready

:use_py_launcher
set "PYTHON_CMD=py -3.12"
goto python_ready

:use_python
set "PYTHON_CMD=python"
goto python_ready

:no_python
echo Build failed: Python 3.12 or newer was not found.
echo Install Python, then run this file again.
pause
exit /b 1

:python_ready
%PYTHON_CMD% -m PyInstaller --version >nul 2>nul
if errorlevel 1 (
    echo PyInstaller is not installed for the selected Python environment.
    echo Run: %PYTHON_CMD% -m pip install pyinstaller
    pause
    exit /b 1
)

echo Building Lords Macro - Anime Expeditions.exe...
%PYTHON_CMD% build_pyinstaller.py
if errorlevel 1 (
    echo.
    echo The executable build failed. Review the messages above.
    pause
    exit /b 1
)

echo.
echo Build complete: dist\Lords Macro - Anime Expeditions.exe
pause
endlocal
