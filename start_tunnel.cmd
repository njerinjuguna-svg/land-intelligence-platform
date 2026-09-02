@echo off
REM ==========================================================================
REM  PUT THE WIDGET ON THE PUBLIC INTERNET                   (Stage 0, step 2)
REM  Land Intelligence Platform - Geocode Spatial Solutions Ltd
REM
REM  Double-click this file. start_api.cmd must already be running - this
REM  checks and says so plainly if it is not.
REM
REM  It prints a boxed https://...trycloudflare.com address. That address is
REM  your laptop, reachable by anyone who has it, until you close this window.
REM  Ctrl-C takes it back off the internet.
REM ==========================================================================
title LandIQ - Tunnel
powershell -ExecutionPolicy Bypass -File "%~dp0\06_delivery\run_tunnel.ps1"
echo.
echo The tunnel is closed. Press any key to close this window.
pause >nul
