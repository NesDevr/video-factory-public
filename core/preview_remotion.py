"""Workspace-backed Remotion preview helpers."""

import json
import logging
import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from core.render_sections import (
    REMOTION_DIR,
    REMOTION_PUBLIC,
    _check_remotion_ready,
    _format_subprocess_cmd,
    _remotion_cli_path,
    build_section_composition_plan,
)
from core.utils import ChannelConfig, Script

logger = logging.getLogger("video_factory")

PREVIEW_COMPOSITION_ID = "FullVideoPreview"
PREVIEW_STAGING_RETENTION = 10
PREVIEW_STUDIO_PORT = 3005
PREVIEW_MANIFEST_VERSION_PATH = REMOTION_DIR / "src" / "generated" / "previewManifestVersion.ts"
PREVIEW_MANIFEST_FILENAME = "preview_manifest.json"
PREVIEW_RUN_COMPOSITION_PREFIX = "Run"


def _preview_static_prefix(workspace: Path) -> str:
    return f"_preview/{workspace.name}"


def _copy_preview_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _studio_is_running(port: int = PREVIEW_STUDIO_PORT) -> bool:
    try:
        with urlopen(f"http://localhost:{port}", timeout=0.5):
            return True
    except HTTPError:
        return True
    except (URLError, OSError):
        return False


def _prune_preview_staging(
    preview_root: Path,
    *,
    keep_workspace_names: set[str],
    max_keep: int = PREVIEW_STAGING_RETENTION,
) -> None:
    staging_dirs = [path for path in preview_root.iterdir() if path.is_dir()]
    protected_dirs = [
        path for path in staging_dirs if path.name in keep_workspace_names
    ]
    other_dirs = [
        path for path in staging_dirs if path.name not in keep_workspace_names
    ]
    other_dirs.sort(key=lambda path: path.stat().st_mtime, reverse=True)

    keep_others = max(0, max_keep - len(protected_dirs))
    for staging_dir in other_dirs[keep_others:]:
        shutil.rmtree(staging_dir, ignore_errors=True)


def _stage_preview_audio(
    workspace: Path,
    config: ChannelConfig,
    staging_dir: Path,
    static_prefix: str,
) -> dict[str, Any]:
    audio_dir = workspace / "audio"
    narration_source = audio_dir / "narration_full.wav"
    if not narration_source.exists():
        raise RuntimeError(f"Missing preview narration track: {narration_source}")

    narration_destination = staging_dir / "audio" / narration_source.name
    _copy_preview_file(narration_source, narration_destination)

    background_music_source = audio_dir / "background_music.mp3"
    transition_sfx_source = audio_dir / "transitions.wav"

    background_music_path = None
    if background_music_source.exists():
        background_music_destination = staging_dir / "audio" / background_music_source.name
        _copy_preview_file(background_music_source, background_music_destination)
        background_music_path = (
            f"{static_prefix}/audio/{background_music_source.name}"
        )

    transition_sfx_path = None
    if transition_sfx_source.exists():
        transition_sfx_destination = staging_dir / "audio" / transition_sfx_source.name
        _copy_preview_file(transition_sfx_source, transition_sfx_destination)
        transition_sfx_path = f"{static_prefix}/audio/{transition_sfx_source.name}"

    return {
        "narration_path": f"{static_prefix}/audio/{narration_source.name}",
        "background_music_path": background_music_path,
        "transition_sfx_path": transition_sfx_path,
        "background_music_volume": config.video.background_music_volume,
        "transition_sfx_volume": config.rendering_defaults.sfx_volume,
    }


def build_preview_manifest(
    script: Script,
    config: ChannelConfig,
    workspace: Path,
) -> dict[str, Any]:
    """Build a manifest consumable by the FullVideoPreview Remotion composition."""
    _check_remotion_ready()

    preview_root = REMOTION_PUBLIC / "_preview"
    preview_root.mkdir(parents=True, exist_ok=True)
    staging_dir = preview_root / workspace.name
    shutil.rmtree(staging_dir, ignore_errors=True)
    staging_dir.mkdir(parents=True, exist_ok=True)

    static_prefix = _preview_static_prefix(workspace)
    sections = build_section_composition_plan(
        script,
        config,
        workspace,
        staging_dir=staging_dir,
        static_prefix=static_prefix,
    )
    if len(sections) != len(script.sections):
        raise RuntimeError(
            "Preview manifest generation requires media for every section "
            f"({len(sections)}/{len(script.sections)} built)"
        )

    total_frames = sum(section["duration_frames"] for section in sections)
    total_frames -= sum(
        section["transition_to_next"]["duration_frames"]
        for section in sections
        if section["transition_to_next"] is not None
    )
    if total_frames <= 0:
        raise RuntimeError("Preview manifest produced a non-positive total frame count")

    width, height = config.video.resolution
    manifest = {
        "title": script.title,
        "width": width,
        "height": height,
        "fps": config.video.fps,
        "total_frames": total_frames,
        "static_root": static_prefix,
        "sections": sections,
        "audio": _stage_preview_audio(workspace, config, staging_dir, static_prefix),
    }
    _prune_preview_staging(preview_root, keep_workspace_names={workspace.name})
    return manifest


