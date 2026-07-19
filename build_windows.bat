@echo off
REM SPDX-License-Identifier: GPL-3.0-only
REM Copyright (C) 2026 dw1rf
setlocal
chcp 65001 > nul
echo ============================================
echo  CP77 Crash Scanner - Windows release build
echo ============================================

set /p VERSION=<version.txt
if "%VERSION%"=="" (
    echo ERROR: version.txt is empty
    exit /b 1
)

echo [1/5] Running regression tests...
python -m unittest discover -s tests -v
if errorlevel 1 exit /b 1

echo [2/5] Building Nuitka standalone application...
call build_nuitka.bat
if errorlevel 1 exit /b 1

echo [3/5] Preparing package and SHA256SUMS.txt...
if exist dist\CP77CrashScanner rmdir /s /q dist\CP77CrashScanner
mkdir dist\CP77CrashScanner
xcopy /e /i /q /y dist_nuitka\cp77_crash_scanner.dist\* dist\CP77CrashScanner\ > nul
if errorlevel 1 (
    echo ERROR: failed to copy Nuitka output
    exit /b 1
)
copy /y README.md dist\CP77CrashScanner\ > nul
copy /y README_RU.md dist\CP77CrashScanner\ > nul
copy /y LICENSE dist\CP77CrashScanner\ > nul

powershell -NoProfile -Command ^
  "$package = (Resolve-Path 'dist\CP77CrashScanner').Path;" ^
  "Get-ChildItem -Recurse -File $package | Where-Object Name -ne 'SHA256SUMS.txt' | Sort-Object FullName | ForEach-Object {" ^
  "  $hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash;" ^
  "  $relative = $_.FullName.Substring($package.Length + 1);" ^
  "  Write-Output ($hash + '  ' + $relative)" ^
  "} | Set-Content -Encoding utf8 (Join-Path $package 'SHA256SUMS.txt')"
if errorlevel 1 exit /b 1

echo [4/5] Verifying checksums and creating binary ZIP...
if exist dist\CP77CrashScanner_v%VERSION%.zip del /q dist\CP77CrashScanner_v%VERSION%.zip
powershell -NoProfile -Command ^
  "$package = (Resolve-Path 'dist\CP77CrashScanner').Path;" ^
  "foreach ($line in Get-Content (Join-Path $package 'SHA256SUMS.txt')) {" ^
  "  if ($line -notmatch '^([0-9A-F]{64})  (.+)$') { throw ('Malformed checksum: ' + $line) };" ^
  "  $path = Join-Path $package $Matches[2];" ^
  "  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw ('Missing checksum path: ' + $Matches[2]) };" ^
  "  if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $Matches[1]) { throw ('Checksum mismatch: ' + $Matches[2]) }" ^
  "};" ^
  "Compress-Archive -Force -Path 'dist\CP77CrashScanner' -DestinationPath 'dist\CP77CrashScanner_v%VERSION%.zip'"
if errorlevel 1 exit /b 1

echo [5/5] Creating corresponding source ZIP...
if exist dist\CP77CrashScanner_v%VERSION%_source.zip del /q dist\CP77CrashScanner_v%VERSION%_source.zip
powershell -NoProfile -Command ^
  "$sourceItems = @(" ^
  "  'cp77_crash_scanner.py', 'tests\test_scanner.py', 'requirements.txt', 'version.txt'," ^
  "  'file_version_info.txt', 'CP77CrashScanner.spec', 'build_windows.bat'," ^
  "  'build_nuitka.bat', 'README.md', 'README_RU.md', 'LICENSE'," ^
  "  '.github\workflows\build.yml'" ^
  ");" ^
  "Compress-Archive -Force -Path $sourceItems -DestinationPath 'dist\CP77CrashScanner_v%VERSION%_source.zip'"
if errorlevel 1 exit /b 1

echo.
echo ============================================
echo  Build complete
echo  EXE: dist\CP77CrashScanner\CP77CrashScanner.exe
echo  BIN: dist\CP77CrashScanner_v%VERSION%.zip
echo  SRC: dist\CP77CrashScanner_v%VERSION%_source.zip
echo ============================================
endlocal
