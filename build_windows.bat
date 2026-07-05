@echo off
chcp 65001 > nul
echo ============================================
echo  CP77 Crash Scanner - Windows Build Script
echo ============================================

echo.
echo [1/5] Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed
    exit /b 1
)

echo.
echo [2/5] Cleaning old dist...
if exist dist\CP77CrashScanner (
    rmdir /s /q dist\CP77CrashScanner
)
if exist dist\CP77CrashScanner_v1.3.0.zip (
    del /q dist\CP77CrashScanner_v1.3.0.zip
)
if exist dist\SHA256SUMS.txt (
    del /q dist\SHA256SUMS.txt
)

echo.
echo [3/5] Building with PyInstaller (onedir, no UPX)...
pyinstaller --noconfirm CP77CrashScanner.spec
if errorlevel 1 (
    echo ERROR: PyInstaller build failed
    exit /b 1
)

echo.
echo [4/5] Generating SHA256SUMS.txt...
powershell -NoProfile -Command ^
  "$root = (Get-Location).Path;" ^
  "Get-ChildItem -Recurse -File 'dist\CP77CrashScanner' | ForEach-Object {" ^
  "  $hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash;" ^
  "  $rel  = $_.FullName.Substring($root.Length + 1);" ^
  "  \"$hash  $rel\"" ^
  "} | Out-File -Encoding utf8 'dist\SHA256SUMS.txt'"
if errorlevel 1 (
    echo ERROR: SHA256 generation failed
    exit /b 1
)

echo.
echo [5/5] Creating release ZIP...
powershell -NoProfile -Command ^
  "$items = @('dist\CP77CrashScanner', 'README.md', 'dist\SHA256SUMS.txt');" ^
  "if (Test-Path 'README_RU.md') { $items += 'README_RU.md' };" ^
  "Compress-Archive -Force -Path $items -DestinationPath 'dist\CP77CrashScanner_v1.3.0.zip'"
if errorlevel 1 (
    echo ERROR: ZIP creation failed
    exit /b 1
)

echo.
echo ============================================
echo  Build complete
echo  EXE:  dist\CP77CrashScanner\CP77CrashScanner.exe
echo  ZIP:  dist\CP77CrashScanner_v1.3.0.zip
echo ============================================
