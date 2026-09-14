@echo off
setlocal
cd /d "%~dp0"

rem The repository can be opened through RDP by several Windows accounts.
rem A venv inside it belongs to whichever account created it and can point at
rem that account's private Python install.  Keep this disposable build venv
rem under the current user's LocalAppData instead, so every account gets an
rem independent interpreter and package cache.
set "TEST_ROOT=%LOCALAPPDATA%\LordsMacroTestBuild"
set "VENV_DIR=%TEST_ROOT%\venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "TEST_DIST=%TEST_ROOT%\dist"
set "LORDS_MACRO_BUILD_DIST=%TEST_DIST%"
set "LORDS_MACRO_BUILD_WORK=%TEST_ROOT%\build"
set "APP_EXE=%TEST_DIST%\Lords Macro - Anime Expeditions.exe"

rem A per-user venv can still become stale after a Python update, so test
rem whether it launches before trusting it.
if not exist "%VENV_PYTHON%" goto create_venv
"%VENV_PYTHON%" --version >nul 2>nul && goto venv_ready
echo Existing per-user test environment cannot run -- recreating it...
rmdir /S /Q "%VENV_DIR%"
if exist "%VENV_DIR%\" goto venv_reset_failed

:create_venv

echo Creating this user's Python virtual environment...
py -3.12 --version >nul 2>nul && goto create_with_py
python --version >nul 2>nul && goto create_with_python
goto no_python

:create_with_py
py -3.12 -m venv "%VENV_DIR%"
goto check_venv

:create_with_python
python -m venv "%VENV_DIR%"
goto check_venv

:check_venv
if errorlevel 1 goto venv_failed
if not exist "%VENV_PYTHON%" goto venv_failed

:venv_ready
rem Bring durable playtest work back before resetting the disposable state.
rem Assets includes map screenshots and camera profiles; Paths contains new
rem recordings made from the test executable.
if exist "%TEST_DIST%\Assets\" (
    echo Preserving new or updated assets from the previous test build...
    xcopy "%TEST_DIST%\Assets" "Assets\" /D /E /I /Y /Q >nul
    if errorlevel 1 goto preserve_assets_failed
)
if exist "%TEST_DIST%\Paths\" (
    echo Preserving walking paths from the previous test build...
    if not exist "Paths\defaults\" mkdir "Paths\defaults"
    xcopy "%TEST_DIST%\Paths" "Paths\defaults\" /D /E /I /Y /Q >nul
    if errorlevel 1 goto preserve_paths_failed
)

echo Resetting disposable data from the previous playtest...
del /F /Q "%TEST_DIST%\settings.json" "%TEST_DIST%\settings.json.tmp" 2>nul
del /F /Q "%TEST_DIST%\debug.log" "%TEST_DIST%\debug.log.*" "%TEST_DIST%\_update.log" 2>nul
del /F /Q "%TEST_DIST%\assets_manifest.json" "%TEST_DIST%\.bootstrap_version" "%TEST_DIST%\.bootstrap_download.zip" 2>nul
if exist "%TEST_DIST%\debug\" rmdir /S /Q "%TEST_DIST%\debug"
if exist "%TEST_DIST%\Recordings\" rmdir /S /Q "%TEST_DIST%\Recordings"
if exist "%TEST_DIST%\Templates\" rmdir /S /Q "%TEST_DIST%\Templates"

echo Installing or updating runtime and build dependencies...
"%VENV_PYTHON%" -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto dependency_failed

echo.
echo Building the interactive test executable...
"%VENV_PYTHON%" build_pyinstaller.py
if errorlevel 1 goto build_failed
if not exist "%APP_EXE%" goto missing_exe

echo Copying editable Assets beside the executable...
xcopy "Assets" "%TEST_DIST%\Assets\" /E /I /Y /Q >nul
if errorlevel 1 goto assets_failed

echo.
echo The isolated playtest environment is ready.
echo Roblox may be started normally; this exe will attach to that normal Roblox window.
echo Launching %APP_EXE%...
pushd "%TEST_DIST%"
start "" /WAIT "Lords Macro - Anime Expeditions.exe"
popd

echo Preserving assets and walking paths created during this test...
xcopy "%TEST_DIST%\Assets" "Assets\" /D /E /I /Y /Q >nul
if errorlevel 1 goto preserve_assets_failed
if exist "%TEST_DIST%\Paths\" (
    if not exist "Paths\defaults\" mkdir "Paths\defaults"
    xcopy "%TEST_DIST%\Paths" "Paths\defaults\" /D /E /I /Y /Q >nul
    if errorlevel 1 goto preserve_paths_failed
)
echo Shared test data is now ready to review with git status.
echo Disposable session metadata remains in %TEST_DIST%\settings.json until the next run.
echo It includes the settings used and the accumulated playtest time.
exit /b 0

:no_python
echo.
echo Test build failed: Python 3.12 or newer was not found.
echo Install Python from python.org, then run this file again.
goto failed

:venv_failed
echo.
echo Test build failed while creating this user's virtual environment.
goto failed

:venv_reset_failed
echo.
echo Test build found an unusable per-user virtual environment but could not remove it.
echo Close anything using this project, then delete "%VENV_DIR%" and run TEST_BUILD.bat again.
goto failed

:dependency_failed
echo.
echo Test build failed while installing dependencies.
goto failed

:build_failed
echo.
echo PyInstaller failed to build the executable.
goto failed

:missing_exe
echo.
echo The build finished without creating the expected executable:
echo %APP_EXE%
goto failed

:assets_failed
echo.
echo The executable was built, but Assets could not be copied beside it.
goto failed

:preserve_assets_failed
echo.
echo Test build stopped because assets from the previous test environment
echo could not be copied back into the project Assets folder.
goto failed

:preserve_paths_failed
echo.
echo Test build stopped because walking paths from the test environment
echo could not be copied into the tracked Paths\defaults folder.

:failed
pause
exit /b 1
