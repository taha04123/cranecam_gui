@echo off
echo Checking FFmpeg filters available on this machine...
echo.
ffmpeg -filters 2>nul | findstr /i "drawtext drawbox"
echo.
echo If drawtext appears above, text overlay is supported.
echo If nothing appears, your build lacks freetype.
echo.
pause
