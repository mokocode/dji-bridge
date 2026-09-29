@echo off
title DJI -^> vJoy Bridge (Wardogs)
echo.
echo  ======================================================
echo    Starting DJI FPV Controller 2 -^> vJoy Bridge...
echo    Keep this window open while playing.
echo  ======================================================
echo.
python "%~dp0bridge.py" %*
pause
