@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

if not exist "bin\ffmpeg.exe" (
    where ffmpeg >nul 2>&1
    if errorlevel 1 (
        echo [错误] 没有找到 bin\ffmpeg.exe，系统 PATH 里也没有 ffmpeg。
        echo 请把 ffmpeg.exe 放到 bin\ffmpeg.exe 后重试。
        pause
        exit /b 1
    )
    if not exist "bin" mkdir "bin"
    for /f "delims=" %%I in ('where ffmpeg') do (
        echo 从 PATH 复制 ffmpeg: %%I
        copy /y "%%I" "bin\ffmpeg.exe" >nul
        goto :ffmpeg_ready
    )
)
:ffmpeg_ready

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

python -m PyInstaller --noconfirm --clean LyricsSubtitle.spec
if errorlevel 1 (
    echo [错误] 构建失败。
    pause
    exit /b 1
)

echo.
echo 构建完成：
echo   dist\LyricsSubtitle\LyricsSubtitle.exe
echo 注意：请保留整个 dist\LyricsSubtitle 文件夹，不能只复制 exe。
pause
