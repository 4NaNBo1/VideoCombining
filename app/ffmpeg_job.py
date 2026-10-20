"""单条输出：归一化 → concat → 水印 / 去重 / 压缩。"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.combo import ComboSpec

ProgressFn = Callable[[float, int, str], None]
from app.ffmpeg_util import CmdCancelled, ffmpeg_path, probe_video, run_cmd


class BuildCancelled(Exception):
    """单条输出在编码过程中被用户取消。"""

# (界面标签, libx264 -crf)；数值越大体积越小、画质越低
COMPRESSION_PRESETS: tuple[tuple[str, int], ...] = (
    ("高", 18),
    ("中高", 20),
    ("中", 23),
    ("中低", 25),
    ("低", 28),
)
DEFAULT_COMPRESSION_INDEX = 2


@dataclass
class EncodeSettings:
    resolution: str  # original | 720p | 1080p | 720p_portrait | 1080p_portrait
    crf: int
    out_ext: str
    watermark_path: str | None
    watermark_pos: str  # tl, tr, bl, br, center
    watermark_opacity: float  # 0-1
    dedup_enabled: bool
    watermark_margin_x: int = 10
    watermark_margin_y: int = 10
    watermark_scale: float = 1.0  # 相对原图宽高的倍数


def target_size(settings: EncodeSettings, reference_path: str) -> tuple[int, int] | None:
    landscape = {
        "720p": (1280, 720),
        "1080p": (1920, 1080),
    }
    portrait = {
        "720p_portrait": (720, 1280),
        "1080p_portrait": (1080, 1920),
    }
    if settings.resolution in landscape:
        return landscape[settings.resolution]
    if settings.resolution in portrait:
        return portrait[settings.resolution]
    info = probe_video(reference_path)
    w, h = info.get("width"), info.get("height")
    if w and h:
        return int(w), int(h)
    return 1280, 720


def scale_filter(w: int, h: int) -> str:
    return (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p"
    )


def mpdecimate_filter() -> str:
    # ponytail: 固定 mpdecimate 默认阈值，由滤镜按帧相似度自动丢重复帧
    return "mpdecimate"


def overlay_position(pos: str, margin_x: int = 10, margin_y: int = 10) -> str:
    mx = max(0, int(margin_x))
    my = max(0, int(margin_y))
    mapping = {
        "tl": f"{mx}:{my}",
        "tr": f"W-w-{mx}:{my}",
        "bl": f"{mx}:H-h-{my}",
        "br": f"W-w-{mx}:H-h-{my}",
        "center": "(W-w)/2:(H-h)/2",
    }
    return mapping.get(pos, mapping["br"])


def watermark_video_filter(scale: float, opacity: float) -> str:
    s = max(0.0, min(2.0, float(scale)))
    a = max(0.0, min(1.0, float(opacity)))
    return f"scale=iw*{s}:ih*{s},format=rgba,colorchannelmixer=aa={a}"


def _check_cancel(should_cancel: Callable[[], bool] | None) -> None:
    if should_cancel and should_cancel():
        raise BuildCancelled()


def _failure_detail(cp) -> str:
    stderr = (cp.stderr or "").strip()
    if len(stderr) > 1500:
        stderr = "…（已省略前半段）…\n" + stderr[-1500:]
    return f"ffmpeg 退出码 {cp.returncode}\n{stderr}"


def normalize_segment(
    src: str,
    dst: str,
    w: int,
    h: int,
    *,
    duration: float | None = None,
    log: callable | None = None,
    on_progress: Callable[[float], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> None:
    ff = ffmpeg_path()
    vf = scale_filter(w, h)
    args = [
        ff,
        "-y",
        "-nostdin",
        "-progress",
        "pipe:1",
        "-nostats",
        "-i",
        src,
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        dst,
    ]
    try:
        cp = run_cmd(
            args,
            log=log,
            should_cancel=should_cancel,
            on_progress=on_progress,
            duration=duration,
        )
    except CmdCancelled:
        raise BuildCancelled() from None
    if cp.returncode != 0:
        raise RuntimeError(f"归一化失败 {src}:\n{_failure_detail(cp)}")


def build_output(
    combo: ComboSpec,
    output_path: str,
    settings: EncodeSettings,
    *,
    work_dir: str | None = None,
    log: callable | None = None,
    progress: ProgressFn | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> None:
    segments = combo.segments
    if not segments:
        raise ValueError("组合为空")

    ref = segments[0]
    size = target_size(settings, ref)
    assert size is not None
    w, h = size

    tmp_ctx = tempfile.TemporaryDirectory(prefix="vc_", dir=work_dir)
    tmp = tmp_ctx.name
    norm_files: list[str] = []
    step_total = len(segments) + 2
    duration_cache: dict[str, float | None] = {}

    def duration_of(path: str) -> float | None:
        if path not in duration_cache:
            duration_cache[path] = probe_video(path).get("duration")
        return duration_cache[path]

    try:
        for i, seg in enumerate(segments):
            _check_cancel(should_cancel)
            out = os.path.join(tmp, f"seg_{i:03d}.mp4")

            def seg_progress(fraction: float, *, index: int = i) -> None:
                if progress:
                    progress(
                        index + fraction,
                        step_total,
                        f"归一化片段 {index + 1}/{len(segments)}",
                    )

            normalize_segment(
                seg,
                out,
                w,
                h,
                duration=duration_of(seg),
                log=log,
                on_progress=seg_progress,
                should_cancel=should_cancel,
            )
            norm_files.append(out)
            if progress:
                progress(
                    i + 1,
                    step_total,
                    f"归一化片段 {i + 1}/{len(segments)}",
                )

        list_path = os.path.join(tmp, "concat.txt")
        with open(list_path, "w", encoding="utf-8") as f:
            for p in norm_files:
                esc = p.replace("'", "'\\''")
                f.write(f"file '{esc}'\n")

        _check_cancel(should_cancel)
        concat_out = os.path.join(tmp, "concat.mp4")
        ff = ffmpeg_path()
        try:
            cp = run_cmd(
                [
                    ff,
                    "-y",
                    "-nostdin",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    list_path,
                    "-c",
                    "copy",
                    concat_out,
                ],
                log=log,
                should_cancel=should_cancel,
            )
        except CmdCancelled:
            raise BuildCancelled() from None
        if cp.returncode != 0:
            raise RuntimeError(f"concat 失败:\n{_failure_detail(cp)}")
        if progress:
            progress(len(segments) + 1, step_total, "拼接片段")

        wm = settings.watermark_path
        opacity = max(0.0, min(1.0, settings.watermark_opacity))
        args = [ff, "-y", "-nostdin", "-progress", "pipe:1", "-nostats", "-i", concat_out]
        fc_lines: list[str] = []
        vlabel = "[0:v]"

        if settings.dedup_enabled:
            dedup = mpdecimate_filter()
            fc_lines.append(f"{vlabel}{dedup}[vdedup]")
            vlabel = "[vdedup]"

        if wm and os.path.isfile(wm) and settings.watermark_scale > 0:
            args += ["-i", wm]
            wm_vf = watermark_video_filter(settings.watermark_scale, opacity)
            fc_lines.append(f"[1:v]{wm_vf}[wm]")
            fc_lines.append(
                f"{vlabel}[wm]overlay={overlay_position(settings.watermark_pos, settings.watermark_margin_x, settings.watermark_margin_y)}[vout]"
            )
            maps = ["-map", "[vout]", "-map", "0:a?"]
        elif fc_lines:
            fc_lines.append(f"{vlabel}copy[vout]")
            maps = ["-map", "[vout]", "-map", "0:a?"]
        else:
            maps = ["-map", "0:v", "-map", "0:a?"]

        if fc_lines:
            args += ["-filter_complex", ";".join(fc_lines)] + maps

        ext = settings.out_ext.lstrip(".").lower()
        vcodec = ["-c:v", "libx264", "-preset", "medium", "-crf", str(settings.crf)]
        if ext in ("mp4", "mov"):
            vcodec += ["-pix_fmt", "yuv420p", "-movflags", "+faststart"]
        args += vcodec + ["-c:a", "aac", "-b:a", "128k", output_path]

        _check_cancel(should_cancel)

        def encode_progress(fraction: float) -> None:
            if progress:
                progress(
                    len(segments) + 1 + fraction,
                    step_total,
                    "编码输出",
                )

        try:
            cp = run_cmd(
                args,
                log=log,
                should_cancel=should_cancel,
                on_progress=encode_progress,
                duration=duration_of(concat_out),
            )
        except CmdCancelled:
            raise BuildCancelled() from None
        if cp.returncode != 0:
            raise RuntimeError(f"输出编码失败:\n{_failure_detail(cp)}")
        if progress:
            progress(step_total, step_total, "编码输出")
    finally:
        tmp_ctx.cleanup()


def _self_check_filter() -> None:
    assert "1280:720" in scale_filter(1280, 720)
    assert overlay_position("br") == "W-w-10:H-h-10"
    assert overlay_position("tl", 20, 30) == "20:30"
    assert "scale=iw*0.5" in watermark_video_filter(0.5, 0.7)
    s = EncodeSettings(
        resolution="720p_portrait",
        crf=23,
        out_ext="mp4",
        watermark_path=None,
        watermark_pos="br",
        watermark_opacity=0.7,
        dedup_enabled=False,
    )
    assert target_size(s, "") == (720, 1280)
    assert mpdecimate_filter() == "mpdecimate"
    assert len(COMPRESSION_PRESETS) == 5
    assert COMPRESSION_PRESETS[DEFAULT_COMPRESSION_INDEX][1] == 23


if __name__ == "__main__":
    _self_check_filter()
    print("ffmpeg_job self-check ok")
