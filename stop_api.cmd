@echo off
REM ==========================================================================
REM  STOP THE WIDGET API
REM  Land Intelligence Platform - Geocode Spatial Solutions Ltd
REM
REM  Use this when the API is running in a window you can no longer find, or
REM  after changing 06_delivery\.env - the API reads its configuration once,
REM  at startup, so a new GOOGLE_MAPS_KEY or password needs a restart.
REM
REM  Stop, then double-click start_api.cmd.
REM ==========================================================================
title LandIQ - stop API
powershell -ExecutionPolicy Bypass -File "%~dp0\06_delivery\stop_api.ps1"
echo.
pause >nul
