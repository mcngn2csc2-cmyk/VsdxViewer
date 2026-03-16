@echo off
setlocal
echo ========================================
echo  VsdxViewer -- PyInstaller build
echo ========================================

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install from https://www.python.org/
    pause & exit /b 1
)

:: Install / upgrade dependencies
echo.
echo [1/3] Installing dependencies...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt
if errorlevel 1 ( echo [ERROR] pip install failed. & pause & exit /b 1 )

python -m pip install pyinstaller
if errorlevel 1 ( echo [ERROR] PyInstaller install failed. & pause & exit /b 1 )

:: Clean previous build
echo.
echo [2/3] Cleaning previous build...
if exist build  rmdir /s /q build
if exist dist   rmdir /s /q dist

:: Build
echo.
echo [3/3] Building executable...
pyinstaller VsdxViewer.spec
if errorlevel 1 ( echo [ERROR] Build failed. & pause & exit /b 1 )

echo.
echo ========================================
echo  Done!  Executable: dist\VsdxViewer\VsdxViewer.exe
echo  Distribute the entire dist\VsdxViewer\ folder.
echo ========================================
pause
