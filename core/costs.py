"""Per-run Google AI cost tracking and estimate reporting."""

from __future__ import annotations

import json
import math
import re
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from tools.log_viewer import render_estimate_html
from settings import PROJECT_ROOT

_PRICE_PATH = PROJECT_ROOT / "config" / "pricing" / "google_ai_pricing.json"
_FIXED_STAGES = {"planning", "script", "thumbnail", "final_review"}
_VARIABLE_STAGES = {"image_source", "audio_source"}
_BILLING_LABEL_KEYS = ("vf_run", "vf_stage", "vf_op", "vf_channel")

_run_id_var: ContextVar[str] = ContextVar("cost_run_id", default="")
_channel_var: ContextVar[str] = ContextVar("cost_channel", default="")
_stage_var: ContextVar[str] = ContextVar("cost_stage", default="")
_operation_var: ContextVar[str] = ContextVar("cost_operation", default="")
_fixture_mode_var: ContextVar[str] = ContextVar("cost_fixture_mode", default="off")


class PricingEntry(BaseModel):
    service: str
    model: str
    input_rate_usd_per_1m_tokens: float | None = None
    input_rate_long_context_usd_per_1m_tokens: float | None = None
    cached_input_rate_usd_per_1m_tokens: float | None = None
    cached_input_rate_long_context_usd_per_1m_tokens: float | None = None
    output_text_rate_usd_per_1m_tokens: float | None = None
    output_text_rate_long_context_usd_per_1m_tokens: float | None = None
    output_image_rate_usd_per_image: float | None = None
    output_audio_rate_usd_per_1m_tokens: float | None = None
    audio_tokens_per_second: int | None = None
    rate_usd_per_minute: float | None = None
    billed_seconds_rounding: int | None = None
    reconciliation_supported: bool = True
    source_url: str = ""
    notes: list[str] = Field(default_factory=list)


class PricingCatalog(BaseModel):
    version: str
    effective_date: str
    entries: list[PricingEntry]


class CostEvent(BaseModel):
    occurred_at: str
    run_id: str
    channel: str
    stage: str
    operation: str
    provider: str
    service: str
    model: str
    cached: bool = False
    cache_kind: str | None = None
    fixture_mode: str = "off"
    estimated_usd: float | None = None
    reconciliation_supported: bool = True
    prompt_tokens: int | None = None
    cached_prompt_tokens: int | None = None
    output_tokens: int | None = None
    generated_images: int | None = None
    audio_seconds: float | None = None
    billed_seconds: int | None = None
    billed_minutes: float | None = None
    audio_output_tokens: int | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    source_url: str | None = None


class CostTracker:
    def __init__(
        self,
        *,
        workspace: Path,
        run_id: str,
        channel: str,
        fixture_mode: str,
        catalog: PricingCatalog,
    ) -> None:
        self.workspace = workspace
        self.run_id = run_id
        self.channel = channel
        self.fixture_mode = fixture_mode
        self.catalog = catalog
        self.events: list[CostEvent] = []
        self.missing_pricing: list[dict[str, str]] = []

    def add_event(self, event: CostEvent) -> None:
        self.events.append(event)

    def add_missing_pricing(self, *, service: str, model: str, reason: str) -> None:
        item = {"service": service, "model": model, "reason": reason}
        if item not in self.missing_pricing:
            self.missing_pricing.append(item)


_tracker: CostTracker | None = None


@lru_cache(maxsize=1)
def _load_pricing_catalog() -> PricingCatalog:
    return PricingCatalog.model_validate_json(_PRICE_PATH.read_text(encoding="utf-8"))


def generate_run_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"vf_{stamp}_{uuid.uuid4().hex[:8]}"


def sanitize_label_value(value: str) -> str:
    sanitized = re.sub(r"[^a-z0-9_-]+", "_", value.strip().lower())
    sanitized = sanitized.strip("_-")
    if not sanitized:
        sanitized = "na"
    return sanitized[:63]


def initialize_cost_tracking(
    *,
    workspace: Path,
    run_id: str,
    channel: str,
    fixture_mode: str = "off",
) -> None:
    global _tracker
    _tracker = CostTracker(
        workspace=workspace,
        run_id=run_id,
        channel=channel,
        fixture_mode=fixture_mode,
        catalog=_load_pricing_catalog(),
    )
    _run_id_var.set(run_id)
    _channel_var.set(channel)
    _fixture_mode_var.set(fixture_mode)


def shutdown_cost_tracking() -> None:
    global _tracker
    _tracker = None
    _run_id_var.set("")
    _channel_var.set("")
    _stage_var.set("")
    _operation_var.set("")
    _fixture_mode_var.set("off")


def get_tracker() -> CostTracker | None:
    return _tracker


