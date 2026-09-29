@echo off
REM ==========================================================================
REM  RECOVER THE OAK GROVE PLOTS FROM THE CAD DRAWING
REM  Land Intelligence Platform - Geocode Spatial Solutions Ltd
REM
REM  A .cmd rather than a block to paste, for the same reason start_api.cmd
REM  is: pasting several lines into PowerShell has crashed PSReadLine on this
REM  machine twice, and the full venv path avoids the three separate ways
REM  PATH has been wrong on it.
REM
REM    recover_plots.cmd          look only. Writes nothing to the database.
REM    recover_plots.cmd load     load them, and withdraw the thirteen.
REM ==========================================================================
setlocal
set ROOT=%~dp0
set PY=%ROOT%03_etl\venv\Scripts\python.exe
cd /d "%ROOT%05_enrichment"

if not exist "%PY%" (
  echo Cannot find the venv python at:
  echo   %PY%
  exit /b 1
)

if /i "%~1"=="load" goto load

echo.
echo ===== WHAT IS IN THE FILE =================================
"%PY%" kmz_probe.py "sample_parcels\OAK GROVE.kmz"
echo.
echo ===== WHAT COMES OUT OF IT ================================
"%PY%" 04_polygonize_cad.py --dry-run
echo.
echo ==========================================================
echo  Nothing was written.
echo.
echo  Now open 05_enrichment\recovered_OAK_GROVE.kml in Google
echo  Earth Pro, on top of polyline_plots. If the plots sit on
echo  the drawn ones, run:   recover_plots.cmd load
echo ==========================================================
goto end

:load
echo.
"%PY%" 04_polygonize_cad.py --load --retire-stale

:end
endlocal
