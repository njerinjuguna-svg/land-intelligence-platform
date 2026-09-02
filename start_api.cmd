@echo off
REM ==========================================================================
REM  START THE WIDGET API                                    (Stage 0, step 1)
REM  Land Intelligence Platform - Geocode Spatial Solutions Ltd
REM
REM  Double-click this file, or run it from anywhere. It finds everything
REM  relative to itself, so no directory has to be right and nothing has to
REM  be on PATH.
REM
REM  Leave the window open. Ctrl-C stops the API.
REM ==========================================================================
title LandIQ - API
powershell -ExecutionPolicy Bypass -File "%~dp0\06_delivery\run_api.ps1"
echo.
echo The API has stopped. Press any key to close this window.
pause >nul