@contextmanager
def bound_context(*, stage: str | None = None, operation: str | None = None):
    stage_token = op_token = None
    if stage is not None:
        stage_token = _stage_var.set(stage)
    if operation is not None:
        op_token = _operation_var.set(operation)
    try:
        yield
    finally:
        if op_token is not None:
            _operation_var.reset(op_token)
        if stage_token is not None:
            _stage_var.reset(stage_token)


def current_billing_labels(operation: str | None = None) -> dict[str, str]:
    run_id = _run_id_var.get()
    channel = _channel_var.get()
    if not run_id or not channel:
        return {}
    stage = _stage_var.get() or "unknown"
    operation_name = operation or _operation_var.get() or "unknown"
    return {
        "vf_run": sanitize_label_value(run_id),
        "vf_stage": sanitize_label_value(stage),
        "vf_op": sanitize_label_value(operation_name),
        "vf_channel": sanitize_label_value(channel),
    }


def _find_price(service: str, model: str) -> PricingEntry | None:
    tracker = get_tracker()
    if tracker is None:
        return None
    for entry in tracker.catalog.entries:
        if entry.service == service and entry.model == model:
            return entry
    return None


def _now_iso() -> str:
    return datetime.now().isoformat()


def _usage_value(usage_metadata: Any, attr: str) -> int:
    value = getattr(usage_metadata, attr, None)
    return int(value or 0)


def _round_usd(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 6)


def _event_defaults(
    *,
    provider: str,
    service: str,
    model: str,
    operation: str,
    cached: bool = False,
    cache_kind: str | None = None,
    reconciliation_supported: bool = True,
    notes: list[str] | None = None,
    source_url: str | None = None,
) -> dict[str, Any]:
    return {
        "occurred_at": _now_iso(),
        "run_id": _run_id_var.get(),
        "channel": _channel_var.get(),
        "stage": _stage_var.get() or "unknown",
        "operation": operation,
        "provider": provider,
        "service": service,
        "model": model,
        "cached": cached,
        "cache_kind": cache_kind,
        "fixture_mode": _fixture_mode_var.get() or "off",
        "labels": current_billing_labels(operation),
        "reconciliation_supported": reconciliation_supported,
        "notes": notes or [],
        "source_url": source_url,
    }


def _record(event: CostEvent) -> None:
    tracker = get_tracker()
    if tracker is None:
        return
    tracker.add_event(event)


def _mark_missing_pricing(service: str, model: str, reason: str) -> None:
    tracker = get_tracker()
    if tracker is None:
        return
    tracker.add_missing_pricing(service=service, model=model, reason=reason)


def record_cache_hit(
    *,
    provider: str,
    service: str,
    model: str,
    operation: str,
    cache_kind: str,
    reconciliation_supported: bool | None = None,
    notes: list[str] | None = None,
) -> None:
    price = _find_price(service, model)
    supported = (
        reconciliation_supported
        if reconciliation_supported is not None
        else (price.reconciliation_supported if price else True)
    )
    event = CostEvent(
        **_event_defaults(
            provider=provider,
            service=service,
            model=model,
            operation=operation,
            cached=True,
            cache_kind=cache_kind,
            reconciliation_supported=supported,
            notes=notes,
            source_url=price.source_url if price else None,
        ),
        estimated_usd=0.0,
    )
    _record(event)


def record_generate_content_cost(
    *,
    model: str,
    usage_metadata: Any,
    operation: str,
    service: str = "generate_content",
    provider: str = "google_vertex_ai",
    generated_images: int | None = None,
) -> None:
    price = _find_price(service, model)
    prompt_tokens = _usage_value(usage_metadata, "prompt_token_count")
    cached_prompt_tokens = _usage_value(usage_metadata, "cached_content_token_count")
    output_tokens = _usage_value(usage_metadata, "candidates_token_count")
    prompt_uncached = max(prompt_tokens - cached_prompt_tokens, 0)
    notes: list[str] = []

    if price is None:
        _mark_missing_pricing(service, model, "no pricing entry")
        estimated_usd = None
        supported = True
        source_url = None
    else:
        source_url = price.source_url
        supported = price.reconciliation_supported
        is_long = prompt_tokens > 200_000
        input_rate = (
            price.input_rate_long_context_usd_per_1m_tokens
            if is_long and price.input_rate_long_context_usd_per_1m_tokens is not None
            else price.input_rate_usd_per_1m_tokens
        )
        cached_rate = (
            price.cached_input_rate_long_context_usd_per_1m_tokens
            if is_long and price.cached_input_rate_long_context_usd_per_1m_tokens is not None
            else price.cached_input_rate_usd_per_1m_tokens
        )
        output_rate = (
            price.output_text_rate_long_context_usd_per_1m_tokens
            if is_long and price.output_text_rate_long_context_usd_per_1m_tokens is not None
            else price.output_text_rate_usd_per_1m_tokens
        )

        estimated_usd = 0.0
        missing_parts: list[str] = []
        if prompt_uncached:
            if input_rate is None:
                missing_parts.append("input_rate")
            else:
                estimated_usd += prompt_uncached / 1_000_000 * input_rate
        if cached_prompt_tokens:
            if cached_rate is None:
                missing_parts.append("cached_input_rate")
            else:
                estimated_usd += cached_prompt_tokens / 1_000_000 * cached_rate
        if output_tokens:
            if output_rate is None:
                missing_parts.append("output_text_rate")
            else:
                estimated_usd += output_tokens / 1_000_000 * output_rate
        if generated_images:
            if price.output_image_rate_usd_per_image is None:
                missing_parts.append("output_image_rate")
            else:
                estimated_usd += generated_images * price.output_image_rate_usd_per_image
        if missing_parts:
            _mark_missing_pricing(service, model, ", ".join(sorted(set(missing_parts))))
            notes.append("Pricing incomplete for one or more billed dimensions.")
            estimated_usd = None

    event = CostEvent(
        **_event_defaults(
            provider=provider,
            service=service,
            model=model,
            operation=operation,
            reconciliation_supported=supported,
            notes=notes,
            source_url=source_url,
        ),
        estimated_usd=_round_usd(estimated_usd),
        prompt_tokens=prompt_tokens or None,
        cached_prompt_tokens=cached_prompt_tokens or None,
        output_tokens=output_tokens or None,
        generated_images=generated_images,
    )
    _record(event)


