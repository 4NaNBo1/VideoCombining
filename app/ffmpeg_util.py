"""ffmpeg / ffprobe 路径与探测。"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable


class CmdCancelled(Exception):
    """subprocess 被用户取消终止。"""


ProgressFraction = Callable[[float], None]


def _hidden_process_kwargs() -> dict:
    """GUI 进程启动控制台程序时，阻止 Windows 新建控制台窗口。"""
    if os.name != "nt":
        return {}
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE
    return {"startupinfo": si, "creationflags": subprocess.CREATE_NO_WINDOW}


def _progress_seconds(line: str) -> float | None:
    """解析 ffmpeg -progress 输出（out_time_us 实为微秒）。"""
    key, sep, value = line.partition("=")
    value = value.strip()
    if not sep or not value or value == "N/A":
        return None
    if key in ("out_time_us", "out_time_ms"):
        try:
            return int(value) / 1_000_000
        except ValueError:
            return None
    if key == "out_time":
        m = re.match(r"(\d+):(\d+):(\d+(?:\.\d+)?)$", value)
        if m:
            return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    return None


class _LineReader:
    """后台读取子进程输出，避免长任务写满管道缓冲区后卡死。"""

    def __init__(self, stream, on_line: Callable[[str], None] | None = None):
        self._stream = stream
        self._on_line = on_line
        self.lines: list[str] = []
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def join(self) -> None:
        self._thread.join()

    def _run(self) -> None:
        try:
            for line in self._stream:
                self.lines.append(line)
                if self._on_line is not None:
                    try:
                        self._on_line(line.rstrip("\r\n"))
                    except Exception:
                        pass
        finally:
            try:
                self._stream.close()
            except Exception:
                pass


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
    on_progress: ProgressFraction | None = None,
    duration: float | None = None,
) -> subprocess.CompletedProcess:
    line = " ".join(_quote(a) for a in args)
    if log:
        log(line)
    hidden = _hidden_process_kwargs()
    if not should_cancel:
        return subprocess.run(
            args,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            **hidden,
        )

    on_stdout: Callable[[str], None] | None = None
    if on_progress is not None and duration and duration > 0:
        last = -1.0

        def on_stdout(text: str) -> None:
            nonlocal last
            seconds = _progress_seconds(text)
            if seconds is None:
                return
            fraction = max(0.0, min(1.0, seconds / duration))
            if fraction != last:
                last = fraction
                on_progress(fraction)

    proc = subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        **hidden,
    )
    out_reader = _LineReader(proc.stdout, on_stdout)
    err_reader = _LineReader(proc.stderr)
    out_reader.start()
    err_reader.start()
    try:
        while proc.poll() is None:
            if should_cancel():
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                raise CmdCancelled()
            time.sleep(0.1)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        out_reader.join()
        err_reader.join()
    return subprocess.CompletedProcess(
        args,
        proc.returncode or 0,
        "".join(out_reader.lines),
        "".join(err_reader.lines),
    )


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
