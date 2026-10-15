"""ffmpeg / ffprobe 路径与探测。"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable


class CmdCancelled(Exception):
    """subprocess 被用户取消终止。"""


def _bundle_bin_dir() -> Path | None:
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        for sub in ("bin", "ffmpeg", "."):
            d = base / sub if sub != "." else base
            if (d / "ffmpeg").exists() or (d / "ffmpeg.exe").exists():
                return d
        exe_dir = Path(sys.executable).parent
        for d in (exe_dir / "bin", exe_dir):
            if (d / "ffmpeg").exists() or (d / "ffmpeg.exe").exists():
                return d
    else:
        root = Path(__file__).resolve().parent.parent / "bin"
        if root.is_dir():
            return root
    return None


def ffmpeg_path() -> str:
    bundle = _bundle_bin_dir()
    if bundle:
        for name in ("ffmpeg", "ffmpeg.exe"):
            p = bundle / name
            if p.is_file():
                return str(p)
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise FileNotFoundError("未找到 ffmpeg，请安装或放置到 bin/ 目录")


def ffprobe_path() -> str:
    bundle = _bundle_bin_dir()
    if bundle:
        for name in ("ffprobe", "ffprobe.exe"):
            p = bundle / name
            if p.is_file():
                return str(p)
    ff = ffmpeg_path()
    sibling = Path(ff).with_name(Path(ff).name.replace("ffmpeg", "ffprobe"))
    if sibling.is_file():
        return str(sibling)
    found = shutil.which("ffprobe")
    if found:
        return found
    return ff  # ponytail: 无 ffprobe 时退回 ffmpeg，由 probe_video 解析 stderr


def run_cmd(
    args: list[str],
    *,
    log: callable | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> subprocess.CompletedProcess:
    line = " ".join(_quote(a) for a in args)
    if log:
        log(line)
    if not should_cancel:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    while True:
        if should_cancel():
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            raise CmdCancelled()
        if proc.poll() is not None:
            break
        time.sleep(0.25)
    stdout, stderr = proc.communicate()
    return subprocess.CompletedProcess(args, proc.returncode or 0, stdout, stderr)


def _quote(s: str) -> str:
    if re.search(r'\s|"', s):
        return f'"{s}"'
    return s


def probe_video(path: str) -> dict:
    probe = ffprobe_path()
    if "ffprobe" in Path(probe).name.lower():
        cp = run_cmd(
            [
                probe,
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_streams",
                "-show_format",
                path,
            ]
        )
        if cp.returncode == 0 and cp.stdout.strip():
            data = json.loads(cp.stdout)
            w = h = None
            for st in data.get("streams", []):
                if st.get("codec_type") == "video":
                    w = st.get("width")
                    h = st.get("height")
                    break
            dur = data.get("format", {}).get("duration")
            return {"width": w, "height": h, "duration": float(dur) if dur else None}

    ff = ffmpeg_path()
    cp = run_cmd([ff, "-hide_banner", "-i", path])
    text = (cp.stderr or "") + (cp.stdout or "")
    m = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", text)
    w, h = (int(m.group(1)), int(m.group(2))) if m else (None, None)
    dm = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", text)
    duration = None
    if dm:
        duration = int(dm.group(1)) * 3600 + int(dm.group(2)) * 60 + float(dm.group(3))
    return {"width": w, "height": h, "duration": duration}


def verify_ffmpeg(log: callable | None = None) -> str:
    exe = ffmpeg_path()
    cp = run_cmd([exe, "-version"], log=log)
    if cp.returncode != 0:
        raise RuntimeError(f"ffmpeg 不可用: {cp.stderr}")
    first = (cp.stdout or cp.stderr or "").splitlines()[0]
    return first