def record_tts_cost(
    *,
    model: str,
    prompt_tokens: int | None,
    audio_seconds: float,
    operation: str,
) -> None:
    price = _find_price("tts", model)
    notes: list[str] = []
    if price is None:
        _mark_missing_pricing("tts", model, "no pricing entry")
        estimated_usd = None
        supported = True
        source_url = None
        audio_output_tokens = None
    else:
        audio_token_factor = price.audio_tokens_per_second
        if price.input_rate_usd_per_1m_tokens is None or price.output_audio_rate_usd_per_1m_tokens is None or audio_token_factor is None:
            _mark_missing_pricing("tts", model, "input/output audio rate")
            estimated_usd = None
            notes.append("Pricing incomplete for TTS.")
            audio_output_tokens = None
        else:
            audio_output_tokens = int(math.ceil(audio_seconds * audio_token_factor))
            estimated_usd = 0.0
            if prompt_tokens:
                estimated_usd += prompt_tokens / 1_000_000 * price.input_rate_usd_per_1m_tokens
            estimated_usd += audio_output_tokens / 1_000_000 * price.output_audio_rate_usd_per_1m_tokens
        supported = price.reconciliation_supported
        source_url = price.source_url

    event = CostEvent(
        **_event_defaults(
            provider="google_cloud_tts",
            service="tts",
            model=model,
            operation=operation,
            reconciliation_supported=supported,
            notes=notes,
            source_url=source_url,
        ),
        estimated_usd=_round_usd(estimated_usd),
        prompt_tokens=prompt_tokens,
        audio_seconds=round(audio_seconds, 3),
        audio_output_tokens=audio_output_tokens,
    )
    _record(event)


def record_stt_cost(
    *,
    model: str,
    audio_seconds: float,
    operation: str = "stt_transcribe",
) -> None:
    price = _find_price("speech_to_text", model)
    notes: list[str] = []
    if price is None or price.rate_usd_per_minute is None:
        _mark_missing_pricing("speech_to_text", model, "rate_usd_per_minute")
        estimated_usd = None
        billed_seconds = None
        billed_minutes = None
        supported = False if price is None else price.reconciliation_supported
        source_url = None if price is None else price.source_url
        notes.append("Pricing incomplete for Speech-to-Text.")
    else:
        rounding = price.billed_seconds_rounding or 1
        billed_seconds = int(math.ceil(audio_seconds / rounding) * rounding)
        billed_minutes = billed_seconds / 60.0
        estimated_usd = billed_minutes * price.rate_usd_per_minute
        supported = price.reconciliation_supported
        source_url = price.source_url

    event = CostEvent(
        **_event_defaults(
            provider="google_cloud_speech",
            service="speech_to_text",
            model=model,
            operation=operation,
            reconciliation_supported=supported,
            notes=notes,
            source_url=source_url,
        ),
        estimated_usd=_round_usd(estimated_usd),
        audio_seconds=round(audio_seconds, 3),
        billed_seconds=billed_seconds,
        billed_minutes=round(billed_minutes, 6) if billed_minutes is not None else None,
    )
    _record(event)


def _group_total(events: list[CostEvent]) -> float:
    return round(sum(event.estimated_usd or 0.0 for event in events), 6)