def write_preview_manifest(
    script: Script,
    config: ChannelConfig,
    workspace: Path,
) -> Path:
    manifest = build_preview_manifest(script, config, workspace)
    payload = json.dumps(manifest, indent=2, ensure_ascii=False)
    manifest_static_path = f"{manifest['static_root']}/{PREVIEW_MANIFEST_FILENAME}"
    manifest_path = REMOTION_PUBLIC / manifest_static_path
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(payload, encoding="utf-8")
    _write_preview_manifest_version(payload, manifest_static_path)
    return manifest_path


def _preview_run_composition_id(workspace_name: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9-]+", "-", workspace_name).strip("-")
    if not sanitized:
        raise RuntimeError(f"Cannot create Remotion composition id for {workspace_name!r}")
    return f"{PREVIEW_RUN_COMPOSITION_PREFIX}-{sanitized}"


def _preview_manifest_payload_version(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _collect_preview_runs(
    *,
    active_manifest_path: Path,
    active_payload: str,
) -> list[dict[str, str]]:
    preview_root = REMOTION_PUBLIC / "_preview"
    if not preview_root.exists():
        return []

    manifest_paths = [
        path / PREVIEW_MANIFEST_FILENAME
        for path in preview_root.iterdir()
        if path.is_dir() and (path / PREVIEW_MANIFEST_FILENAME).exists()
    ]
    manifest_paths.sort(
        key=lambda path: (
            path.resolve() != active_manifest_path.resolve(),
            -path.stat().st_mtime,
        )
    )

    seen_ids: set[str] = set()
    runs: list[dict[str, str]] = []
    for manifest_path in manifest_paths:
        payload = (
            active_payload
            if manifest_path.resolve() == active_manifest_path.resolve()
            else manifest_path.read_text(encoding="utf-8")
        )
        composition_id = _preview_run_composition_id(manifest_path.parent.name)
        if composition_id in seen_ids:
            raise RuntimeError(f"Duplicate Remotion preview composition id: {composition_id}")
        seen_ids.add(composition_id)
        runs.append(
            {
                "compositionId": composition_id,
                "manifestPath": manifest_path.relative_to(REMOTION_PUBLIC).as_posix(),
                "manifestVersion": _preview_manifest_payload_version(payload),
            }
        )
    return runs


def _write_preview_manifest_version(payload: str, manifest_static_path: str) -> None:
    active_manifest_path = REMOTION_PUBLIC / manifest_static_path
    runs = _collect_preview_runs(
        active_manifest_path=active_manifest_path,
        active_payload=payload,
    )
    if not runs:
        raise RuntimeError("No Remotion preview runs found after writing preview manifest")

    PREVIEW_MANIFEST_VERSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    runs_json = json.dumps(runs, indent=2, ensure_ascii=False)
    PREVIEW_MANIFEST_VERSION_PATH.write_text(
        "\n".join([
            "export type PreviewRunManifest = {",
            "  compositionId: string;",
            "  manifestPath: string;",
            "  manifestVersion: string;",
            "};",
            "",
            f"export const PREVIEW_RUNS = {runs_json} satisfies PreviewRunManifest[];",
            "",
        ]),
        encoding="utf-8",
    )


def _build_remotion_studio_cmd() -> list[str]:
    entry_point = REMOTION_DIR / "src" / "index.ts"
    return [
        "node",
        str(_remotion_cli_path()),
        "studio",
        str(entry_point.resolve()),
        "--port",
        str(PREVIEW_STUDIO_PORT),
    ]


def launch_remotion_studio() -> None:
    """Spawn Remotion Studio for the preview manifest without waiting for exit."""
    if _studio_is_running(PREVIEW_STUDIO_PORT):
        logger.info(
            f"Remotion Studio already running on :{PREVIEW_STUDIO_PORT} "
            "— manifest/version rewrite triggers hot reload"
        )
        return

    cmd = _build_remotion_studio_cmd()
    logger.info(f"Remotion preview cmd: {_format_subprocess_cmd(cmd)}")
    logger.info(f"Remotion preview URL: http://localhost:{PREVIEW_STUDIO_PORT}")

    creationflags = 0
    if sys.platform == "win32":
        creationflags = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )

    subprocess.Popen(
        cmd,
        cwd=str(REMOTION_DIR),
        creationflags=creationflags,
    )
