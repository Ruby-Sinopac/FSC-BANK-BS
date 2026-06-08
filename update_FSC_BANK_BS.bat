@echo off
REM ===========================================================
REM  update_FSC_BANK_BS  -  FSC 資產負債簡表自動更新
REM  雙擊即可執行。會自動切到本檔所在資料夾再執行更新。
REM ===========================================================

REM 切換到這個 .bat 檔所在的資料夾（才能找到 fsc_scraper 與 config.yaml）
cd /d "%~dp0"

echo ===========================================================
echo   FSC-BANK-BS  update
echo ===========================================================
echo.
echo   [!] Please CLOSE the target Excel file before continuing.
echo       (Excel must be closed, otherwise the file is locked.)
echo.
pause

echo.
python -m fsc_scraper update

echo.
echo ===========================================================
echo   Done. Please review the messages above.
echo ===========================================================
pause
