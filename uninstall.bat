@echo off
setlocal
title Remove BG - uninstall
set "DEST=%LOCALAPPDATA%\RemoveBG"

echo.
echo   Removing the "Remove Background" right-click menu...
if exist "%DEST%\removebg.exe" (
  "%DEST%\removebg.exe" --uninstall
) else (
  for %%E in (jpg jpeg png bmp gif webp tif tiff heic heif avif) do (
    reg delete "HKCU\Software\Classes\SystemFileAssociations\.%%E\shell\RemoveBG" /f >nul 2>&1
  )
  echo   menu removed
)

echo.
echo   The program files are still in:
echo     %DEST%
echo   The downloaded models are in:
echo     %USERPROFILE%\.rembg
echo.
echo   Delete those two folders yourself to reclaim the space.
echo   The models are the big part, 4.6 MB for fast and 176 MB for balanced.
echo.
pause
