@echo off
setlocal
cd /d "%~dp0\..\.."

rem Always test the one current project executable, with per-account data.
set "TEST_ROOT=%LOCALAPPDATA%\LordsMacroTestBuild"
set "TEST_DIST=%TEST_ROOT%\dist"
set "APP_EXE=%TEST_DIST%\Lords Macro - Anime Expeditions.exe"
set "TEST_PROJECT_ROOT=%CD%"
if exist "%TEST_ROOT%\venv\Scripts\python.exe" (
    "%TEST_ROOT%\venv\Scripts\python.exe" --version >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_CMD="%TEST_ROOT%\venv\Scripts\python.exe""
        goto python_ready
    )
)
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe --version >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_CMD=.venv\Scripts\python.exe"
        goto python_ready
    )
)
py -3.12 --version >nul 2>nul && (
    set "PYTHON_CMD=py -3.12"
    goto python_ready
)
python --version >nul 2>nul && (
    set "PYTHON_CMD=python"
    goto python_ready
)
goto no_python

:python_ready
%PYTHON_CMD% --version >nul 2>nul
if errorlevel 1 goto no_python

:venv_ready
if /I "%~1"=="--export-only" goto export_only

rem Resume/fresh applies only to this account's isolated test folder.
%PYTHON_CMD% scripts\windows\playtest_session.py --dist "%TEST_DIST%" --project "%TEST_PROJECT_ROOT%" --prepare
if errorlevel 1 goto export_failed

echo Syncing the current project executable...
%PYTHON_CMD% scripts\windows\playtest_session.py --dist "%TEST_DIST%" --project "%TEST_PROJECT_ROOT%" --sync-exe
if errorlevel 1 goto sync_failed
if not exist "%APP_EXE%" goto missing_exe

echo.
echo The isolated playtest environment is ready.
echo Roblox may be started normally; this exe will attach to that normal Roblox window.
echo Launching %APP_EXE%...
rem The supervisor waits for the actual exe to close (including a crash),
rem then copies every data file back to the original source project.
%PYTHON_CMD% scripts\windows\playtest_session.py --dist "%TEST_DIST%" --project "%TEST_PROJECT_ROOT%"
if errorlevel 1 goto export_failed

echo This account's complete setup remains in %TEST_DIST% for the next test.
echo Private changes are archived for review; they are not copied into release source.
echo Test logs, screenshots, and settings were saved to:
echo %TEST_PROJECT_ROOT%\test-output
exit /b 0

:export_only
%PYTHON_CMD% scripts\windows\playtest_session.py --dist "%TEST_DIST%" --project "%TEST_PROJECT_ROOT%" --recover
if errorlevel 1 goto export_failed
exit /b 0

:export_failed
echo.
echo The test data could not be archived in the project folder.
echo This Windows account needs write access to "%TEST_PROJECT_ROOT%\test-output".
echo Original data was retained in "%TEST_DIST%". The next run will retry before resetting it.
goto failed

:no_python
echo.
echo Test build failed: Python 3.12 or newer was not found.
echo Install Python from python.org, then run this file again.
goto failed

:sync_failed
echo.
echo Could not sync the current executable. Close this account's running test first.
echo If the project executable is missing, run BUILD_EXE.bat.
goto failed

:missing_exe
echo.
echo The build finished without creating the expected executable:
echo %APP_EXE%
goto failed

:failed
pause
exit /b 1
