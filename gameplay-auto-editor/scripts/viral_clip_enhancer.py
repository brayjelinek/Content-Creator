"""Post-process rendered vertical clips with viral-style motion, audio, and text effects."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

from scripts.clip_cutter import format_font_path, get_video_duration, probe_has_audio
from scripts.moment_validator import is_validated_highlight
from scripts.render_settings import merge_render_config, resolve_font_path
from scripts.text_utils import sanitize_overlay_text

logger = logging.getLogger(__name__)

DEFAULT_VIRAL_CONFIG: dict[str, Any] = {
    "enabled": True,
    "slowmo_enabled": True,
    "slowmo_speed": 0.5,
    "slowmo_source_seconds": 0.45,
    "zoom_enabled": True,
    "zoom_factor": 1.1,
    "zoom_duration": 0.3,
    "audio_boost_db": 3,
    "contrast_boost": 1.08,
    "brightness_boost": 0.02,
    "screen_shake": False,
    "impact_text_enabled": True,
    "require_validation": True,
    "min_validation_score": 55,
    "min_signal_count": 2,
}


def merge_viral_config(render_config: dict | None) -> dict[str, Any]:
    merged = dict(DEFAULT_VIRAL_CONFIG)
    cfg = dict(render_config or {})
    viral = dict(cfg.get("viral_enhancements") or {})
    merged.update(viral)
    return merged


def enhance_rendered_clip(clip_path: str | Path, highlight: dict, render_config: dict | None = None) -> bool:
    """Apply viral enhancements in-place on an already rendered vertical clip."""
    settings = merge_render_config(render_config)
    viral = merge_viral_config(settings)
    clip_path = Path(clip_path)

    if not viral.get("enabled", True):
        return False
    if not clip_path.exists():
        return False
    if not is_validated_highlight(highlight, viral):
        return False

    duration = get_video_duration(clip_path)
    if duration <= 1.2:
        logger.info("[Enhancer] Clip too short for effects (%.2fs)", duration)
        return False

    impact_t = _impact_time_in_clip(highlight, duration)
    temp_output = clip_path.with_suffix(".viral.tmp.mp4")

    try:
        _render_enhanced_clip(
            input_path=clip_path,
            output_path=temp_output,
            highlight=highlight,
            settings=settings,
            viral=viral,
            clip_duration=duration,
            impact_t=impact_t,
        )
        temp_output.replace(clip_path)
        highlight["viral_enhanced"] = True
        logger.info("[Enhancer] Viral effects applied to %s", clip_path.name)
        return True
    except Exception as exc:  # noqa: BLE001 - never break pipeline
        logger.warning("[Enhancer] Enhancement failed — keeping original clip: %s", exc)
        temp_output.unlink(missing_ok=True)
        return False


def _impact_time_in_clip(highlight: dict, clip_duration: float) -> float:
    start = float(highlight.get("start", 0))
    timestamp = float(highlight.get("timestamp", start + clip_duration / 2))
    relative = timestamp - start
    return max(0.35, min(relative, max(clip_duration - 0.35, 0.35)))


def _render_enhanced_clip(
    *,
    input_path: Path,
    output_path: Path,
    highlight: dict,
    settings: dict,
    viral: dict,
    clip_duration: float,
    impact_t: float,
) -> None:
    has_audio = probe_has_audio(input_path)
    filter_chain = build_viral_filter_chain(
        clip_duration=clip_duration,
        impact_t=impact_t,
        impact_text=str(highlight.get("impact_text") or "INSANE"),
        settings=settings,
        viral=viral,
        include_audio=has_audio,
    )

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-filter_complex",
        filter_chain,
        "-map",
        "[vout]",
    ]
    if has_audio:
        command.extend(["-map", "[aout]", "-c:a", "aac"])
    command.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            str(settings["preset"]),
            "-crf",
            str(settings["video_crf"]),
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )

    logger.info("[Enhancer] Applying viral filter chain")
    logger.debug("[Enhancer] Filter chain: %s", filter_chain)
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "FFmpeg enhancement failed")
    if not output_path.exists() or output_path.stat().st_size <= 0:
        raise RuntimeError("Enhanced output missing or empty")


def build_viral_filter_chain(
    *,
    clip_duration: float,
    impact_t: float,
    impact_text: str,
    settings: dict,
    viral: dict,
    include_audio: bool,
) -> str:
    width = int(settings["width"])
    height = int(settings["height"])
    bottom_safe = int(settings["bottom_safe_zone"])
    caption_font = int(settings.get("impact_font_size", 72))
    font_path = resolve_font_path(settings.get("font_candidates"))
    box_color = str(settings["text_box_color"])
    box_border = int(settings["text_box_border"])

    slow_src = float(viral.get("slowmo_source_seconds", 0.45))
    slow_speed = max(0.25, min(float(viral.get("slowmo_speed", 0.5)), 1.0))
    pts_mult = 1.0 / slow_speed

    slow_start = max(0.0, impact_t - slow_src)
    slow_end = min(clip_duration, impact_t)
    if slow_end - slow_start < 0.2:
        slow_start = max(0.0, impact_t - 0.3)
        slow_end = min(clip_duration, impact_t)

    use_slowmo = bool(viral.get("slowmo_enabled", True)) and slow_end > slow_start + 0.1

    if use_slowmo:
        output_impact = slow_start + ((slow_end - slow_start) * pts_mult)
        video_chain = (
            f"[0:v]split=3[vpre][vslow][vpost];"
            f"[vpre]trim=0:{slow_start:.3f},setpts=PTS-STARTPTS[v1];"
            f"[vslow]trim={slow_start:.3f}:{slow_end:.3f},setpts={pts_mult:.3f}*(PTS-STARTPTS),"
            f"minterpolate=fps=45:mi_mode=mci[v2];"
            f"[vpost]trim={slow_end:.3f}:{clip_duration:.3f},setpts=PTS-STARTPTS[v3];"
            f"[v1][v2][v3]concat=n=3:v=1:a=0[vcat]"
        )
    else:
        output_impact = impact_t
        video_chain = "[0:v]setpts=PTS[vcat]"

    zoom_factor = float(viral.get("zoom_factor", 1.1))
    zoom_duration = float(viral.get("zoom_duration", 0.3))
    zoom_end = output_impact + zoom_duration

    contrast = float(viral.get("contrast_boost", 1.08))
    brightness = float(viral.get("brightness_boost", 0.02))
    eq_end = output_impact + 0.45

    if viral.get("zoom_enabled", True):
        video_chain += (
            f";[vcat]zoompan=z='if(between(in_time\\,{output_impact:.3f}\\,{zoom_end:.3f})\\,{zoom_factor:.3f}\\,1)':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={width}x{height}:fps=30[vzoom]"
        )
        last_video = "[vzoom]"
    else:
        last_video = "[vcat]"

    video_chain += (
        f";{last_video}eq=contrast={contrast:.3f}:brightness={brightness:.3f}:"
        f"enable='between(t,{output_impact:.3f},{eq_end:.3f})'[veq]"
    )
    last_video = "[veq]"

    if viral.get("screen_shake", False):
        shake_end = output_impact + 0.25
        video_chain += (
            f";{last_video}crop={width}:{height}:"
            f"x='if(between(t\\,{output_impact:.3f}\\,{shake_end:.3f})\\,4*sin(40*t)\\,0)':"
            f"y='if(between(t\\,{output_impact:.3f}\\,{shake_end:.3f})\\,4*cos(40*t)\\,0)'[vshake]"
        )
        last_video = "[vshake]"

    if viral.get("impact_text_enabled", True):
        impact_label = sanitize_overlay_text(impact_text.upper())
        impact_y = height - bottom_safe - caption_font - 20
        font_opt = f"fontfile={format_font_path(font_path)}:" if font_path else ""
        impact_start = output_impact
        impact_end = min(output_impact + 1.2, clip_duration + 2.0)
        video_chain += (
            f";{last_video}drawtext={font_opt}"
            f'text="{impact_label}":fontsize={caption_font}:fontcolor=white:'
            f"box=1:boxcolor={box_color}:boxborderw={box_border}:"
            f"x=(w-text_w)/2:y={impact_y}:"
            f"enable='between(t,{impact_start:.3f},{impact_end:.3f})'[vout]"
        )
    else:
        video_chain += f";{last_video}format=yuv420p[vout]"

    if not include_audio:
        return video_chain

    audio_boost = float(viral.get("audio_boost_db", 3))
    boost_end = output_impact + 0.4

    if use_slowmo:
        audio_chain = (
            f"[0:a]aformat=sample_rates=48000:channel_layouts=stereo,asplit=3[apre][aslow][apost];"
            f"[apre]atrim=0:{slow_start:.3f},asetpts=PTS-STARTPTS[a1];"
            f"[aslow]atrim={slow_start:.3f}:{slow_end:.3f},volume=0[a2];"
            f"[apost]atrim={slow_end:.3f},asetpts=PTS-STARTPTS[a3];"
            f"[a1][a2][a3]concat=n=3:v=0:a=1[acat];"
            f"[acat]volume={audio_boost:.1f}dB:enable='between(t,{output_impact:.3f},{boost_end:.3f})'[aout]"
        )
    else:
        audio_chain = (
            f"[0:a]aformat=sample_rates=48000:channel_layouts=stereo[acat];"
            f"[acat]volume={audio_boost:.1f}dB:enable='between(t,{output_impact:.3f},{boost_end:.3f})'[aout]"
        )

    return f"{video_chain};{audio_chain}"
