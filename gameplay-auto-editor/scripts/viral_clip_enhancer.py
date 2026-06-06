"""Post-process rendered vertical clips with viral-style motion, audio, and text effects."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

from scripts.clip_cutter import (
    _build_drawtext_filter,
    _caption_line_positions,
    _centered_x_expression,
    _max_chars_for_safe_width,
    format_font_path,
    get_video_duration,
    probe_has_audio,
)
from scripts.moment_validator import is_validated_for_slowmo
from scripts.ass_captions import build_ass_subtitle_path, escape_ass_filter_path
from scripts.render_settings import merge_render_config, resolve_font_path
from scripts.text_utils import sanitize_overlay_text, wrap_overlay_text

logger = logging.getLogger(__name__)

DEFAULT_VIRAL_CONFIG: dict[str, Any] = {
    "enabled": True,
    "always_apply_polish": True,
    "slowmo_enabled": True,
    "slowmo_speed": 0.5,
    "slowmo_source_seconds": 0.45,
    "zoom_enabled": True,
    "zoom_factor": 1.12,
    "zoom_duration": 0.35,
    "audio_boost_db": 3,
    "contrast_boost": 1.1,
    "brightness_boost": 0.03,
    "screen_shake": False,
    "impact_text_enabled": True,
    "burn_captions_when_overlay_missing": True,
    "require_validation_for_slowmo": True,
    "min_validation_score": 45,
    "min_signal_count": 1,
    "sound_effects_enabled": False,
    "sound_effect_volume": 0.35,
    "sound_effect_path": "",
    "styled_ass_captions_enabled": False,
    "ass_karaoke_enabled": False,
}


def merge_viral_config(render_config: dict | None) -> dict[str, Any]:
    merged = dict(DEFAULT_VIRAL_CONFIG)
    cfg = dict(render_config or {})
    viral = dict(cfg.get("viral_enhancements") or {})
    merged.update(viral)
    return merged


def enhance_rendered_clip(clip_path: str | Path, highlight: dict, render_config: dict | None = None) -> bool:
    """Apply viral polish in-place on an already rendered vertical clip."""
    settings = merge_render_config(render_config)
    viral = merge_viral_config(settings)
    clip_path = Path(clip_path)

    if not viral.get("enabled", True):
        logger.info("[Enhancer] Viral polish disabled in config")
        return False
    if not clip_path.exists():
        return False
    if not viral.get("always_apply_polish", True):
        logger.info("[Enhancer] always_apply_polish=false — skipping polish")
        return False

    duration = get_video_duration(clip_path)
    if duration <= 0.8:
        logger.info("[Enhancer] Clip too short for polish (%.2fs)", duration)
        return False

    use_slowmo = bool(viral.get("slowmo_enabled", True)) and is_validated_for_slowmo(highlight, viral)
    burn_captions = bool(
        viral.get("burn_captions_when_overlay_missing", True) and not highlight.get("overlay_applied", True)
    )
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
            use_slowmo=use_slowmo,
            burn_captions=burn_captions,
        )
        temp_output.replace(clip_path)
        highlight["viral_enhanced"] = True
        highlight["viral_slowmo_applied"] = use_slowmo
        highlight["viral_captions_burned"] = burn_captions
        highlight["zoom_applied"] = bool(viral.get("zoom_enabled", True))
        if apply_styled_ass_captions(clip_path, highlight, settings, viral):
            highlight["viral_ass_captions_applied"] = True
        applied = []
        if burn_captions:
            applied.append("hook/caption overlays")
        if viral.get("zoom_enabled", True):
            applied.append("impact zoom")
        if viral.get("impact_text_enabled", True):
            applied.append("impact text")
        applied.append("contrast/audio polish")
        if use_slowmo:
            applied.append("pre-impact slow-mo")
        if highlight.get("viral_sound_effect_applied"):
            applied.append("impact SFX")
        if highlight.get("viral_ass_captions_applied"):
            applied.append("styled ASS captions")
        logger.info("[Enhancer] Applied to %s: %s", clip_path.name, ", ".join(applied))
        return True
    except Exception as exc:  # noqa: BLE001 - never break pipeline
        logger.warning("[Enhancer] Polish failed — keeping original clip: %s", exc)
        temp_output.unlink(missing_ok=True)
        return False


def _impact_time_in_clip(highlight: dict, clip_duration: float) -> float:
    start = float(highlight.get("start", 0))
    timestamp = float(highlight.get("timestamp", start + clip_duration / 2))
    relative = timestamp - start
    return max(0.25, min(relative, max(clip_duration - 0.25, 0.25)))


def _render_enhanced_clip(
    *,
    input_path: Path,
    output_path: Path,
    highlight: dict,
    settings: dict,
    viral: dict,
    clip_duration: float,
    impact_t: float,
    use_slowmo: bool,
    burn_captions: bool,
) -> None:
    has_audio = probe_has_audio(input_path)
    sfx_path = _resolve_sound_effect_path(viral, settings)
    filter_chain = build_viral_filter_chain(
        clip_duration=clip_duration,
        impact_t=impact_t,
        highlight=highlight,
        settings=settings,
        viral=viral,
        include_audio=has_audio,
        use_slowmo=use_slowmo,
        burn_captions=burn_captions,
        sfx_input_index=1 if sfx_path else None,
    )

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
    ]
    if sfx_path:
        command.extend(["-i", str(sfx_path)])
    command.extend(
        [
            "-filter_complex",
            filter_chain,
            "-map",
            "[vout]",
        ]
    )
    if has_audio or sfx_path:
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

    logger.info(
        "[Enhancer] Running viral polish (slowmo=%s captions=%s sfx=%s)",
        use_slowmo,
        burn_captions,
        bool(sfx_path),
    )
    logger.debug("[Enhancer] Filter chain: %s", filter_chain)
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "FFmpeg enhancement failed")
    if not output_path.exists() or output_path.stat().st_size <= 0:
        raise RuntimeError("Enhanced output missing or empty")


def _append_hook_and_caption_filters(
    *,
    filters: list[str],
    highlight: dict,
    settings: dict,
) -> None:
    width = int(settings["width"])
    height = int(settings["height"])
    top_safe = int(settings["top_safe_zone"])
    bottom_safe = int(settings["bottom_safe_zone"])
    side_safe = int(settings["side_safe_zone"])
    hook_font = int(settings["top_hook_font_size"])
    caption_font = int(settings["caption_font_size"])
    box_color = str(settings["text_box_color"])
    box_border = int(settings["text_box_border"])
    font_path = resolve_font_path(settings.get("font_candidates"))

    hook_text = sanitize_overlay_text(highlight.get("hook_text") or "Watch this...")
    caption_lines = highlight.get("caption_lines") or wrap_overlay_text(
        sanitize_overlay_text(highlight.get("caption_text") or highlight.get("summary") or "Gameplay highlight"),
        max_chars=_max_chars_for_safe_width(side_safe, caption_font, int(settings["caption_max_chars"])),
        max_lines=int(settings["caption_max_lines"]),
    )
    hook_lines = wrap_overlay_text(
        hook_text.upper(),
        max_chars=_max_chars_for_safe_width(side_safe, hook_font, int(settings["hook_max_chars"])),
        max_lines=int(settings["hook_max_lines"]),
    )

    hook_y = top_safe
    hook_line_gap = hook_font + 20
    for line in hook_lines:
        filters.append(
            _build_drawtext_filter(
                text=line,
                font_size=hook_font,
                y=hook_y,
                x=_centered_x_expression(),
                font_path=font_path,
                box_color=box_color,
                box_border=box_border,
            )
        )
        hook_y += hook_line_gap

    caption_line_gap = caption_font + 18
    caption_y_anchor = height - bottom_safe
    positions = _caption_line_positions(
        line_count=min(len(caption_lines), int(settings["caption_max_lines"])),
        caption_font=caption_font,
        line_gap=caption_line_gap,
        anchor_y=caption_y_anchor,
    )
    for line, line_y in zip(caption_lines[: int(settings["caption_max_lines"])], positions):
        filters.append(
            _build_drawtext_filter(
                text=line,
                font_size=caption_font,
                y=line_y,
                x=_centered_x_expression(),
                font_path=font_path,
                box_color=box_color,
                box_border=box_border,
            )
        )


def build_viral_filter_chain(
    *,
    clip_duration: float,
    impact_t: float,
    highlight: dict,
    settings: dict,
    viral: dict,
    include_audio: bool,
    use_slowmo: bool,
    burn_captions: bool,
    sfx_input_index: int | None = None,
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
    if slow_end - slow_start < 0.15:
        slow_start = max(0.0, impact_t - 0.25)
        slow_end = min(clip_duration, impact_t)

    if use_slowmo and slow_end > slow_start + 0.08:
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
        slow_start = slow_end = 0.0
        video_chain = "[0:v]setpts=PTS[vcat]"

    zoom_factor = float(viral.get("zoom_factor", 1.12))
    zoom_duration = float(viral.get("zoom_duration", 0.35))
    zoom_end = output_impact + zoom_duration

    contrast = float(viral.get("contrast_boost", 1.1))
    brightness = float(viral.get("brightness_boost", 0.03))
    eq_end = output_impact + 0.5

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

    draw_filters: list[str] = []
    if burn_captions:
        _append_hook_and_caption_filters(filters=draw_filters, highlight=highlight, settings=settings)

    if viral.get("impact_text_enabled", True):
        impact_label = sanitize_overlay_text(str(highlight.get("impact_text") or "INSANE").upper())
        impact_y = height - bottom_safe - caption_font - 20
        font_opt = f"fontfile={format_font_path(font_path)}:" if font_path else ""
        impact_start = output_impact
        impact_end = min(output_impact + 1.4, clip_duration + 2.5)
        draw_filters.append(
            f"drawtext={font_opt}"
            f'text="{impact_label}":fontsize={caption_font}:fontcolor=white:'
            f"box=1:boxcolor={box_color}:boxborderw={box_border}:"
            f"x=(w-text_w)/2:y={impact_y}:"
            f"enable='between(t,{impact_start:.3f},{impact_end:.3f})'"
        )

    if draw_filters:
        video_chain += f";{last_video}{','.join(draw_filters)}[vout]"
    else:
        video_chain += f";{last_video}format=yuv420p[vout]"

    if not include_audio:
        return video_chain

    audio_boost = float(viral.get("audio_boost_db", 3))
    boost_end = output_impact + 0.45
    sfx_volume = float(viral.get("sound_effect_volume", 0.35))
    sfx_delay_ms = max(0, int(output_impact * 1000))

    if use_slowmo and slow_end > slow_start + 0.08:
        audio_chain = (
            f"[0:a]aformat=sample_rates=48000:channel_layouts=stereo,asplit=3[apre][aslow][apost];"
            f"[apre]atrim=0:{slow_start:.3f},asetpts=PTS-STARTPTS[a1];"
            f"[aslow]atrim={slow_start:.3f}:{slow_end:.3f},volume=0[a2];"
            f"[apost]atrim={slow_end:.3f},asetpts=PTS-STARTPTS[a3];"
            f"[a1][a2][a3]concat=n=3:v=0:a=1[acat];"
            f"[acat]volume={audio_boost:.1f}dB:enable='between(t,{output_impact:.3f},{boost_end:.3f})'[aboost]"
        )
    else:
        audio_chain = (
            f"[0:a]aformat=sample_rates=48000:channel_layouts=stereo[acat];"
            f"[acat]volume={audio_boost:.1f}dB:enable='between(t,{output_impact:.3f},{boost_end:.3f})'[aboost]"
        )

    if sfx_input_index is not None:
        highlight["viral_sound_effect_applied"] = True
        audio_chain += (
            f";[{sfx_input_index}:a]volume={sfx_volume:.2f},adelay={sfx_delay_ms}|{sfx_delay_ms}[sfx];"
            f"[aboost][sfx]amix=inputs=2:duration=first:dropout_transition=0[aout]"
        )
    else:
        audio_chain += ";[aboost]anull[aout]"

    return f"{video_chain};{audio_chain}"


def _resolve_sound_effect_path(viral: dict, settings: dict) -> Path | None:
    if not viral.get("sound_effects_enabled", False):
        return None

    candidates: list[Path] = []
    custom = str(viral.get("sound_effect_path") or settings.get("sound_effect_path") or "").strip()
    if custom:
        candidates.append(Path(custom))

    project_root = Path(__file__).resolve().parents[1]
    candidates.extend(
        [
            project_root / "assets" / "sfx" / "impact.mp3",
            project_root / "assets" / "sfx" / "impact.wav",
        ]
    )

    for candidate in candidates:
        if candidate.exists() and candidate.stat().st_size > 0:
            return candidate.resolve()
    return None


def apply_styled_ass_captions(
    clip_path: Path,
    highlight: dict,
    settings: dict,
    viral: dict,
) -> bool:
    """Burn styled ASS subtitles on top of an already polished clip."""
    if not viral.get("styled_ass_captions_enabled", False):
        return False

    duration = get_video_duration(clip_path)
    if duration <= 0.5:
        return False

    karaoke_words = highlight.get("transcript_words") if viral.get("ass_karaoke_enabled", False) else None
    ass_path = build_ass_subtitle_path(
        highlight,
        settings,
        duration,
        karaoke_words=karaoke_words,
    )
    if not ass_path:
        return False

    temp_output = clip_path.with_suffix(".ass.tmp.mp4")
    escaped = escape_ass_filter_path(ass_path)
    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(clip_path),
        "-vf",
        f"subtitles='{escaped}'",
        "-c:v",
        "libx264",
        "-preset",
        str(settings["preset"]),
        "-crf",
        str(settings["video_crf"]),
        "-c:a",
        "copy",
        "-movflags",
        "+faststart",
        str(temp_output),
    ]

    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0 or not temp_output.exists():
            logger.info("[Enhancer] ASS captions skipped: %s", (result.stderr or "").strip())
            return False
        temp_output.replace(clip_path)
        logger.info("[Enhancer] Applied styled ASS captions to %s", clip_path.name)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.info("[Enhancer] ASS captions skipped: %s", exc)
        return False
    finally:
        ass_path.unlink(missing_ok=True)
        if temp_output.exists() and temp_output != clip_path:
            temp_output.unlink(missing_ok=True)
