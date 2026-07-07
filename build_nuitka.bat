@echo off
chcp 65001 > nul
echo ============================================
echo  CP77 Crash Scanner - Nuitka onedir build
echo ============================================
echo.
echo Nuitka compiles Python to real C code, so the
echo PyInstaller bootloader signature that antiviruses
echo flag is gone. This drastically reduces false positives.
echo.

set /p VERSION=<version.txt
if "%VERSION%"=="" (
    echo ERROR: version.txt is empty
    exit /b 1
)

echo [1/3] Installing pinned build deps...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed
    exit /b 1
)

echo.
echo [2/3] Cleaning old Nuitka output...
if exist dist_nuitka\cp77_crash_scanner.dist (
    rmdir /s /q dist_nuitka\cp77_crash_scanner.dist
)

echo.
echo [3/3] Building standalone (onedir, no onefile)...
python -m nuitka ^
  --standalone ^
  --enable-plugin=tk-inter ^
  --windows-console-mode=disable ^
  --assume-yes-for-downloads ^
  --remove-output ^
  --output-dir=dist_nuitka ^
  --output-filename=CP77CrashScanner.exe ^
  --company-name=dw1rf ^
  --product-name="CP77 Crash Scanner" ^
  --file-version=%VERSION%.0 ^
  --product-version=%VERSION%.0 ^
  --file-description="Cyberpunk 2077 crash log and mod compatibility scanner" ^
  --copyright="Copyright (c) dw1rf" ^
  cp77_crash_scanner.py
if errorlevel 1 (
    echo ERROR: Nuitka build failed
    exit /b 1
)

echo.
echo ============================================
echo  Build complete
echo  Folder: dist_nuitka\cp77_crash_scanner.dist\
echo  EXE:    dist_nuitka\cp77_crash_scanner.dist\CP77CrashScanner.exe
echo.
echo  Distribute the WHOLE .dist folder (zip it),
echo  not just the exe.
echo ============================================