def _rollup(events: list[CostEvent], *fields: str) -> list[dict[str, Any]]:
    buckets: dict[tuple[Any, ...], list[CostEvent]] = {}
    for event in events:
        key = tuple(getattr(event, field) for field in fields)
        buckets.setdefault(key, []).append(event)

    rows = []
    for key, bucket in buckets.items():
        row = {field: value for field, value in zip(fields, key)}
        row["estimated_usd"] = _group_total(bucket)
        row["event_count"] = len(bucket)
        row["cached_event_count"] = sum(1 for event in bucket if event.cached)
        rows.append(row)
    rows.sort(key=lambda row: row["estimated_usd"], reverse=True)
    return rows


def _cost_bucket(stage: str) -> str:
    if stage in _FIXED_STAGES:
        return "fixed"
    if stage in _VARIABLE_STAGES:
        return "variable"
    return "other"


def build_estimate_report(workspace: Path, checkpoint: dict[str, Any] | None = None) -> dict[str, Any]:
    tracker = get_tracker()
    if tracker is None:
        raise RuntimeError("Cost tracking has not been initialized.")

    events = [event.model_dump() for event in tracker.events]
    fixed_events = [event for event in tracker.events if _cost_bucket(event.stage) == "fixed"]
    variable_events = [event for event in tracker.events if _cost_bucket(event.stage) == "variable"]
    other_events = [event for event in tracker.events if _cost_bucket(event.stage) == "other"]
    label_supported_estimate = _group_total([
        event for event in tracker.events if event.reconciliation_supported
    ])
    unpriced_events = [event for event in tracker.events if event.estimated_usd is None]
    cache_hits = sum(1 for event in tracker.events if event.cached)

    summary = {
        "estimated_usd": _group_total(tracker.events),
        "fixed_overhead_usd": _group_total(fixed_events),
        "variable_media_usd": _group_total(variable_events),
        "other_usd": _group_total(other_events),
        "label_supported_estimated_usd": label_supported_estimate,
        "event_count": len(tracker.events),
        "billable_event_count": sum(1 for event in tracker.events if (event.estimated_usd or 0) > 0),
        "zero_cost_event_count": sum(1 for event in tracker.events if event.estimated_usd == 0),
        "cache_hit_count": cache_hits,
        "unpriced_event_count": len(unpriced_events),
    }
    by_stage = _rollup(tracker.events, "stage")
    by_operation = _rollup(tracker.events, "stage", "operation")
    by_model = _rollup(tracker.events, "service", "model")
    top_contributors = _rollup(tracker.events, "stage", "operation", "model")[:5]
    report = {
        "report_type": "cost_estimate",
        "generated_at": _now_iso(),
        "workspace": str(workspace),
        "run_id": tracker.run_id,
        "channel": tracker.channel,
        "fixture_mode": tracker.fixture_mode,
        "pricing_catalog": {
            "path": str(_PRICE_PATH),
            "version": tracker.catalog.version,
            "effective_date": tracker.catalog.effective_date,
        },
        "incomplete": bool(tracker.missing_pricing),
        "missing_pricing": tracker.missing_pricing,
        "billing_label_keys": list(_BILLING_LABEL_KEYS),
        "summary": summary,
        "by_stage": by_stage,
        "by_operation": by_operation,
        "by_model": by_model,
        "top_contributors": top_contributors,
        "checkpoint": checkpoint or {},
        "events": events,
        "limitations": [
            "Speech-to-Text events are estimated locally and are not directly reconcilable by run label.",
            "Serper and Pexels subscription or API-plan fees are not included in the AI estimate.",
        ],
    }
    return report



def write_estimate_reports(workspace: Path, checkpoint: dict[str, Any] | None = None) -> dict[str, Any]:
    report = build_estimate_report(workspace, checkpoint=checkpoint)
    reports_dir = workspace / "reports"
    reports_dir.mkdir(exist_ok=True)
    json_path = reports_dir / "cost_estimate.json"
    html_path = reports_dir / "cost_estimate.html"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(render_estimate_html(report), encoding="utf-8")
    return report


def cost_summary_line(report: dict[str, Any]) -> str:
    summary = report["summary"]
    contributors = report["top_contributors"]
    if contributors:
        top = ", ".join(
            f"{row['stage']}/{row['operation']} ${row['estimated_usd']:.4f}"
            for row in contributors[:3]
        )
    else:
        top = "none"
    suffix = " (INCOMPLETE)" if report["incomplete"] else ""
    total_line = f"Estimated AI cost: ${summary['estimated_usd']:.6f}"
    fixed_line = f"Fixed overhead: ${summary['fixed_overhead_usd']:.6f}"
    variable_line = f"Variable media: ${summary['variable_media_usd']:.6f}"
    return (
        f"{total_line}{suffix}\n"
        f"{fixed_line}\n"
        f"{variable_line}\n"
        f"Top contributors: {top}"
    )
