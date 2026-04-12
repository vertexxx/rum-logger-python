@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%"

set "APP_NAME=rumlogger_main"
set "DIST_DIR=%SCRIPT_DIR%dist"
set "BUILD_DIR=%SCRIPT_DIR%build"
set "PYTHON_CMD="
set "PYTHON_VERSION="

call :select_python "py -3"
if not defined PYTHON_CMD (
	call :select_python "python"
)

if not defined PYTHON_CMD (
	echo Python 3.11 or newer was not found.
	echo Install Python 3.11+ and ensure either `py` or `python` is available on PATH.
	popd
	pause
	exit /b 1
)

echo Using Python %PYTHON_VERSION% via %PYTHON_CMD%

%PYTHON_CMD% -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
	echo PyInstaller is not installed for the selected Python interpreter.
	echo Install it with: %PYTHON_CMD% -m pip install pyinstaller
	popd
	pause
	exit /b 1
)

if exist "%DIST_DIR%" rmdir /s /q "%DIST_DIR%"
if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"

%PYTHON_CMD% -m PyInstaller ^
	--noconfirm ^
	--clean ^
	--onefile ^
	--windowed ^
	--name "%APP_NAME%" ^
	--distpath "%DIST_DIR%" ^
	--workpath "%BUILD_DIR%" ^
	--specpath "%BUILD_DIR%" ^
	--icon "%SCRIPT_DIR%res\favicon.ico" ^
	--add-data "%SCRIPT_DIR%res;res" ^
	--add-data "%SCRIPT_DIR%www;www" ^
	--add-data "%SCRIPT_DIR%scripts;scripts" ^
	--collect-all customtkinter ^
	--hidden-import can.interface ^
	--hidden-import can.interfaces ^
	--hidden-import can.interfaces.vector ^
	--hidden-import can.interfaces.vector.canlib ^
	--hidden-import can.interfaces.vector.exceptions ^
	--hidden-import can.interfaces.vector.xlclass ^
	--hidden-import can.interfaces.vector.xldefine ^
	--hidden-import can.interfaces.vector.xldriver ^
	--exclude-module PyQt5 ^
	--exclude-module PyQt6 ^
	--exclude-module PySide2 ^
	--exclude-module PySide6 ^
	--exclude-module qtpy ^
	"%SCRIPT_DIR%rumlogger_main.py"

set "BUILD_EXIT_CODE=%ERRORLEVEL%"

if %BUILD_EXIT_CODE% equ 0 (
	echo Build succeeded: "%DIST_DIR%\%APP_NAME%.exe"
) else (
	echo Build failed with exit code %BUILD_EXIT_CODE%.
)

popd
pause
exit /b %BUILD_EXIT_CODE%

:select_python
set "CANDIDATE=%~1"
set "CANDIDATE_VERSION="

for /f "usebackq delims=" %%V in (`%CANDIDATE% -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')" 2^>nul`) do set "CANDIDATE_VERSION=%%V"

if not defined CANDIDATE_VERSION goto :eof

for /f "tokens=1,2 delims=." %%A in ("%CANDIDATE_VERSION%") do (
	if %%A GTR 3 (
		set "PYTHON_CMD=%CANDIDATE%"
		set "PYTHON_VERSION=%CANDIDATE_VERSION%"
		goto :eof
	)
	if %%A EQU 3 if %%B GEQ 11 (
		set "PYTHON_CMD=%CANDIDATE%"
		set "PYTHON_VERSION=%CANDIDATE_VERSION%"
		goto :eof
	)
)

goto :eof