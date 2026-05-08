"""Tests for per-run cost tracking and reconciliation."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import clients as fixture_cache
from core import costs
from tools.log_viewer import render_estimate_html
from tools.reconcile_gcp_costs import build_actual_report


def _init_tracker(tmp_path: Path, run_id: str = "vf_test") -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    costs.initialize_cost_tracking(
        workspace=workspace,
        run_id=run_id,
        channel="demo_channel",
    )


def _usage(prompt: int, output: int, cached: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        prompt_token_count=prompt,
        candidates_token_count=output,
        cached_content_token_count=cached,
    )


def test_generate_content_cost_uses_prompt_cached_and_output_tokens(tmp_path):
    _init_tracker(tmp_path)
    try:
        with costs.bound_context(stage="script"):
            costs.record_generate_content_cost(
                model="gemini-3.1-pro-preview",
                usage_metadata=_usage(prompt=1200, output=500, cached=200),
                operation="script_generate",
            )
        report = costs.build_estimate_report(tmp_path / "workspace")
        event = report["events"][0]
        assert round(event["estimated_usd"], 6) == 0.00804
        assert report["summary"]["estimated_usd"] == 0.00804
    finally:
        costs.shutdown_cost_tracking()


def test_tts_cost_uses_audio_output_tokens(tmp_path):
    _init_tracker(tmp_path)
    try:
        with costs.bound_context(stage="audio_source"):
            costs.record_tts_cost(
                model="gemini-2.5-pro-tts",
                prompt_tokens=2000,
                audio_seconds=30.0,
                operation="tts_section_generate",
            )
        report = costs.build_estimate_report(tmp_path / "workspace")
        event = report["events"][0]
        assert event["audio_output_tokens"] == 750
        assert round(event["estimated_usd"], 6) == 0.017
    finally:
        costs.shutdown_cost_tracking()


def test_stt_cost_tracks_billed_minutes(tmp_path):
    _init_tracker(tmp_path)
    try:
        with costs.bound_context(stage="audio_source"):
            costs.record_stt_cost(
                model="long",
                audio_seconds=61.2,
            )
        report = costs.build_estimate_report(tmp_path / "workspace")
        event = report["events"][0]
        assert event["billed_seconds"] == 62
        assert round(event["billed_minutes"], 6) == round(62 / 60, 6)
        assert round(event["estimated_usd"], 6) == round((62 / 60) * 0.016, 6)
    finally:
        costs.shutdown_cost_tracking()


def test_missing_pricing_marks_report_incomplete(tmp_path):
    _init_tracker(tmp_path)
    try:
        with costs.bound_context(stage="thumbnail"):
            costs.record_generate_content_cost(
                model="unknown-image-model",
                usage_metadata=_usage(prompt=100, output=0),
                service="generate_content_image",
                generated_images=1,
                operation="thumbnail_generate",
            )
        report = costs.build_estimate_report(tmp_path / "workspace")
        assert report["incomplete"] is True
        assert report["summary"]["unpriced_event_count"] == 1
        assert report["missing_pricing"] == [
            {
                "service": "generate_content_image",
                "model": "unknown-image-model",
                "reason": "no pricing entry",
            }
        ]
    finally:
        costs.shutdown_cost_tracking()


def test_report_separates_fixed_and_variable_costs(tmp_path):
    _init_tracker(tmp_path)
    try:
        with costs.bound_context(stage="planning"):
            costs.record_generate_content_cost(
                model="gemini-3-flash-preview",
                usage_metadata=_usage(prompt=1000, output=100),
                operation="planning_topic_selection",
            )
        with costs.bound_context(stage="audio_source"):
            costs.record_stt_cost(
                model="long",
                audio_seconds=30.0,
            )
        report = costs.build_estimate_report(tmp_path / "workspace")
        assert report["summary"]["fixed_overhead_usd"] > 0
        assert report["summary"]["variable_media_usd"] > 0
        assert report["summary"]["estimated_usd"] == round(
            report["summary"]["fixed_overhead_usd"] + report["summary"]["variable_media_usd"],
            6,
        )
    finally:
        costs.shutdown_cost_tracking()


def test_current_billing_labels_are_sanitized(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    costs.initialize_cost_tracking(
        workspace=workspace,
        run_id="VF RUN 123",
        channel="Demo Channel!",
    )
    try:
        with costs.bound_context(stage="Script Review"):
            labels = costs.current_billing_labels("Thumbnail Review!")
        assert labels == {
            "vf_run": "vf_run_123",
            "vf_stage": "script_review",
            "vf_op": "thumbnail_review",
            "vf_channel": "demo_channel",
        }
    finally:
        costs.shutdown_cost_tracking()


def test_fixture_replay_creates_zero_cost_event(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(fixture_cache, "FIXTURES_DIR", tmp_path / "fixtures")
    fixture_cache.set_mode("replay", channel_slug="demo")
    costs.initialize_cost_tracking(
        workspace=workspace,
        run_id="vf_replay",
        channel="demo_channel",
        fixture_mode="replay",
    )

    async def generate_text(prompt: str, **kwargs):
        raise AssertionError("Replay should bypass the wrapped function")

    wrapped = fixture_cache.cached_text(generate_text)
    key = fixture_cache._cache_key("generate_text", ("hello",), {})
    cache_path = fixture_cache.FIXTURES_DIR / "demo" / "text" / f"{key}.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps({"fn": "generate_text", "key": key, "result": "cached"}),
        encoding="utf-8",
    )

    try:
        with costs.bound_context(stage="script"):
            result = asyncio.run(wrapped("hello"))
        report = costs.build_estimate_report(workspace)
        event = report["events"][0]
        assert result == "cached"
        assert event["cached"] is True
        assert event["cache_kind"] == "fixture_replay"
        assert event["fixture_mode"] == "replay"
        assert event["estimated_usd"] == 0.0
    finally:
        fixture_cache.set_mode("off")
        costs.shutdown_cost_tracking()


def test_actual_report_without_rows_stays_pending(tmp_path):
    estimate_report = {
        "run_id": "vf_test",
        "channel": "demo_channel",
        "summary": {
            "estimated_usd": 1.23,
            "label_supported_estimated_usd": 1.11,
        },
    }
    report = build_actual_report(
        workspace=tmp_path,
        estimate_report=estimate_report,
        table_fqid="billing.dataset.table",
        query_row=None,
    )
    assert report["status"] == "pending_reconciliation"
    assert report["actual"] is None
    assert report["estimated_summary"]["estimated_usd"] == 1.23


def test_actual_report_matches_billing_rows(tmp_path):
    estimate_report = {
        "run_id": "vf_test",
        "channel": "demo_channel",
        "summary": {
            "estimated_usd": 1.0,
            "label_supported_estimated_usd": 0.9,
        },
    }
    query_row = SimpleNamespace(
        gross_cost_usd=2.0,
        credits_usd=-0.25,
        net_cost_usd=1.75,
        matched_rows=3,
        first_usage_start_time="2026-04-10T00:00:00Z",
        last_usage_end_time="2026-04-10T00:05:00Z",
        line_items=[
            {"service": "Vertex AI", "sku": "Gemini", "cost": 2.0, "credits_amount": -0.25},
        ],
    )
    report = build_actual_report(
        workspace=tmp_path,
        estimate_report=estimate_report,
        table_fqid="billing.dataset.table",
        query_row=query_row,
    )
    assert report["status"] == "matched"
    assert report["actual"]["gross_cost_usd"] == 2.0
    assert report["actual"]["credits_usd"] == -0.25
    assert report["actual"]["net_cost_usd"] == 1.75
    assert report["actual"]["line_items"][0]["cost"] == 2.0


def test_cost_estimate_html_uses_dark_theme_and_subscription_note(tmp_path):
    _init_tracker(tmp_path)
    try:
        with costs.bound_context(stage="image_source"):
            costs.record_generate_content_cost(
                model="gemini-3.1-flash-image-preview",
                usage_metadata=_usage(prompt=100, output=0),
                service="generate_content_image",
                generated_images=1,
                operation="image_generate_illustration",
            )
        report = costs.build_estimate_report(tmp_path / "workspace")
        html = render_estimate_html(report)
        assert "--bg: #0d1117;" in html
        assert "class=\"card\"" in html
        assert "Serper and Pexels subscription or API-plan fees are not included" in html
        assert "body { font-family: Arial, sans-serif; margin: 24px; color: #111; }" not in html
    finally:
        costs.shutdown_cost_tracking()
