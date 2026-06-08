@echo off
REM ===========================================================
REM  update_FSC_BANK_BS  -  FSC balance sheet auto update
REM  Double-click to run. Works on local AND network (UNC) paths.
REM  NOTE: please CLOSE the target Excel file before running.
REM ===========================================================

REM PUSHD maps a temp drive for UNC paths (\\server\share\...),
REM so this also works when placed on a network folder.
pushd "%~dp0"

echo ===========================================================
echo   FSC-BANK-BS update   (target Excel must be CLOSED)
echo ===========================================================
echo.

python -m fsc_scraper update

echo.
echo ===========================================================
echo   Done. Please review the messages above.
echo ===========================================================

popd
pause
