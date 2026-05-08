"""Tests for workspace-backed Remotion preview manifest generation."""

import json
import os
import hashlib
from pathlib import Path

import core.preview_remotion as preview_remotion
from core.render_sections import build_section_composition_plan
from core.utils import ChannelConfig, Script, ScriptSection, VisualSlot


def _minimal_config(*, logo_path: Path | None = None) -> ChannelConfig:
    return ChannelConfig(
        channel_name="test",
        niche={
            "category": "test",
            "focus": "test",
            "audience": "general",
            "content_style": "informative",
        },
        youtube={
            "channel_id": "x",
            "tags": ["t"],
            "title_formats": [{"name": "a", "instruction": "a"}],
            "description_styles": [{"name": "a", "instruction": "a"}],
        },
        thumbnail_strategies=[{"name": "hero", "instruction": "Make a hero thumbnail"}],
        video={
            "fps": 30,
            "resolution": [1280, 720],
            "transition_duration_seconds": 0.8,
            "background_music_volume": 0.25,
        },
        style={
            "subtitle_highlight": {"color": "#FF00AA"},
            "video": {"transition_pool": ["fade", "wipeleft"]},
            "watermark": {
                "enabled": True,
                "logo_path": str(logo_path) if logo_path else "",
                "opacity": 0.4,
                "position": "top_right",
            },
        },
    )


def _build_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "preview-workspace"
    (workspace / "images" / "ready").mkdir(parents=True)
    (workspace / "data").mkdir(parents=True)
    (workspace / "audio").mkdir(parents=True)
    return workspace


def _build_script() -> Script:
    return Script(
        title="Preview Test",
        video_type="listicle",
        sections=[
            ScriptSection(
                id=1,
                narration="First section narration",
                actual_duration_seconds=6.0,
                word_timestamps=[
                    {"word": "First", "start": 0.0, "end": 0.4},
                    {"word": "section", "start": 0.4, "end": 0.8},
                    {"word": "narration", "start": 0.8, "end": 1.4},
                ],
                highlighted_keywords=["section"],
                slots=[
                    VisualSlot(visual="google_photo", prompt="photo", keywords="photo"),
                    VisualSlot(
                        visual="bar_chart",
                        props={"title": "Chart", "bars": [{"label": "A", "value": 1}]},
                    ),
                    VisualSlot(
                        visual="subscribe_cta",
                        prompt="Realistic photo of an older adult smiling in a bright living room.",
                        keywords="older adult smiling living room real photo",
                        props={"cta_text": "Join"},
                    ),
                ],
            ),
            ScriptSection(
                id=2,
                narration="Second section narration",
                actual_duration_seconds=4.0,
                transition_type="cut",
                word_timestamps=[
                    {"word": "Second", "start": 6.0, "end": 6.3},
                    {"word": "section", "start": 6.3, "end": 6.7},
                    {"word": "narration", "start": 6.7, "end": 7.2},
                ],
                slots=[
                    VisualSlot(
                        visual="info_slide",
                        props={"title": "Slide", "text": "Preview details"},
                    ),
                ],
            ),
        ],
    )


