@echo off
rem MuPDF.js test - double-click this file. It asks for the sample folder, then runs the 3 steps.
cd /d "%~dp0"

rem use the app's Python (.venv) when it exists, otherwise the Python on PATH
set PY=python
if exist "..\..\.venv\Scripts\python.exe" set PY="..\..\.venv\Scripts\python.exe"

where node >nul 2>nul || (echo Node.js is not installed - install it from nodejs.org first. & pause & exit /b)
if not exist "node_modules\mupdf" (echo Downloading MuPDF.js the first time... & call npm install)

echo.
set /p FOLDER=Paste the folder with the masked sample PDFs and press Enter:
set FOLDER=%FOLDER:"=%

echo.
echo === Step 1 of 3: reading with PyMuPDF (today's engine) ===
%PY% 1_read_pymupdf.py "%FOLDER%" || goto :fail
echo.
echo === Step 2 of 3: reading with MuPDF.js (browser engine) ===
node 2_read_mupdfjs.mjs "%FOLDER%" || goto :fail
echo.
echo === Step 3 of 3: comparing ===
%PY% 3_compare.py || goto :fail
echo.
echo The result is also saved in compare_report.txt in this folder.
pause
exit /b

:fail
echo.
echo The test stopped - the message above says why.
pause
