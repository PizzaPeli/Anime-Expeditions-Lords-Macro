@echo off
setlocal
cd /d "%~dp0"

echo This resets all local Lords Macro test and user data in:
echo %CD%
echo.
echo It will remove:
echo   - settings and saved task state
echo   - custom templates and task presets
echo   - personal input recordings
echo   - debug captures, logs, and local updater metadata
echo.
echo All walking paths, camera profiles, Templates\examples, Assets, source files,
echo and executable build output will be preserved.
echo.
choice /C YN /N /M "Continue? [Y/N]: "
if errorlevel 2 (
    echo Cancelled. Nothing was changed.
    exit /b 0
)

del /F /Q "settings.json" "settings.json.tmp" 2>nul
del /F /Q "debug.log" "debug.log.*" "_update.log" 2>nul
del /F /Q "assets_manifest.json" ".bootstrap_version" ".bootstrap_download.zip" 2>nul

if exist "debug\" rmdir /S /Q "debug"
if exist "Recordings\" rmdir /S /Q "Recordings"

if exist "Templates\" (
    for /D %%D in ("Templates\*") do (
        if /I not "%%~nxD"=="examples" rmdir /S /Q "%%~fD"
    )
    for %%F in ("Templates\*") do (
        if not exist "%%~fF\" del /F /Q "%%~fF" 2>nul
    )
)

echo.
echo Local data reset complete. Shipped defaults and examples were preserved.
pause
endlocal
