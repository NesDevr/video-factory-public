"""Tests for concurrent-stage HTML log rendering."""

from pathlib import Path
import re

from tools.log_viewer import generate_log_html


def _stage_group(html: str, stage_name: str) -> tuple[str, str]:
    pattern = re.compile(
        rf'<div class="stage-group"><div class="stage-header"><span class="arrow">▼</span>'
        rf'<span class="name">{stage_name}</span><span class="dur">(.*?)</span></div>'
        rf'<div class="stage-body">(.*?)</div></div>',
        re.DOTALL,
    )
    match = pattern.search(html)
    assert match, f"missing stage group for {stage_name}"
    return match.group(1), match.group(2)


def test_generate_log_html_groups_parallel_stages_correctly(tmp_path: Path) -> None:
    log_path = tmp_path / "pipeline.log"
    output_path = tmp_path / "pipeline.html"
    log_path.write_text(
        "\n".join(
            [
                "19:31:25 | INFO    | [stage] image_source started",
                "19:31:25 | INFO    | [stage] audio_source started",
                "19:31:26 | INFO    | Voice variation 0: Warm, trustworthy male narrator",
                "19:31:26 | INFO    | Sourcing illustration for section_001_02.jpg",
                "19:31:26 | INFO    | [ai_gen] generate_image_gemini model=gemini-3.1-flash-image-preview prompt=\"Medical illustration...\" (405 chars)",
                "19:31:26 | INFO    | [tts] generate_speech model=gemini-2.5-flash-tts voice=Charon lang=en-US text=72 words",
                "19:31:29 | INFO    | B-roll prepared: section_001_01.mp4 (9.7s)",
                "19:31:59 | INFO    | STT transcribed 72 words in 1 chunk(s)",
                "19:31:59 | INFO    | Section s001: 72 words, 29.7s (offset 0.0s)",
                "19:32:06 | INFO    | [stage] audio_source completed in 50.8s",
                "19:32:10 | INFO    | [gemini] review_with_vision model=gemini-3-flash-preview images=1 prompt=\"Review these images sourced...\"",
                "19:32:15 | INFO    | [gemini] review_with_vision done — 5.8s, 2037 in + 110 out tokens",
                "19:32:16 | INFO    | [stage] image_source completed in 100.8s",
                "19:32:16 | INFO    | [validate] raw_images: PASS",
                "19:32:16 | INFO    | [validate] audio: PASS",
                "19:33:08 | INFO    | [stage] thumbnail started",
                "19:33:08 | INFO    | [stage] render_sections started",
                "19:33:08 | INFO    | Thumbnail strategy: demo_thumbnail",
                "19:33:08 | INFO    | Rendering 2 sections (concurrency=2)",
                "19:33:08 | INFO    | [gemini] generate_image_gemini model=gemini-3-pro-image-preview ref=yes prompt=\"Generate the final 1280x720 YouTube thumbnail image...\"",
                "19:33:34 | INFO    | [gemini] generate_image_gemini done — 26.3s → thumbnail.png",
                "19:33:43 | WARNING | [thumbnail_review] REJECTED attempt 1: Extra text in thumbnail",
                "19:35:17 | INFO    | Section s002: 3 slots [video, InfoSlide, zoom_focus] (30.7s)",
                "19:35:22 | INFO    | [stage] render_sections completed in 134.0s",
                "19:35:22 | INFO    | [stage] assemble started",
                "19:35:22 | INFO    | [validate] ready_images: PASS",
                "19:35:22 | INFO    | [validate] audio: PASS",
                "19:35:22 | INFO    | Per-section transitions from script",
                "19:35:29 | INFO    | Video assembled: out.mp4",
                "19:35:31 | INFO    | [stage] assemble completed in 9.2s",
            ]
        ),
        encoding="utf-8",
    )

    generate_log_html(log_path, output_path)
    html = output_path.read_text(encoding="utf-8")

    image_dur, image_body = _stage_group(html, "image_source")
    assert "100.8s" in image_dur
    assert "Sourcing illustration for section_001_02.jpg" in image_body
    assert "B-roll prepared: section_001_01.mp4" in image_body
    assert "Review these images sourced" in image_body
    assert "raw_images: PASS" in image_body
    assert "Voice variation 0" not in image_body

    audio_dur, audio_body = _stage_group(html, "audio_source")
    assert "50.8s" in audio_dur
    assert "Voice variation 0: Warm, trustworthy male narrator" in audio_body
    assert "generate_speech model=gemini-2.5-flash-tts" in audio_body
    assert "STT transcribed 72 words in 1 chunk(s)" in audio_body
    assert "Section s001: 72 words" in audio_body
    assert "offset" in audio_body
    assert "audio: PASS" in audio_body
    assert "Sourcing illustration for section_001_02.jpg" not in audio_body

    thumb_dur, thumb_body = _stage_group(html, "thumbnail")
    assert thumb_dur == ""
    assert "Thumbnail strategy: demo_thumbnail" in thumb_body
    assert "generate_image_gemini model=gemini-3-pro-image-preview" in thumb_body
    assert "thumbnail.png" in thumb_body
    assert "REJECTED attempt 1: Extra text in thumbnail" in thumb_body
    assert "Rendering 2 sections" not in thumb_body

    render_dur, render_body = _stage_group(html, "render_sections")
    assert "134.0s" in render_dur
    assert "Rendering 2 sections (concurrency=2)" in render_body
    assert "Section s002: 3 slots [video, InfoSlide, zoom_focus]" in render_body
    assert "generate_image_gemini model=gemini-3-pro-image-preview" not in render_body

    assemble_dur, assemble_body = _stage_group(html, "assemble")
    assert "9.2s" in assemble_dur
    assert "ready_images: PASS" in assemble_body
    assert "audio: PASS" in assemble_body
    assert "Per-section transitions from script" in assemble_body
    assert "Video assembled: out.mp4" in assemble_body


