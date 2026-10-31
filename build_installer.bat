@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PYINSTALLER_CONFIG_DIR=%CD%\.pyinstaller-cache"
set "CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"

if not exist "bin\ffmpeg.exe" (
    echo [错误] 没有找到 bin\ffmpeg.exe。
    echo 请先准备 LGPL 版 FFmpeg shared build，把 ffmpeg.exe 和 DLL 放到 bin。
    pause
    exit /b 1
)
if not exist "bin\avcodec-*.dll" (
    echo [错误] bin 目录缺少 FFmpeg 共享 DLL。
    pause
    exit /b 1
)
if not exist "%CSC%" (
    echo [错误] 找不到 .NET Framework 4.8 C# 编译器：
    echo   %CSC%
    pause
    exit /b 1
)

python -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo 正在安装 PyInstaller...
    python -m pip install -r requirements-build.txt
    if errorlevel 1 (
        echo [错误] PyInstaller 安装失败。
        pause
        exit /b 1
    )
)

echo [1/5] 构建应用...
python -m PyInstaller --noconfirm --clean LyricsSubtitle.spec
if errorlevel 1 goto :failed

echo [2/5] 编译卸载程序...
"%CSC%" /nologo /target:winexe /codepage:65001 /win32icon:"assets\icon.ico" /out:"dist\Uninstall.exe" "installer\Uninstaller.cs" /r:System.dll /r:System.Drawing.dll /r:System.Windows.Forms.dll
if errorlevel 1 goto :failed
copy /y "dist\Uninstall.exe" "dist\LyricsSubtitle\Uninstall.exe" >nul
if errorlevel 1 goto :failed

echo [3/5] 复制许可证...
copy /y "LICENSE" "dist\LyricsSubtitle\LICENSE" >nul
copy /y "THIRD_PARTY_NOTICES.md" "dist\LyricsSubtitle\THIRD_PARTY_NOTICES.md" >nul
if exist "dist\LyricsSubtitle\licenses" rmdir /s /q "dist\LyricsSubtitle\licenses"
xcopy /E /I /Y "licenses" "dist\LyricsSubtitle\licenses" >nul
if errorlevel 1 goto :failed

echo [4/5] 打包安装负载...
python installer\make_payload.py
if errorlevel 1 goto :failed

echo [5/5] 编译安装程序...
"%CSC%" /nologo /target:winexe /codepage:65001 /win32icon:"assets\icon.ico" /out:"dist\LyricsSubtitle-Installer.exe" /resource:"dist\LyricsSubtitle-payload.zip",payload.zip /resource:"LICENSE",license.txt /resource:"THIRD_PARTY_NOTICES.md",notices.txt "installer\Installer.cs" /r:System.dll /r:System.Drawing.dll /r:System.Windows.Forms.dll /r:System.IO.Compression.dll /r:System.IO.Compression.FileSystem.dll
if errorlevel 1 goto :failed

echo.
echo 构建完成：
echo   dist\LyricsSubtitle-Installer.exe
pause
exit /b 0

:failed
echo.
echo [错误] 构建失败。
pause
exit /b 1
