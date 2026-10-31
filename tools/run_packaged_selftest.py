"""Development helper: run the packaged app's self-test with a timeout."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

exe = Path("dist/LyricsSubtitle/LyricsSubtitle.exe").resolve()
marker = Path(os.environ.get("TEMP", ".")) / "lyrics_subtitle_selftest.txt"
marker.unlink(missing_ok=True)

env = os.environ.copy()
env["PATH"] = r"C:\Windows\System32;C:\Windows"

try:
    proc = subprocess.run(
        [str(exe), "--self-test"],
        cwd=str(Path.cwd()),
        env=env,
        capture_output=True,
        timeout=20,
    )
    print("returncode:", proc.returncode)
    print("stdout:", proc.stdout.decode("utf-8", "replace")[:1000])
    print("stderr:", proc.stderr.decode("utf-8", "replace")[:1000])
except subprocess.TimeoutExpired as exc:
    print("timeout")
    print("stdout:", (exc.stdout or b"").decode("utf-8", "replace")[:1000])
    print("stderr:", (exc.stderr or b"").decode("utf-8", "replace")[:1000])

print("marker exists:", marker.exists())
if marker.exists():
    print(marker.read_text(encoding="utf-8", errors="replace"))
