"""把 dist/LyricsSubtitle 的内容打包成安装程序的 payload。"""
from __future__ import annotations

import zipfile
from pathlib import Path

SOURCE = Path("dist/LyricsSubtitle")
TARGET = Path("dist/LyricsSubtitle-payload.zip")


def main() -> int:
    if not (SOURCE / "LyricsSubtitle.exe").is_file():
        raise SystemExit(f"missing app build: {SOURCE / 'LyricsSubtitle.exe'}")
    TARGET.unlink(missing_ok=True)
    with zipfile.ZipFile(TARGET, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(SOURCE.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(SOURCE).as_posix())
    print(f"{TARGET} {TARGET.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
