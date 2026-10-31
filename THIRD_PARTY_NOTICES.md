# Third-party notices / 第三方组件声明

LyricsSubtitle 的源代码使用 MIT 许可证，见仓库根目录 `LICENSE`。
安装包中附带的第三方组件遵循各自的许可证。以下声明适用于
`LyricsSubtitle.exe`、`LyricsSubtitle-Installer.exe` 及其安装目录中的文件。

## FFmpeg

- 组件：`ffmpeg.exe`、`avcodec-59.dll`、`avdevice-59.dll`、
  `avfilter-8.dll`、`avformat-59.dll`、`avutil-57.dll`、
  `swresample-4.dll`、`swscale-6.dll`
- 版权：Copyright (c) 2000-2022 the FFmpeg developers
- 版本：`N-106957-g27cffd16aa-20220522`（FFmpeg 开发快照，2022-05-22）
- 许可证：GNU Lesser General Public License v3.0（LGPL-3.0）
  该构建配置未启用 `--enable-gpl`，使用 `--enable-version3` 与
  `--enable-shared`；完整构建配置可用 `ffmpeg.exe -version` 查看。
- 来源：
  - FFmpeg 源码对应提交：
    <https://github.com/FFmpeg/FFmpeg/commit/27cffd16aa>
  - 构建脚本（BtbN FFmpeg-Builds，`win64-lgpl-shared`）：
    <https://github.com/BtbN/FFmpeg-Builds>
- 本安装包中的 FFmpeg 文件是未修改的共享库构建；它们位于安装目录的
  `bin` 子目录，用户可以替换为自行编译的兼容版本。
- 许可证全文：`licenses/FFmpeg-LICENSE.txt`

## Qt 6 / PySide6

- 组件：Qt 6.11.0 运行库与 PySide6 6.11.0 Python 绑定
- 版权：Copyright (C) The Qt Company Ltd.
- 许可证：LGPL-3.0（Qt 同时提供 GPLv3 与商业许可）
- 来源：
  - Qt 源码：<https://download.qt.io/official_releases/qt/6.11/>
  - Qt for Python 源码：<https://code.qt.io/cgit/pyside/pyside-setup.git/>
  - PySide6 发布页：<https://download.qt.io/official_releases/QtForPython/>
- 安装包以动态链接方式附带 Qt/PySide6 共享库，用户可以在安装目录中
  替换这些共享库；本项目未修改 Qt/PySide6 源码。
- Qt Multimedia 的 FFmpeg 后端也会在安装目录中附带相应的 FFmpeg 运行库，
  随 Qt/PySide6 一起按 LGPL-3.0 分发。
- 许可证全文：`licenses/LGPL-3.0.txt`

## NumPy

- 版本：1.26.4
- 版权：Copyright (c) 2005-2023 NumPy Developers
- 许可证：BSD 3-Clause
- 来源：<https://github.com/numpy/numpy>
- 许可证全文：`licenses/BSD-3-Clause-NumPy.txt`

## Python

- 版本：Python 3.10.6
- 版权：Copyright (c) Python Software Foundation
- 许可证：Python Software Foundation License 2.0
- 来源：<https://www.python.org/downloads/release/python-3106/>
- 许可证全文：`licenses/Python-LICENSE.txt`

## PyInstaller

- 打包工具：PyInstaller 5.9.0（仅用于构建应用）
- 许可证：GPL-2.0-or-later，附带允许分发专有应用程序的 bootloader 例外
- 来源：<https://pyinstaller.org/>

## 源码获取说明

FFmpeg、Qt/PySide6 等组件的对应源码可从上述上游地址获取。若某个链接
失效，请通过仓库 Issue 联系维护者，我们会提供对应版本的源码获取方式。
本项目的源代码仓库为 <https://github.com/Ling-Clouds/LyricsSubtitle>。
