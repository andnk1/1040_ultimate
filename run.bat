@echo off
cd /d "%~dp0"
rem use the project virtual environment (.venv) when it exists, otherwise the Python on PATH
set PY=python
if exist ".venv\Scripts\python.exe" set PY=".venv\Scripts\python.exe"
rem a virtual environment can lose the way to Tcl/Tk (needed for the file windows): point it at the base Python's copy
set PYHOME=
if exist ".venv\pyvenv.cfg" for /f "tokens=1,* delims== " %%a in ('findstr /b /c:"home" ".venv\pyvenv.cfg"') do set "PYHOME=%%b"
if defined PYHOME if exist "%PYHOME%\tcl\tcl8.6" set "TCL_LIBRARY=%PYHOME%\tcl\tcl8.6"
if defined PYHOME if exist "%PYHOME%\tcl\tk8.6" set "TK_LIBRARY=%PYHOME%\tcl\tk8.6"
echo Using: %PY%
%PY% --version
echo Checking the libraries (the first time after an update this can take a few minutes)...
%PY% -m pip install -q --disable-pip-version-check -r requirements.txt
echo.
echo Starting 1040 Ultimate - open http://127.0.0.1:5067 in the browser if it does not open by itself.
%PY% app.py
echo.
echo The program stopped - the message above says why.
pause
