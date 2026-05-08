"""Stage: Render each script section as a single Remotion SectionComposition.

Replaces both render_scenes and render_images. For each section, gathers all
slot media (images, scene component descriptors, B-roll video), builds
SectionComposition props (slots + transition), and invokes a single Remotion
render per section.

Output: workspace/videos/sections/section_NNN.mp4  (one per section)
"""

import asyncio
import hashlib
import json
import logging
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from core.utils import (
    Script,
    ScriptSection,
    ChannelConfig,
    RenderingDefaults,
    compute_sub_durations,
    minimum_visual_slots_for_duration,
)
from settings import PROJECT_ROOT
from settings import settings

logger = logging.getLogger("video_factory")

REMOTION_DIR = Path(settings.remotion_project_path)
REMOTION_PUBLIC = REMOTION_DIR / "public"
_SHELL = sys.platform == "win32"

PRESETS = ["parallax", "drift", "zoom_focus"]
DIRECTIONS = ["left", "right", "up", "down"]
_SECTION_CACHE_DURATION_TOLERANCE_SECONDS = 0.1
_WINDOWS_REMOTION_CHROME_MODE = "chrome-for-testing"
_WINDOWS_REMOTION_GL = "angle"
_DEFAULT_REMOTION_GL = "vulkan"
_WINDOWS_GPU_REQUIRED_STATUSES = {
    "Canvas": "Hardware accelerated",
    "Compositing": "Hardware accelerated",
    "Rasterization": "Hardware accelerated",
    "WebGL": "Hardware accelerated",
    "OpenGL": "Enabled",
}
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")


