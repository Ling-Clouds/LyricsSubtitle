@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PYINSTALLER_CONFIG_DIR=%CD%\.pyinstaller-cache"

if not exist "bin\ffmpeg.exe" (
    echo [閿欒] 娌℃湁鎵惧埌 bin\ffmpeg.exe銆?    echo 璇蜂娇鐢?LGPL 鐗?FFmpeg shared build锛屾妸 ffmpeg.exe 鍜岄厤濂?DLL 鏀惧埌 bin 鐩綍銆?    echo 鎺ㄨ崘鏉ユ簮锛歨ttps://github.com/BtbN/FFmpeg-Builds 鐨?win64-lgpl-shared 鍖呫€?    pause
    exit /b 1
)
if not exist "bin\avcodec-*.dll" (
    echo [閿欒] bin 鐩綍缂哄皯 ffmpeg 鐨勫叡浜?DLL銆?    echo 璇锋妸 LGPL shared build 鐨?bin 鐩綍涓叏閮?.dll 鍜?ffmpeg.exe 澶嶅埗杩囨潵銆?    pause
    exit /b 1
)

python -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo 姝ｅ湪瀹夎 PyInstaller...
    python -m pip install -r requirements-build.txt
    if errorlevel 1 (
        echo [閿欒] PyInstaller 瀹夎澶辫触銆?        pause
        exit /b 1
    )
)

python -m PyInstaller --noconfirm --clean LyricsSubtitle.spec
if errorlevel 1 (
    echo [閿欒] 鏋勫缓澶辫触銆?    pause
    exit /b 1
)

echo.
echo 鏋勫缓瀹屾垚锛?echo   dist\LyricsSubtitle\LyricsSubtitle.exe
echo 娉ㄦ剰锛氳淇濈暀鏁翠釜 dist\LyricsSubtitle 鏂囦欢澶癸紝涓嶈兘鍙鍒?exe銆?pause
