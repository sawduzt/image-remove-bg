@echo off
setlocal
title Remove BG - install
set "SRC=%~dp0"
set "DEST=%LOCALAPPDATA%\RemoveBG"

echo.
echo   Remove BG  -  setup
echo   installing to %DEST%
echo.

rem stop a running copy so the files can be replaced
taskkill /f /im removebg.exe >nul 2>&1

if not exist "%DEST%" mkdir "%DEST%" 2>nul
robocopy "%SRC%removebg" "%DEST%" /E /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (
  echo   ERROR: could not copy the files to %DEST%
  echo.
  pause
  exit /b 1
)
copy /y "%SRC%uninstall.bat" "%DEST%\uninstall.bat" >nul 2>&1

"%DEST%\removebg.exe" --install
if errorlevel 1 (
  echo.
  echo   The right-click menu could not be registered - see above.
  echo.
  pause
  exit /b 1
)

echo.
echo   The balanced model is 176 MB. Fetching it now saves a wait on your
echo   first right-click, but it is optional - it downloads itself later if not.
choice /c YN /n /m "  download the balanced model now? [Y/N] "
if errorlevel 2 goto done
"%DEST%\removebg.exe" --warm balanced

:done
echo.
echo   Done.
echo   Right-click any image  ->  Remove Background  ->  Fast / Balanced / HQ
echo   Windows 11 keeps it under "Show more options".
echo   The cut-out lands next to the original as ^<name^>_bgremoved.png
echo.
echo   This folder and the zip can be deleted now.
echo   To undo everything: run uninstall.bat in %DEST%
echo.
pause