def test_build_section_composition_plan_captures_preview_props(tmp_path):
    workspace = _build_workspace(tmp_path)
    logo_path = tmp_path / "watermark.png"
    logo_path.write_bytes(b"logo")

    ready_dir = workspace / "images" / "ready"
    (ready_dir / "section_001_01.png").write_bytes(b"image-one")
    (ready_dir / "section_001_03.png").write_bytes(b"image-three")
    (ready_dir / "section_002_01.png").write_bytes(b"image-two")
    (workspace / "data" / "section_001_02.json").write_text(
        '{"values":[{"date":"2026-01","value":10}]}',
        encoding="utf-8",
    )

    config = _minimal_config(logo_path=logo_path)
    script = _build_script()
    staging_dir = tmp_path / "staging"
    entries = build_section_composition_plan(
        script,
        config,
        workspace,
        staging_dir=staging_dir,
        static_prefix=f"_preview/{workspace.name}",
    )

    assert len(entries) == 2
    assert entries[0]["transition_to_next"] == {"type": "cut", "duration_frames": 1}
    assert entries[0]["props"]["slots"][2]["component"] == "BackdropFigureScene"
    assert entries[0]["props"]["slots"][2]["props"]["figure_component"] == "SubscribeCTA"
    assert entries[0]["props"]["narrationSubtitle"]["highlight_color"] == "#FF00AA"
    assert len(entries[0]["props"]["narrationSubtitle"]["suppress_frame_ranges"]) >= 2
    assert entries[1]["props"]["slots"][0]["component"] == "InfoSlide"
    assert (
        entries[1]["props"]["slots"][0]["props"]["illustration_url"]
        == f"_preview/{workspace.name}/section_002_01.png"
    )
    assert (
        entries[1]["props"]["watermark"]["logo_path"]
        == f"_preview/{workspace.name}/watermark.png"
    )


def test_build_preview_manifest_stages_audio_and_computes_total_frames(monkeypatch, tmp_path):
    workspace = _build_workspace(tmp_path)
    logo_path = tmp_path / "watermark.png"
    logo_path.write_bytes(b"logo")

    ready_dir = workspace / "images" / "ready"
    (ready_dir / "section_001_01.png").write_bytes(b"image-one")
    (ready_dir / "section_001_03.png").write_bytes(b"image-three")
    (ready_dir / "section_002_01.png").write_bytes(b"image-two")
    (workspace / "data" / "section_001_02.json").write_text(
        '{"values":[{"date":"2026-01","value":10}]}',
        encoding="utf-8",
    )
    (workspace / "audio" / "narration_full.wav").write_bytes(b"wav")
    (workspace / "audio" / "background_music.mp3").write_bytes(b"mp3")

    monkeypatch.setattr(preview_remotion, "_check_remotion_ready", lambda: None)
    monkeypatch.setattr(preview_remotion, "REMOTION_PUBLIC", tmp_path / "remotion_public")

    manifest = preview_remotion.build_preview_manifest(
        _build_script(),
        _minimal_config(logo_path=logo_path),
        workspace,
    )

    expected_total = sum(section["duration_frames"] for section in manifest["sections"])
    expected_total -= sum(
        section["transition_to_next"]["duration_frames"]
        for section in manifest["sections"]
        if section["transition_to_next"] is not None
    )

    assert manifest["total_frames"] == expected_total
    assert [section["section_id"] for section in manifest["sections"]] == [1, 2]
    assert manifest["audio"]["narration_path"] == f"_preview/{workspace.name}/audio/narration_full.wav"
    assert manifest["audio"]["background_music_path"] == (
        f"_preview/{workspace.name}/audio/background_music.mp3"
    )
    assert manifest["audio"]["transition_sfx_path"] is None
    assert (
        tmp_path
        / "remotion_public"
        / "_preview"
        / workspace.name
        / "audio"
        / "narration_full.wav"
    ).exists()


def test_build_section_composition_plan_never_emits_negative_slot_frames(tmp_path):
    workspace = _build_workspace(tmp_path)
    logo_path = tmp_path / "watermark.png"
    logo_path.write_bytes(b"logo")

    ready_dir = workspace / "images" / "ready"
    (ready_dir / "section_001_03.png").write_bytes(b"image-three")

    script = Script(
        title="Packed Preview Test",
        video_type="listicle",
        sections=[
            ScriptSection(
                id=1,
                narration="Packed section narration",
                actual_duration_seconds=13.6,
                slots=[
                    VisualSlot(
                        visual="text_only_slide",
                        props={
                            "variant": "ai_prompt_preview",
                            "title": "One",
                            "text": "Model: gemini-test\n\nPrompt:\nFirst instruction",
                        },
                    ),
                    VisualSlot(
                        visual="text_only_slide",
                        props={
                            "variant": "ai_prompt_preview",
                            "title": "Two",
                            "text": "Model: gemini-test\n\nPrompt:\nSecond instruction",
                        },
                    ),
                    VisualSlot(visual="google_photo", prompt="photo", keywords="photo"),
                ],
            ),
        ],
    )

    entries = build_section_composition_plan(
        script,
        _minimal_config(logo_path=logo_path),
        workspace,
        staging_dir=tmp_path / "staging",
        static_prefix=f"_preview/{workspace.name}",
    )

    durations = [slot["durationFrames"] for slot in entries[0]["props"]["slots"]]
    assert all(duration > 0 for duration in durations)