def _probe_video_duration(path: Path) -> float:
    """Get actual duration of a video file via ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning(f"ffprobe failed for {path.name}, using scheduled duration")
        return 0.0
    return float(result.stdout.strip())


# Alias for subtitle suppression — same as component types
from core.utils import VisualSlot as _VS

# Map unified visual type → Remotion component name
_VISUAL_TO_COMPONENT = {
    "bar_chart": "AnimatedBarChart",
    "line_chart": "AnimatedLineChart",
    "donut_gauge": "DonutGauge",
    "comparison_bars": "ComparisonBars",
    "info_card": "InfoCard",
    "info_slide": "InfoSlide",
    "text_only_slide": "TextOnlySlide",
    "fact_highlight": "FactHighlight",
    "title_card": "TitleCard",
    "title_banner": "TitleBanner",
    "subscribe_cta": "SubscribeCTA",
}
_BACKDROP_FIGURE_COMPONENTS = _VS.BACKDROP_FIGURE_TYPES



# ── Remotion helpers (moved from render_scenes.py) ──────────────

def _check_remotion_ready() -> None:
    """Verify Node.js and Remotion project are available."""
    result = subprocess.run(
        ["node", "--version"], capture_output=True, text=True, shell=_SHELL,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Node.js is required for Remotion rendering. "
            "Install from https://nodejs.org/"
        )
    if not (REMOTION_DIR / "node_modules").exists():
        raise RuntimeError(
            f"Remotion dependencies not installed. Run:\n"
            f"  cd {REMOTION_DIR}\n"
            f"  npm install"
        )
    if not _remotion_cli_path().exists():
        raise RuntimeError(
            f"Remotion CLI not found. Run:\n"
            f"  cd {REMOTION_DIR}\n"
            f"  npm install"
        )
    if not _remotion_babel_parser_path().exists():
        raise RuntimeError(
            f"Remotion Studio dependency @babel/parser not found. Run:\n"
            f"  cd {REMOTION_DIR}\n"
            f"  npm install"
        )


def _format_subprocess_cmd(cmd: list[str]) -> str:
    """Format a subprocess command for logging / shell execution."""
    if sys.platform == "win32":
        return subprocess.list2cmdline(cmd)
    return shlex.join(cmd)


def _stage_static_asset(
    source: Path,
    staging_dir: Path,
    static_prefix: str,
    target_name: str,
) -> str:
    """Copy an asset into Remotion public/ and return the staticFile() path."""
    destination = staging_dir / target_name
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        shutil.copy2(source, destination)
    return f"{static_prefix}/{target_name.replace('\\', '/')}"


def _frame_sequence_pad_length(duration_frames: int) -> int:
    """Return the zero-padding width for a frame sequence."""
    return max(len(str(max(duration_frames - 1, 0))), 1)


def _frame_sequence_extension(image_format: str) -> str:
    """Return the file extension emitted by Remotion for a frame-sequence format."""
    if image_format == "jpeg":
        return "jpeg"
    if image_format == "png":
        return "png"
    raise ValueError(f"Unsupported frame-sequence image format: {image_format}")


def _remotion_cli_path() -> Path:
    return REMOTION_DIR / "node_modules" / "@remotion" / "cli" / "remotion-cli.js"


def _remotion_babel_parser_path() -> Path:
    return REMOTION_DIR / "node_modules" / "@babel" / "parser"


def _build_remotion_gpu_cmd(
    *,
    chrome_mode: str,
    gl_backend: str,
) -> list[str]:
    return [
        "node",
        str(_remotion_cli_path()),
        "gpu",
        "--chrome-mode",
        chrome_mode,
        "--gl",
        gl_backend,
    ]


def _parse_remotion_gpu_output(output: str) -> dict[str, str]:
    """Parse `remotion gpu` output into a feature->status mapping."""
    statuses: dict[str, str] = {}
    for raw_line in output.splitlines():
        line = _ANSI_ESCAPE_RE.sub("", raw_line).strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        statuses[key.strip()] = value.strip()
    return statuses


def _check_windows_gpu_preflight() -> dict[str, str]:
    """Ensure Windows section rendering will use a hardware-accelerated Chromium path."""
    cmd = _build_remotion_gpu_cmd(
        chrome_mode=_WINDOWS_REMOTION_CHROME_MODE,
        gl_backend=_WINDOWS_REMOTION_GL,
    )
    logger.info(
        "Windows Remotion GPU preflight: "
        f"chrome_mode={_WINDOWS_REMOTION_CHROME_MODE}, gl={_WINDOWS_REMOTION_GL}"
    )
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(REMOTION_DIR),
    )
    combined_output = "\n".join(
        part for part in (result.stdout.strip(), result.stderr.strip()) if part
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Windows Remotion GPU preflight failed: "
            + combined_output[-500:]
        )

    statuses = _parse_remotion_gpu_output(combined_output)
    if not statuses:
        raise RuntimeError(
            "Windows Remotion GPU preflight returned no parseable status output"
        )

    failures = []
    for feature, required in _WINDOWS_GPU_REQUIRED_STATUSES.items():
        actual = statuses.get(feature)
        if actual != required:
            failures.append(f"{feature}={actual or 'missing'} (expected {required})")
    if failures:
        raise RuntimeError(
            "Windows Remotion GPU preflight reported software rendering: "
            + "; ".join(failures)
        )

    logger.info(
        "Windows Remotion GPU preflight passed: "
        + ", ".join(f"{feature}={statuses[feature]}" for feature in _WINDOWS_GPU_REQUIRED_STATUSES)
    )
    return statuses


def _expected_section_clip_duration(
    section: ScriptSection,
    xfade_pad_frames: int,
    fps: int,
) -> float:
    target_duration = section.actual_duration_seconds or section.estimated_duration_seconds
    return target_duration + (xfade_pad_frames / fps)


def _validate_max_visual_hold(
    section: ScriptSection,
    sub_durations: list[float],
    *,
    max_seconds: float,
    crossfade: float = 0.3,
) -> None:
    """Fail fast when any visible slot would hold longer than the pacing cap."""
    violations = []
    for idx, duration in enumerate(sub_durations, start=1):
        if duration <= max_seconds:
            continue
        slot = section.non_overlay_slots[idx - 1]
        violations.append((idx, slot.visual, duration))
    if not violations:
        return

    worst_idx, worst_visual, worst_duration = max(violations, key=lambda item: item[2])
    section_duration = section.actual_duration_seconds or section.estimated_duration_seconds
    required_slots = minimum_visual_slots_for_duration(
        section_duration,
        max_seconds,
        crossfade=crossfade,
    )
    raise RuntimeError(
        f"Section {section.id} exceeds the max visual hold of {max_seconds:.1f}s. "
        f"Slot {worst_idx} ({worst_visual}) would stay on screen for {worst_duration:.2f}s "
        f"across a {section_duration:.2f}s section with {len(section.non_overlay_slots)} "
        f"slots. Add more visual slots or split the narration into shorter "
        f"sections (roughly {required_slots}+ evenly paced slots at minimum)."
    )


def _reconcile_slot_frame_budget(
    *,
    section: ScriptSection,
    slots: list[dict[str, Any]],
    frame_error: int,
) -> None:
    if frame_error == 0 or not slots:
        return

    preferred_indices = [
        index for index in range(len(slots) - 1, -1, -1)
        if slots[index].get("type") != "video"
    ]
    fallback_indices = [
        index for index in range(len(slots) - 1, -1, -1)
        if index not in preferred_indices
    ]
    candidate_indices = preferred_indices + fallback_indices

    if frame_error > 0:
        target_index = preferred_indices[0] if preferred_indices else None
        if target_index is None:
            return
        slots[target_index]["durationFrames"] += frame_error
        return

    remaining = -frame_error
    for index in candidate_indices:
        available = max(slots[index]["durationFrames"] - 1, 0)
        if available <= 0:
            continue
        trim = min(available, remaining)
        slots[index]["durationFrames"] -= trim
        remaining -= trim
        if remaining == 0:
            return

    raise RuntimeError(
        f"Section {section.id} slot durations exceed the frame budget by {remaining} frame(s) "
        "even after trimming every slot to the minimum of 1 frame."
    )


def _section_clip_matches_duration(output_path: Path, expected_duration: float) -> bool:
    actual_duration = _probe_video_duration(output_path)
    return (
        actual_duration > 0
        and abs(actual_duration - expected_duration) <= _SECTION_CACHE_DURATION_TOLERANCE_SECONDS
    )


def _build_remotion_render_cmd(
    component: str,
    props_path: Path,
    output_target: Path,
    width: int,
    height: int,
    fps: int,
    duration_frames: int,
    image_sequence: bool,
    sequence_image_format: str,
    sequence_jpeg_quality: int,
) -> list[str]:
    """Build the Remotion CLI command for either video or frame-sequence output."""
    entry_point = str(REMOTION_DIR / "src" / "index.ts")
    cmd = [
        "node", str(_remotion_cli_path()),
        "render",
        entry_point,
        component,
        str(output_target.resolve()),
        "--props", str(props_path.resolve()),
        "--width", str(width),
        "--height", str(height),
        "--fps", str(fps),
    ]
    if image_sequence:
        cmd.extend([
            "--sequence",
            "--image-format", sequence_image_format,
            "--image-sequence-pattern", "frame-[frame].[ext]",
        ])
        if sequence_image_format == "jpeg":
            cmd.extend(["--jpeg-quality", str(sequence_jpeg_quality)])
    else:
        cmd.extend([
            "--codec", "h264",
            "--crf", "18",
            "--hardware-acceleration", "if-possible",
        ])
    if sys.platform == "win32":
        cmd.extend([
            "--chrome-mode", _WINDOWS_REMOTION_CHROME_MODE,
            "--gl", _WINDOWS_REMOTION_GL,
        ])
    else:
        cmd.extend(["--gl", _DEFAULT_REMOTION_GL])
    cmd.extend([
        "--duration", str(duration_frames),
        "--log", "error",
    ])
    return cmd


async def _run_remotion_render(cmd: list[str], cwd: Path) -> None:
    """Run a Remotion CLI command and raise on failure."""
    cmd_str = _format_subprocess_cmd(cmd)
    logger.debug(f"Remotion cmd: {cmd_str}")
    proc = await asyncio.create_subprocess_shell(
        cmd_str,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(cwd),
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        stderr_text = stderr.decode(errors="replace") if stderr else ""
        raise RuntimeError(stderr_text[-500:])


def _build_section_encode_cmd(
    frames_dir: Path,
    output_path: Path,
    fps: int,
    duration_frames: int,
    sequence_image_format: str,
) -> list[str]:
    """Build the FFmpeg NVENC command for a Remotion-rendered frame sequence."""
    pad_length = _frame_sequence_pad_length(duration_frames)
    input_pattern = frames_dir / f"frame-%0{pad_length}d.{_frame_sequence_extension(sequence_image_format)}"
    return [
        settings.ffmpeg_path, "-y",
        "-framerate", str(fps),
        "-start_number", "0",
        "-i", str(input_pattern),
        "-frames:v", str(duration_frames),
        "-c:v", "h264_nvenc",
        "-preset", "p4",
        "-rc", "vbr",
        "-cq", "18",
        "-pix_fmt", "yuv420p",
        "-an",
        str(output_path),
    ]


def _encode_section_frames(
    frames_dir: Path,
    output_path: Path,
    fps: int,
    duration_frames: int,
    sequence_image_format: str,
) -> None:
    """Encode a rendered frame sequence into an H.264 NVENC section clip."""
    cmd = _build_section_encode_cmd(
        frames_dir,
        output_path,
        fps,
        duration_frames,
        sequence_image_format,
    )
    logger.debug(f"Section encode cmd: {_format_subprocess_cmd(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Section encode failed: {result.stderr[-500:]}")


async def _render_remotion_scene(
    component: str,
    props_path: Path,
    output_path: Path,
    width: int,
    height: int,
    fps: int,
    rendering_defaults: RenderingDefaults,
    duration_frames: int = 150,
) -> None:
    """Invoke npx remotion render for a composition."""
    image_sequence = sys.platform != "darwin"
    sequence_image_format = rendering_defaults.frame_sequence_image_format
    sequence_jpeg_quality = rendering_defaults.frame_sequence_jpeg_quality
    if image_sequence:
        frames_dir = output_path.parent / f"{output_path.stem}_frames"
        if frames_dir.exists():
            shutil.rmtree(frames_dir)
        render_target = frames_dir
    else:
        frames_dir = None
        render_target = output_path

    cmd = _build_remotion_render_cmd(
        component=component,
        props_path=props_path,
        output_target=render_target,
        width=width,
        height=height,
        fps=fps,
        duration_frames=duration_frames,
        image_sequence=image_sequence,
        sequence_image_format=sequence_image_format,
        sequence_jpeg_quality=sequence_jpeg_quality,
    )

    try:
        await _run_remotion_render(cmd, REMOTION_DIR)
    except RuntimeError as exc:
        raise RuntimeError(
            f"Remotion render failed for {component}: {str(exc)[-500:]}"
        ) from exc

    if frames_dir is not None:
        _encode_section_frames(
            frames_dir,
            output_path,
            fps,
            duration_frames,
            sequence_image_format,
        )
        shutil.rmtree(frames_dir)


# ── Duration adjustment ──────────────────────────────────────────



def _enforce_component_minimums(
    section: ScriptSection,
    sub_durations: list[float],
    min_seconds: float = 8.0,
    donor_min: float = 3.0,
) -> list[float]:
    """Ensure full-screen component slots (charts, InfoCard, InfoSlide) get at least
    *min_seconds*.

    Steals time proportionally from non-component slots. If there aren't
    enough non-component slots to steal from, clamps to the minimum
    without exceeding the total section duration.
    """
    num_slots = len(sub_durations)
    non_overlay_slots = section.non_overlay_slots
    is_component = []
    for i in range(num_slots):
        slot = non_overlay_slots[i] if i < len(non_overlay_slots) else None
        is_component.append(slot is not None and slot.visual in _VS.COMPONENT_TYPES)

    # Find which component slots are under minimum
    deficit = 0.0
    for i in range(num_slots):
        if is_component[i] and sub_durations[i] < min_seconds:
            deficit += min_seconds - sub_durations[i]

    if deficit <= 0:
        return sub_durations

    # Steal from non-component slots proportionally
    donor_total = sum(
        sub_durations[i] for i in range(num_slots) if not is_component[i]
    )
    stealable = sum(
        max(sub_durations[i] - donor_min, 0) for i in range(num_slots) if not is_component[i]
    )

    if stealable <= 0:
        return sub_durations

    steal_ratio = min(deficit / stealable, 1.0)

    adjusted = list(sub_durations)
    for i in range(num_slots):
        if is_component[i] and adjusted[i] < min_seconds:
            adjusted[i] = min_seconds
        elif not is_component[i]:
            give = max(adjusted[i] - donor_min, 0) * steal_ratio
            adjusted[i] -= give

    return adjusted


# ── Slot building ────────────────────────────────────────────────

def _image_motion_profile(section_id: int, sub_idx: int) -> tuple[str, str]:
    slot_hash = hash((section_id, sub_idx))
    return PRESETS[slot_hash % len(PRESETS)], DIRECTIONS[slot_hash % len(DIRECTIONS)]

def _build_slot(
    slot,
    sub_idx: int,
    duration_frames: int,
    fps: int,
    videos_dir: Path,
    ready_dir: Path,
    data_dir: Path,
    staging_dir: Path,
    config: ChannelConfig,
    section_id: int,
    static_prefix: str = "_sections",
) -> dict | None:
    """Build a single slot dict for the SectionComposition props.

    Returns None if no media is available for this sub-slot.
    """
    file_label = f"section_{section_id:03d}_{sub_idx + 1:02d}"
    component = _VISUAL_TO_COMPONENT.get(slot.visual)

    # 1. Component slots (charts, cards, slides) — rendered inline by Remotion
    if slot.visual in _VS.COMPONENT_TYPES:
        props = dict(slot.props)

        if slot.visual in _BACKDROP_FIGURE_COMPONENTS:
            img_path = None
            for ext in (".jpg", ".png"):
                candidate = ready_dir / f"{file_label}{ext}"
                if candidate.exists():
                    img_path = candidate
                    break
            if not img_path:
                logger.warning(
                    f"No background image for {slot.visual} slot s{section_id}.{sub_idx + 1} — skipping slot"
                )
                return None

            static_name = _stage_static_asset(
                img_path,
                staging_dir,
                static_prefix,
                f"{file_label}{img_path.suffix}",
            )
            preset, direction = _image_motion_profile(section_id, sub_idx)
            return {
                "type": "component",
                "component": "BackdropFigureScene",
                "props": {
                    "background_path": static_name,
                    "animation_preset": preset,
                    "direction": direction,
                    "figure_component": component,
                    "figure_props": props,
                },
                "durationFrames": duration_frames,
            }

        # Chart components: load fetched data series
        if slot.visual in _VS.CHART_TYPES:
            data_file = data_dir / f"{file_label}.json"
            if not data_file.exists():
                data_file = data_dir / f"section_{section_id:03d}.json"
            if data_file.exists():
                props["data"] = json.loads(data_file.read_text(encoding="utf-8"))

        if slot.visual == "text_only_slide" and props.get("variant") != "ai_prompt_preview":
            raise RuntimeError(
                f"TextOnlySlide slot s{section_id}.{sub_idx + 1} is reserved for "
                "internal AI prompt preview only"
            )

        # InfoCard / InfoSlide: wire illustration image if one was sourced
        if slot.visual in {"info_card", "info_slide"}:
            for ext in (".jpg", ".png"):
                img_candidate = ready_dir / f"{file_label}{ext}"
                if img_candidate.exists():
                    props["illustration_url"] = _stage_static_asset(
                        img_candidate,
                        staging_dir,
                        static_prefix,
                        f"{file_label}{img_candidate.suffix}",
                    )
                    break

        if slot.visual == "info_slide" and "illustration_url" not in props:
            raise RuntimeError(
                f"InfoSlide slot s{section_id}.{sub_idx + 1} is missing sourced media; "
                "image-less info_slide/text-only fallback is not allowed"
            )

        return {
            "type": "component",
            "component": component,
            "props": props,
            "durationFrames": duration_frames,
        }

    # 2. B-roll video → "video" slot
    if slot.visual == "b_roll":
        video_path = videos_dir / f"{file_label}.mp4"
        if video_path.exists():
            static_name = _stage_static_asset(
                video_path,
                staging_dir,
                static_prefix,
                f"{file_label}.mp4",
            )
            # Clamp to the real clip duration so Remotion never schedules
            # more frames than the file actually contains.
            real_dur = _probe_video_duration(video_path)
            if real_dur > 0:
                duration_frames = min(duration_frames, int(real_dur * fps))
            return {
                "type": "video",
                "videoPath": static_name,
                "durationFrames": duration_frames,
            }
        # B-roll failed — fall through to image check (fallback frame was extracted)

    # 3. Image slots (google_photo, stock_photo, ai_photo, ai_illustration, or b_roll fallback)
    img_path = None
    for ext in (".jpg", ".png"):
        candidate = ready_dir / f"{file_label}{ext}"
        if candidate.exists():
            img_path = candidate
            break

    if img_path:
        static_name = _stage_static_asset(
            img_path,
            staging_dir,
            static_prefix,
            f"{file_label}{img_path.suffix}",
        )

        preset, direction = _image_motion_profile(section_id, sub_idx)

        return {
            "type": "image",
            "imagePath": static_name,
            "durationFrames": duration_frames,
            "preset": preset,
            "direction": direction,
        }

    logger.warning(f"No media for s{section_id}.{sub_idx + 1} — skipping slot")
    return None

def _select_transition(
    config: ChannelConfig,
    title: str,
    crossfade: float,
    section_transition: str = "",
) -> dict:
    """Pick transition type: per-section LLM value > channel pool hash."""
    if section_transition:
        name = section_transition
        if name == "crossfade":
            name = "fade"
        if name == "cut":
            return {"type": "cut", "durationFrames": 0}
        return {"type": name, "durationFrames": int(crossfade * config.video.fps)}

    pool = config.style.video.get("transition_pool", ["fade"])
    idx = int(hashlib.md5(title.encode()).hexdigest(), 16) % len(pool)
    name = pool[idx]
    if name == "crossfade":
        name = "fade"
    if name == "cut":
        return {"type": "cut", "durationFrames": 0}
    return {"type": name, "durationFrames": int(crossfade * config.video.fps)}


def _default_inter_section_transition(config: ChannelConfig) -> str:
    transition_pool = config.style.video.get("transition_pool", ["fade"])
    default_transition = transition_pool[0]
    return "fade" if default_transition == "crossfade" else default_transition


def _resolve_inter_section_transition(raw_transition: str, default_transition: str) -> str:
    effective = raw_transition or default_transition
    return "fade" if effective == "crossfade" else effective


def _build_inter_section_transition_plan(
    script: Script,
    config: ChannelConfig,
    fps: int,
) -> tuple[dict[int, int], dict[int, dict[str, Any] | None]]:
    """Mirror assembler boundary timing so preview and render stay in sync."""
    inter_xfade_duration = config.video.transition_duration_seconds
    default_transition = _default_inter_section_transition(config)
    sections = sorted(script.sections, key=lambda section: section.id)
    xfade_pad_frames: dict[int, int] = {}
    transitions_to_next: dict[int, dict[str, Any] | None] = {}

    for index, section in enumerate(sections):
        if index == len(sections) - 1:
            xfade_pad_frames[section.id] = 0
            transitions_to_next[section.id] = None
            continue

        next_section = sections[index + 1]
        transition_type = _resolve_inter_section_transition(
            next_section.transition_type,
            default_transition,
        )
        duration_frames = 1 if transition_type == "cut" else int(inter_xfade_duration * fps)
        xfade_pad_frames[section.id] = duration_frames
        transitions_to_next[section.id] = {
            "type": transition_type,
            "duration_frames": duration_frames,
        }

    return xfade_pad_frames, transitions_to_next


def _build_watermark_props(
    config: ChannelConfig,
    staging_dir: Path,
    static_prefix: str,
) -> dict[str, Any] | None:
    wm_cfg = config.style.watermark
    if not wm_cfg.get("enabled"):
        return None

    wm_props: dict[str, Any] = {}
    if wm_cfg.get("text"):
        wm_props["text"] = wm_cfg["text"]
    if wm_cfg.get("logo_path"):
        logo_src = Path(wm_cfg["logo_path"])
        if not logo_src.is_absolute():
            logo_src = PROJECT_ROOT / logo_src
        if logo_src.exists():
            wm_props["logo_path"] = _stage_static_asset(
                logo_src,
                staging_dir,
                static_prefix,
                f"watermark{logo_src.suffix}",
            )
    if wm_cfg.get("opacity"):
        wm_props["opacity"] = wm_cfg["opacity"]
    if wm_cfg.get("position"):
        wm_props["position"] = wm_cfg["position"]
    return wm_props or None


def _build_section_composition_entry(
    *,
    section: ScriptSection,
    config: ChannelConfig,
    videos_dir: Path,
    ready_dir: Path,
    data_dir: Path,
    staging_dir: Path,
    static_prefix: str,
    fps: int,
    transition: dict[str, Any],
    xfade_pad_frames: int,
    transition_to_next: dict[str, Any] | None,
) -> dict[str, Any] | None:
    rd = config.rendering_defaults
    intra_crossfade = rd.intra_slot_crossfade

    num_slots = section.sub_slot_count
    sub_durations = compute_sub_durations(
        section,
        num_slots,
        intra_crossfade,
        max_visual_hold_seconds=rd.max_visual_hold_seconds,
    )
    sub_durations = _enforce_component_minimums(
        section,
        sub_durations,
        min_seconds=rd.component_min_duration,
        donor_min=rd.image_slot_min_duration,
    )
    _validate_max_visual_hold(
        section,
        sub_durations,
        max_seconds=rd.max_visual_hold_seconds,
        crossfade=intra_crossfade,
    )

    slots: list[dict[str, Any]] = []
    slot_origins = []
    for sub_idx, visual_slot in enumerate(section.non_overlay_slots):
        duration_frames = int(sub_durations[sub_idx] * fps)
        built = _build_slot(
            visual_slot,
            sub_idx,
            duration_frames,
            fps,
            videos_dir,
            ready_dir,
            data_dir,
            staging_dir,
            config,
            section_id=section.id,
            static_prefix=static_prefix,
        )
        if built:
            slots.append(built)
            slot_origins.append(visual_slot)

    if not slots:
        logger.warning(f"No media for section {section.id} — skipping")
        return None

    target_duration = section.actual_duration_seconds or section.estimated_duration_seconds
    overlap_frames = transition["durationFrames"] if transition["type"] != "cut" else 0
    total_frames = max(int(target_duration * fps), 1) + xfade_pad_frames

    slot_sum = sum(slot["durationFrames"] for slot in slots)
    if len(slots) > 1:
        slot_sum -= overlap_frames * (len(slots) - 1)
    frame_error = total_frames - slot_sum
    if frame_error != 0:
        _reconcile_slot_frame_budget(
            section=section,
            slots=slots,
            frame_error=frame_error,
        )

    narration_sub = None
    if section.word_timestamps:
        offset = 0.0 if section.id == 1 else section.word_timestamps[0]["start"]
        narration_sub = {
            "word_timestamps": [
                {
                    "word": word["word"],
                    "start": round(word["start"] - offset, 3),
                    "end": round(word["end"] - offset, 3),
                }
                for word in section.word_timestamps
            ],
        }
        if section.highlighted_keywords:
            narration_sub["highlighted_keywords"] = section.highlighted_keywords
        highlight_cfg = config.style.subtitle_highlight
        if highlight_cfg.get("color"):
            narration_sub["highlight_color"] = highlight_cfg["color"]

        suppress_ranges: list[list[int]] = []
        cursor = 0
        for index, slot in enumerate(slots):
            duration = slot["durationFrames"]
            origin = slot_origins[index] if index < len(slot_origins) else None
            if origin and origin.visual in _VS.CHART_TYPES:
                suppress_ranges.append([cursor, cursor + duration])
            cursor += duration - (overlap_frames if index < len(slots) - 1 else 0)

        for index, slot in enumerate(slots):
            origin = slot_origins[index] if index < len(slot_origins) else None
            if origin and origin.visual == "subscribe_cta":
                start = 0
                for earlier_index, earlier_slot in enumerate(slots[:index]):
                    start += earlier_slot["durationFrames"]
                    if earlier_index < len(slots[:index]) - 1:
                        start -= overlap_frames
                suppress_ranges.append([start, start + slot["durationFrames"]])

        if suppress_ranges:
            narration_sub["suppress_frame_ranges"] = suppress_ranges

    section_props: dict[str, Any] = {
        "slots": slots,
        "transition": transition,
    }
    if narration_sub:
        section_props["narrationSubtitle"] = narration_sub

    watermark = _build_watermark_props(config, staging_dir, static_prefix)
    if watermark:
        section_props["watermark"] = watermark

    return {
        "section_id": section.id,
        "duration_frames": total_frames,
        "transition_to_next": transition_to_next,
        "props": section_props,
    }


def build_section_composition_plan(
    script: Script,
    config: ChannelConfig,
    workspace: Path,
    *,
    staging_dir: Path,
    static_prefix: str,
    props_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Build canonical per-section Remotion payloads and stage static assets."""
    videos_dir = workspace / "videos" / "raw"
    ready_dir = workspace / "images" / "ready"
    data_dir = workspace / "data"
    fps = config.video.fps
    transition = _select_transition(
        config,
        script.title,
        config.rendering_defaults.intra_slot_crossfade,
        section_transition=script.intra_transition,
    )
    xfade_pad_frames, transitions_to_next = _build_inter_section_transition_plan(
        script,
        config,
        fps,
    )

    section_entries: list[dict[str, Any]] = []
    for section in sorted(script.sections, key=lambda item: item.id):
        entry = _build_section_composition_entry(
            section=section,
            config=config,
            videos_dir=videos_dir,
            ready_dir=ready_dir,
            data_dir=data_dir,
            staging_dir=staging_dir,
            static_prefix=static_prefix,
            fps=fps,
            transition=transition,
            xfade_pad_frames=xfade_pad_frames.get(section.id, 0),
            transition_to_next=transitions_to_next.get(section.id),
        )
        if entry is None:
            continue

        if props_dir is not None:
            props_path = props_dir / f"section_props_{section.id:03d}.json"
            props_path.write_text(
                json.dumps(entry["props"], indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            entry["props_path"] = props_path

        section_entries.append(entry)

    return section_entries


# ── Main stage ───────────────────────────────────────────────────

async def render_sections(
    script: Script,
    config: ChannelConfig,
    workspace: Path,
) -> dict:
    """Render each section as a single SectionComposition clip.

    Returns a summary dict for reporting.
    """
    _check_remotion_ready()
    if sys.platform == "win32":
        _check_windows_gpu_preflight()

    sections_dir = workspace / "videos" / "sections"
    sections_dir.mkdir(parents=True, exist_ok=True)
    props_dir = workspace / "clips"
    props_dir.mkdir(parents=True, exist_ok=True)

    # Staging area inside Remotion's public/ for staticFile() access
    staging_dir = REMOTION_PUBLIC / "_sections"
    staging_dir.mkdir(parents=True, exist_ok=True)

    w, h = config.video.resolution
    fps = config.video.fps
    rd = config.rendering_defaults
    section_entries = build_section_composition_plan(
        script,
        config,
        workspace,
        staging_dir=staging_dir,
        static_prefix="_sections",
        props_dir=props_dir,
    )
    entries_by_id = {entry["section_id"]: entry for entry in section_entries}

    async def _render_one_section(
        section: ScriptSection,
        sem: asyncio.Semaphore,
    ) -> dict | None:
        """Build props and render a single section. Returns result dict or None on skip."""
        entry = entries_by_id.get(section.id)
        if entry is None:
            return None

        output_path = sections_dir / f"section_{section.id:03d}.mp4"
        xfade_pad_frames = (
            entry["transition_to_next"]["duration_frames"]
            if entry["transition_to_next"]
            else 0
        )
        expected_duration = _expected_section_clip_duration(section, xfade_pad_frames, fps)

        # Skip only when the cached clip still matches the script's audio duration.
        if output_path.exists():
            if _section_clip_matches_duration(output_path, expected_duration):
                logger.info(f"Section clip already exists: {output_path.name}")
                return {"section_id": section.id, "cached": True}
            logger.info(
                "Section clip duration changed; rerendering "
                f"{output_path.name} for {expected_duration:.2f}s"
            )

        slots = entry["props"]["slots"]
        total_frames = entry["duration_frames"]
        props_path = entry["props_path"]

        async with sem:
            await _render_remotion_scene(
                "SectionComposition", props_path, output_path,
                w, h, fps, rd, total_frames,
            )
        slot_summary = ", ".join(
            s.get("preset", s.get("component", "video")) for s in slots
        )
        logger.info(
            f"  Section s{section.id:03d}: {len(slots)} slots "
            f"[{slot_summary}] ({total_frames / fps:.1f}s)"
        )
        return {
            "section_id": section.id,
            "slots": len(slots),
            "duration": round(total_frames / fps, 1),
            "backdrop_figure_slots": sum(
                1 for slot in section.slots
                if slot.visual in _VS.BACKDROP_FIGURE_TYPES
            ),
            "cached": False,
        }

    # ── Launch parallel section renders ─────────────────────────────
    concurrency = rd.render_concurrency
    logger.info(f"Rendering {len(section_entries)} sections (concurrency={concurrency})")
    sem = asyncio.Semaphore(concurrency)
    tasks = [
        _render_one_section(section, sem)
        for section in sorted(script.sections, key=lambda item: item.id)
    ]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    results = []
    failures: list[str] = []
    for res in raw_results:
        if isinstance(res, Exception):
            error_text = str(res)
            logger.error(f"Section render FAILED: {error_text}")
            failures.append(error_text)
        elif res is not None:
            results.append(res)

    # Clean up staging directory
    shutil.rmtree(staging_dir, ignore_errors=True)

    if failures:
        raise RuntimeError(
            f"Section rendering failed for {len(failures)} section(s): {failures[0]}"
        )

    return {"rendered": len(results), "failed": 0, "details": results}