def test_generate_log_html_renders_trace_links(tmp_path: Path) -> None:
    log_path = tmp_path / "pipeline.log"
    output_path = tmp_path / "pipeline.html"
    log_path.write_text(
        "\n".join(
            [
                "19:31:25 | INFO    | [stage] script started",
                "19:31:26 | INFO    | [gemini] generate_text model=gemini-3-pro prompt=\"Write script...\" (1200 chars) trace=pipeline.html#0002_script_generate",
                "19:31:30 | INFO    | [gemini] generate_text done — 4.2s, 1840 in + 3200 out tokens, 15000 chars trace=pipeline.html#0002_script_generate",
                "19:31:31 | INFO    | [stage] script completed in 6.0s",
            ]
        ),
        encoding="utf-8",
    )

    generate_log_html(log_path, output_path)
    html = output_path.read_text(encoding="utf-8")

    assert 'href="pipeline.html#0002_script_generate"' in html
    assert '>pipeline.html#0002_script_generate</a>' in html


def test_generate_log_html_embeds_workspace_artifacts(tmp_path: Path) -> None:
    log_path = tmp_path / "pipeline.log"
    output_path = tmp_path / "pipeline.html"
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    log_path.write_text(
        "19:31:25 | INFO    | [stage] planning started\n"
        "19:31:26 | INFO    | [gemini] generate_text model=gemini-3-pro prompt=\"Plan...\" (100 chars) trace=pipeline.html#0001_planning_topic_selection\n"
        "19:31:27 | INFO    | [stage] planning completed in 2.0s\n",
        encoding="utf-8",
    )
    (tmp_path / "checkpoint.json").write_text('{"current_stage":"planning","last_error":null}', encoding="utf-8")
    (tmp_path / "plan.json").write_text('{"topic":"Test topic","video_type":"listicle"}', encoding="utf-8")
    (reports_dir / "cost_estimate.json").write_text('{"total_cost_usd":0.12}', encoding="utf-8")
    (reports_dir / "ai_trace_report.json").write_text(
        """
        {
          "run_id": "vf_test",
          "channel": "test",
          "generated_at": "2026-04-16T02:00:00",
          "traces": [
            {
              "trace_id": "0001_planning_topic_selection",
              "stage": "planning",
              "operation": "planning_topic_selection",
              "service": "generate_content",
              "model": "gemini-3-pro",
              "started_at": "2026-04-16T02:00:00",
              "duration_seconds": 2.0,
              "status": "ok",
              "request": {"prompt": "Plan prompt"},
              "response": {"text": "{\\"topic\\":\\"Test topic\\"}"}
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    generate_log_html(log_path, output_path)
    html = output_path.read_text(encoding="utf-8")

    assert "Checkpoint" in html
    assert "Test topic" in html
    assert "Cost Estimate" in html
    assert '<details class="artifact-section" id="ai-traces" open>' in html
    assert "AI Traces" in html
    assert '<details class="trace-card" id="0001_planning_topic_selection">' in html