def test_build_preview_manifest_rebuilds_workspace_staging(monkeypatch, tmp_path):
    workspace = _build_workspace(tmp_path)
    logo_path = tmp_path / "watermark.png"
    logo_path.write_bytes(b"logo")

    ready_dir = workspace / "images" / "ready"
    (ready_dir / "section_001_01.png").write_bytes(b"image-one")
    (ready_dir / "section_001_03.png").write_bytes(b"image-three")
    (ready_dir / "section_002_01.png").write_bytes(b"image-two")
    (workspace / "data" / "section_001_02.json").write_text(
        '{"values":[{"date":"2026-01","value":10}]}',
        encoding="utf-8",
    )
    (workspace / "audio" / "narration_full.wav").write_bytes(b"wav")

    monkeypatch.setattr(preview_remotion, "_check_remotion_ready", lambda: None)
    monkeypatch.setattr(preview_remotion, "REMOTION_PUBLIC", tmp_path / "remotion_public")

    script = _build_script()
    config = _minimal_config(logo_path=logo_path)
    preview_remotion.build_preview_manifest(script, config, workspace)

    stale_file = (
        tmp_path / "remotion_public" / "_preview" / workspace.name / "stale.txt"
    )
    stale_file.write_text("stale", encoding="utf-8")

    preview_remotion.build_preview_manifest(script, config, workspace)

    assert not stale_file.exists()


def test_build_preview_manifest_keeps_only_latest_ten_staged_previews(monkeypatch, tmp_path):
    workspace = _build_workspace(tmp_path)
    logo_path = tmp_path / "watermark.png"
    logo_path.write_bytes(b"logo")

    ready_dir = workspace / "images" / "ready"
    (ready_dir / "section_001_01.png").write_bytes(b"image-one")
    (ready_dir / "section_002_01.png").write_bytes(b"image-two")
    (workspace / "data" / "section_001_02.json").write_text(
        '{"values":[{"date":"2026-01","value":10}]}',
        encoding="utf-8",
    )
    (workspace / "audio" / "narration_full.wav").write_bytes(b"wav")

    preview_root = tmp_path / "remotion_public" / "_preview"
    preview_root.mkdir(parents=True)
    for index in range(12):
        old_dir = preview_root / f"old-preview-{index:02d}"
        old_dir.mkdir()
        old_dir.joinpath("marker.txt").write_text("old", encoding="utf-8")
        timestamp = 1_700_000_000 + index
        os.utime(old_dir, (timestamp, timestamp))

    monkeypatch.setattr(preview_remotion, "_check_remotion_ready", lambda: None)
    monkeypatch.setattr(preview_remotion, "REMOTION_PUBLIC", tmp_path / "remotion_public")

    script = _build_script()
    config = _minimal_config(logo_path=logo_path)
    preview_remotion.build_preview_manifest(script, config, workspace)

    remaining = sorted(path.name for path in preview_root.iterdir() if path.is_dir())
    assert workspace.name in remaining
    assert len(remaining) == preview_remotion.PREVIEW_STAGING_RETENTION
    assert "old-preview-00" not in remaining
    assert "old-preview-01" not in remaining
    assert "old-preview-11" in remaining


