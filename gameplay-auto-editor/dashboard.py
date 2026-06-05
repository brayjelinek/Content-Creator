"""Streamlit dashboard for uploading gameplay videos and reviewing generated clips."""

from __future__ import annotations

import re
from pathlib import Path
from time import time

import streamlit as st

from scripts.pipeline import PROJECT_ROOT, load_config, run_pipeline


RAW_CLIPS_DIR = PROJECT_ROOT / "raw_clips"
FINAL_CLIPS_DIR = PROJECT_ROOT / "final_clips"


def main() -> None:
    st.set_page_config(page_title="Gameplay Auto Editor", page_icon=":video_game:", layout="wide")

    st.title("Gameplay Auto Editor")
    st.caption("Upload gameplay footage, generate vertical sample clips, review them, and download your favorites.")

    config = load_config()
    sidebar_settings = _sidebar(config)
    uploaded_file = st.file_uploader(
        "Drop or upload a gameplay video",
        type=["mp4", "mov", "mkv", "webm"],
        help="Longer videos take more time because frames must be sampled, analyzed, and rendered.",
    )

    if uploaded_file:
        saved_path = _save_upload(uploaded_file)
        st.success(f"Uploaded: {saved_path.name}")
        st.video(str(saved_path))

        if st.button("Generate sample clips", type="primary", use_container_width=True):
            _run_generation(saved_path, sidebar_settings)

    if "last_report" in st.session_state:
        _show_report(st.session_state["last_report"])
    else:
        _show_existing_clips()


def _sidebar(config: dict) -> dict:
    vision = config.get("vision", {})
    detection = config.get("highlight_detection", {})
    rendering = config.get("rendering", {})

    st.sidebar.header("Clip settings")
    provider = st.sidebar.selectbox(
        "Vision mode",
        ["heuristic", "auto", "openai", "anthropic"],
        index=["heuristic", "auto", "openai", "anthropic"].index(vision.get("provider", "heuristic")),
        help="Use heuristic for free local testing. Use auto/openai/anthropic after API keys are configured.",
    )
    max_clips = st.sidebar.slider("Number of sample clips", 1, 10, int(detection.get("max_clips", 5)))
    min_score = st.sidebar.slider("Minimum highlight score", 0, 100, int(detection.get("min_score", 55)))
    analysis_interval = st.sidebar.slider(
        "Analyze every N seconds",
        1,
        10,
        int(vision.get("analysis_interval_seconds", 3)),
    )
    max_frames = st.sidebar.slider("Max frames to analyze", 4, 80, int(vision.get("max_frames_to_analyze", 24)))
    add_hashtags = st.sidebar.checkbox("Add hashtags to captions", bool(rendering.get("add_hashtags", True)))

    st.sidebar.divider()
    st.sidebar.markdown("**API key status**")
    st.sidebar.write(f"OpenAI key: {'configured' if vision.get('openai_api_key') else 'not set'}")
    st.sidebar.write(f"Anthropic key: {'configured' if vision.get('anthropic_api_key') else 'not set'}")

    return {
        "vision": {
            "provider": provider,
            "analysis_interval_seconds": analysis_interval,
            "max_frames_to_analyze": max_frames,
        },
        "highlight_detection": {
            "max_clips": max_clips,
            "min_score": min_score,
        },
        "rendering": {
            "add_hashtags": add_hashtags,
        },
    }


def _run_generation(video_path: Path, settings: dict) -> None:
    with st.status("Generating clips...", expanded=True) as status:
        st.write("Extracting frames and analyzing highlight moments.")
        try:
            report = run_pipeline(video_path, config_override=settings)
        except Exception as exc:  # noqa: BLE001 - display readable UI errors.
            status.update(label="Generation failed", state="error")
            st.error(str(exc))
            return

        status.update(label="Clips generated", state="complete")
        st.session_state["last_report"] = report
        st.rerun()


def _show_report(report: dict) -> None:
    st.header("Generated sample clips")
    col1, col2, col3 = st.columns(3)
    col1.metric("Clips created", report.get("clips_created", 0))
    col2.metric("Frames analyzed", report.get("frames_analyzed", 0))
    col3.metric("Video length", f"{report.get('duration_seconds', 0)}s")

    for index, clip in enumerate(report.get("clips", []), start=1):
        with st.container(border=True):
            left, right = st.columns([1, 1])
            final_clip = Path(clip["final_clip"])

            with left:
                st.subheader(f"Clip {index}: score {clip.get('score')}/100")
                if final_clip.exists():
                    st.video(str(final_clip))
                else:
                    st.warning("Rendered clip file was not found.")

            with right:
                st.write(f"**Hook:** {clip.get('hook_text', '')}")
                st.write(f"**Caption:** {clip.get('caption_text', '')}")
                st.write(f"**Categories:** {', '.join(clip.get('categories', [])) or 'none'}")
                st.write(f"**Moment:** {clip.get('start')}s to {clip.get('end')}s")
                st.write(f"**Why it was selected:** {clip.get('reason', '')}")

                if final_clip.exists():
                    st.download_button(
                        "Download this clip",
                        data=final_clip.read_bytes(),
                        file_name=final_clip.name,
                        mime="video/mp4",
                        key=f"download_{index}_{final_clip.name}",
                        use_container_width=True,
                    )


def _show_existing_clips() -> None:
    clips = sorted(FINAL_CLIPS_DIR.glob("*_vertical.mp4"), reverse=True)
    if not clips:
        st.info("Upload a video and click Generate sample clips to create your first outputs.")
        return

    st.header("Existing final clips")
    for clip_path in clips[:6]:
        with st.container(border=True):
            st.write(clip_path.name)
            st.video(str(clip_path))


def _save_upload(uploaded_file) -> Path:
    RAW_CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_filename(uploaded_file.name)
    destination = RAW_CLIPS_DIR / f"{int(time())}_{safe_name}"
    destination.write_bytes(uploaded_file.getbuffer())
    return destination


def _safe_filename(filename: str) -> str:
    name = Path(filename).name
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", name).strip("._")
    return cleaned or "gameplay_upload.mp4"


if __name__ == "__main__":
    main()