def test_write_preview_manifest_writes_run_manifest_and_active_pointer(monkeypatch, tmp_path):
    workspace = _build_workspace(tmp_path)
    remotion_public = tmp_path / "remotion_public"
    version_path = tmp_path / "remotion_src" / "generated" / "previewManifestVersion.ts"
    manifest = {
        "title": "Preview Test",
        "width": 1280,
        "height": 720,
        "fps": 30,
        "total_frames": 150,
        "static_root": "_preview/preview-workspace",
        "sections": [{"section_id": 1, "duration_frames": 150, "props": {}}],
        "audio": {
            "narration_path": "_preview/preview-workspace/audio/narration_full.wav",
            "background_music_path": None,
            "transition_sfx_path": None,
            "background_music_volume": 0.25,
            "transition_sfx_volume": 0.15,
        },
    }

    monkeypatch.setattr(preview_remotion, "REMOTION_PUBLIC", remotion_public)
    monkeypatch.setattr(preview_remotion, "PREVIEW_MANIFEST_VERSION_PATH", version_path)
    monkeypatch.setattr(preview_remotion, "build_preview_manifest", lambda *args: manifest)

    manifest_path = preview_remotion.write_preview_manifest(
        _build_script(),
        _minimal_config(),
        workspace,
    )

    payload = json.dumps(manifest, indent=2, ensure_ascii=False)
    expected_manifest_path = (
        remotion_public / "_preview" / "preview-workspace" / "preview_manifest.json"
    )
    assert manifest_path == expected_manifest_path
    assert expected_manifest_path.read_text(encoding="utf-8") == payload
    assert not (workspace / "preview_manifest.json").exists()
    version = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    assert version_path.read_text(encoding="utf-8") == (
        "export type PreviewRunManifest = {\n"
        "  compositionId: string;\n"
        "  manifestPath: string;\n"
        "  manifestVersion: string;\n"
        "};\n"
        "\n"
        "export const PREVIEW_RUNS = [\n"
        "  {\n"
        '    "compositionId": "Run-preview-workspace",\n'
        '    "manifestPath": "_preview/preview-workspace/preview_manifest.json",\n'
        f'    "manifestVersion": "{version}"\n'
        "  }\n"
        "] satisfies PreviewRunManifest[];\n"
    )


def test_launch_remotion_studio_spawns_without_manifest_props(monkeypatch, tmp_path):
    spawned = {}

    monkeypatch.setattr(preview_remotion, "_remotion_cli_path", lambda: Path("remotion-cli.js"))
    monkeypatch.setattr(preview_remotion, "REMOTION_DIR", tmp_path / "remotion")
    monkeypatch.setattr(preview_remotion, "_studio_is_running", lambda port=preview_remotion.PREVIEW_STUDIO_PORT: False)

    def fake_popen(cmd, cwd, creationflags):
        spawned["cmd"] = cmd
        spawned["cwd"] = cwd
        spawned["creationflags"] = creationflags
        return object()

    monkeypatch.setattr(preview_remotion.subprocess, "Popen", fake_popen)

    preview_remotion.launch_remotion_studio()

    assert spawned["cmd"][0] == "node"
    assert spawned["cmd"][2] == "studio"
    assert "--port" in spawned["cmd"]
    assert "--props" not in spawned["cmd"]
    assert "--force-new" not in spawned["cmd"]
    assert str(preview_remotion.PREVIEW_STUDIO_PORT) in spawned["cmd"]


def test_launch_remotion_studio_skips_spawn_when_already_running(monkeypatch):
    spawned = {"count": 0}

    monkeypatch.setattr(preview_remotion, "_studio_is_running", lambda port=preview_remotion.PREVIEW_STUDIO_PORT: True)

    def fake_popen(*args, **kwargs):
        spawned["count"] += 1
        return object()

    monkeypatch.setattr(preview_remotion.subprocess, "Popen", fake_popen)

    preview_remotion.launch_remotion_studio()

    assert spawned["count"] == 0
