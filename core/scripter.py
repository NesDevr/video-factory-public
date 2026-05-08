"""Stage 1: Script generation — AI writes narration + image prompts, reviewed by Gate #1."""

import json
import logging
import math
from pathlib import Path

import clients
import prompts
from core.reviewer import ReviewGateError, review_gate
from core.utils import (
    duration_window,
    estimate_section_seconds,
    script_timing_profile,
    words_for_seconds,
)
from core.utils import (
    ChannelConfig, Script, ScriptSection, VisualSlot,
    compute_sections_range, minimum_visual_slots_for_duration, save_script,
)
from settings import settings

logger = logging.getLogger("video_factory")

_MAX_DURATION_RETRIES = 2


def _thumbnail_strategy_options(
    config: ChannelConfig,
    allowed_names: list[str],
) -> list[dict[str, str]]:
    strategies_by_name = {
        strategy.name: strategy
        for strategy in config.thumbnail_strategies
    }
    return [
        {
            "name": strategies_by_name[name].name,
            "instruction": strategies_by_name[name].instruction,
        }
        for name in allowed_names
    ]


def _validate_thumbnail_strategy_choice(
    chosen_strategy: str,
    *,
    video_type: str,
    allowed_names: list[str],
) -> str:
    allowed = set(allowed_names)
    if chosen_strategy not in allowed:
        available = ", ".join(sorted(allowed))
        raise ValueError(
            "Script selected thumbnail strategy "
            f"'{chosen_strategy}' not allowed for video type '{video_type}'. "
            f"Allowed: {available}"
        )
    return chosen_strategy


def _title_banner_numbering_errors(
    script_data: dict,
    numbering_order: str | None,
) -> list[str]:
    """Validate numbered title_banner slots before the script is saved."""
    if not numbering_order:
        return []

    banners = []
    for section in script_data.get("sections", []):
        for slot in section.get("slots", []):
            if slot.get("visual") == "title_banner":
                props = slot.get("props") or {}
                banners.append({
                    "section_id": section.get("id"),
                    "section_number": props.get("section_number"),
                })

    if not banners:
        return []

    errors: list[str] = []
    actual_numbers: list[int] = []
    for banner in banners:
        section_id = banner["section_id"]
        section_number = banner["section_number"]
        if not isinstance(section_number, int):
            errors.append(
                f"Section {section_id}: title_banner.section_number must be an integer."
            )
            continue
        actual_numbers.append(section_number)

    if len(actual_numbers) != len(banners):
        return errors

    if numbering_order == "ascending":
        expected_numbers = list(range(1, len(banners) + 1))
    elif numbering_order == "descending":
        expected_numbers = list(range(len(banners), 0, -1))
    else:
        raise ValueError(f"Unsupported numbering_order: {numbering_order}")

    if actual_numbers != expected_numbers:
        errors.append(
            "title_banner section_number values must be "
            f"{expected_numbers} in section order; got {actual_numbers}."
        )

    return errors


def _script_word_totals(
    data: dict,
) -> tuple[int, int]:
    """Return (section_count, total_words)."""
    secs = data.get("sections", [])
    total_words = sum(len(s.get("narration", "").split()) for s in secs)
    return len(secs), total_words


def _apply_word_based_duration_estimates(
    data: dict,
    *,
    timing_profile,
) -> dict:
    total_estimated_seconds = 0.0
    for index, section in enumerate(data.get("sections", []), start=1):
        word_count = len(str(section.get("narration", "")).split())
        estimated_seconds = round(
            estimate_section_seconds(word_count, profile=timing_profile),
            1,
        )
        section.setdefault("id", index)
        section["estimated_duration_seconds"] = estimated_seconds
        total_estimated_seconds += estimated_seconds
    data["total_estimated_duration_seconds"] = round(total_estimated_seconds, 1)
    return data


def _script_validation_errors(
    data: dict,
    *,
    numbering_order: str | None,
    max_visual_hold_seconds: float,
    crossfade: float,
    timing_profile,
    min_sections: int | None = None,
    min_words: int | None = None,
    max_words: int | None = None,
) -> tuple[list[str], list[dict]]:
    sections = data.get("sections", [])
    errors = _title_banner_numbering_errors(data, numbering_order)
    pacing_issues: list[dict] = []
    subscribe_cta_sections: list[int] = []

    if (
        min_sections is not None
        and min_words is not None
        and max_words is not None
    ):
        total_words = 0
        for section in sections:
            total_words += len(str(section.get("narration", "")).split())
        if len(sections) < min_sections:
            errors.append(
                f"script has {len(sections)} sections; needs at least {min_sections}"
            )
        if total_words < min_words:
            errors.append(
                f"script is too short: {total_words} words; needs at least {min_words}"
            )
        if total_words > max_words:
            errors.append(
                f"script is too long: {total_words} words; must be at most {max_words}"
            )

    for idx, section in enumerate(sections, start=1):
        section_id = section.get("id", idx)
        slots = list(section.get("slots", []))
        if not slots:
            errors.append(f"Section {section_id} has no visual slots.")
            continue

        word_count = len(str(section.get("narration", "")).split())
        estimated_seconds = estimate_section_seconds(
            word_count,
            profile=timing_profile,
        )
        minimum_slots = minimum_visual_slots_for_duration(
            estimated_seconds,
            max_visual_hold_seconds,
            crossfade,
        )
        avg_hold = (
            estimated_seconds + (crossfade * max(len(slots) - 1, 0))
        ) / len(slots)
        if avg_hold > max_visual_hold_seconds:
            issue = {
                "section_id": section_id,
                "word_count": word_count,
                "current_slots": len(slots),
                "minimum_slots": minimum_slots,
                "recommended_action": "split_section" if minimum_slots > 6 else "add_slots",
                "message": (
                    f"Section {section_id}: {len(slots)} slots is too sparse for "
                    f"{word_count} narration words; needs at least {minimum_slots} slots "
                    f"to keep beats under {max_visual_hold_seconds:.0f}s, so add more slots "
                    "or split the section."
                ),
            }
            pacing_issues.append(issue)
            errors.append(issue["message"])

        title_banner_slots = [
            slot for slot in slots
            if str(slot.get("visual", "")) == "title_banner"
        ]
        if len(title_banner_slots) > 1:
            errors.append(
                f"Section {section_id} has {len(title_banner_slots)} title_banner slots; only one is allowed per section."
            )
        if title_banner_slots and str(slots[0].get("visual", "")) != "title_banner":
            errors.append(
                f"Section {section_id}: title_banner must be the first slot in its section."
            )

        if any(str(slot.get("visual", "")) == "subscribe_cta" for slot in slots):
            subscribe_cta_sections.append(section_id)

        for slot_index, slot in enumerate(slots, start=1):
            visual = str(slot.get("visual", ""))
            props = slot.get("props") or {}
            if visual == "text_only_slide" and props.get("variant") != "ai_prompt_preview":
                errors.append(
                    f"Section {section_id} slot {slot_index}: text_only_slide is reserved for internal AI prompt preview only."
                )
            if visual == "info_slide" and not str(slot.get("prompt", "")).strip():
                errors.append(
                    f"Section {section_id} slot {slot_index}: info_slide requires an image prompt; do not use image-less text slides."
                )
            visual_policy = str(slot.get("visual_policy", "source_as_written"))
            if visual_policy not in VisualSlot.VISUAL_POLICIES:
                errors.append(
                    f"Section {section_id} slot {slot_index}: unknown visual_policy '{visual_policy}'."
                )
            if visual_policy == "photo_backed_info_slide" and visual != "info_slide":
                errors.append(
                    f"Section {section_id} slot {slot_index}: visual_policy photo_backed_info_slide requires visual info_slide."
                )
            if visual in VisualSlot.BACKDROP_FIGURE_TYPES:
                if not str(slot.get("prompt", "")).strip():
                    errors.append(
                        f"Section {section_id} slot {slot_index}: {visual} requires a background image prompt."
                    )
                if not str(slot.get("keywords", "")).strip():
                    errors.append(
                        f"Section {section_id} slot {slot_index}: {visual} requires background image keywords."
                    )

    if len(subscribe_cta_sections) > 1:
        errors.append(
            f"Script has {len(subscribe_cta_sections)} subscribe_cta sections; only one is allowed per video."
        )
    return errors, pacing_issues


def _prompt_word_targets(
    *,
    target_seconds: int,
    sections_range: list[int],
    timing_profile,
) -> tuple[int, int, int]:
    representative_sections = max(1.0, sum(sections_range) / 2)
    target_words = max(
        1,
        int(round(words_for_seconds(
            target_seconds,
            section_count=representative_sections,
            profile=timing_profile,
        ))),
    )
    min_words_per_section = max(
        1,
        int(math.ceil(
            words_for_seconds(
                target_seconds,
                section_count=sections_range[1],
                profile=timing_profile,
            ) / sections_range[1]
        )),
    )
    target_words_per_section = max(
        1,
        int(round(target_words / representative_sections)),
    )
    return target_words, min_words_per_section, target_words_per_section


def _duration_word_bounds(
    *,
    min_duration: float,
    max_duration: float,
    section_count: int,
    timing_profile,
) -> tuple[int, int]:
    min_words = max(
        1,
        int(math.ceil(words_for_seconds(
            min_duration,
            section_count=section_count,
            profile=timing_profile,
        ))),
    )
    max_words = max(
        min_words,
        int(math.floor(words_for_seconds(
            max_duration,
            section_count=section_count,
            profile=timing_profile,
        ))),
    )
    return min_words, max_words


async def generate_script(
    config: ChannelConfig,
    plan: dict,
    workspace: Path,
    *,
    allow_review_failure: bool = False,
    preview_mode: bool = False,
) -> tuple[Script, dict]:
    """Generate and review a script for the given plan.

    Returns a validated, reviewed Script.
    """
    topic = plan["topic"]
    video_type = plan["video_type"]
    angle = plan.get("angle", "")
    narrative_hook = plan.get("narrative_hook", "")
    research_context = plan.get("research_context", "")

    # Get video type config
    vt_config = config.video_types.get(video_type)
    if not vt_config:
        raise ValueError(f"Video type '{video_type}' not found in channel config")
    numbering_order = vt_config.numbering_order

    # Generate initial script
    logger.info(f"Generating script: {topic} ({video_type})")

    # Auto-calculate sections from duration (~1 section per 45s)
    target = config.video.target_duration_minutes
    sections_range = compute_sections_range(target, vt_config)
    target_seconds = target * 60
    min_sections = sections_range[0]
    timing_profile = script_timing_profile(settings.gemini_tts_model)
    min_duration, max_duration = duration_window(
        target_seconds,
        preview_mode=preview_mode,
    )
    max_duration_retries = _MAX_DURATION_RETRIES
    max_visual_hold_seconds = config.rendering_defaults.max_visual_hold_seconds
    intra_crossfade = config.rendering_defaults.intra_slot_crossfade
    target_words, min_words_per_section, target_words_per_section = _prompt_word_targets(
        target_seconds=target_seconds,
        sections_range=sections_range,
        timing_profile=timing_profile,
    )
    generation_duration_requirements = (
        f"12. TOTAL WORD COUNT: Aim for about {target_words} words of narration "
        f"across all sections combined for this {target}-minute video.\n"
        f"13. SECTIONS: You MUST write at least {sections_range[0]} sections "
        f"(up to {sections_range[1]}). DO NOT write fewer than {sections_range[0]}.\n"
        "14. PER-SECTION NARRATION: "
        f"with {sections_range[0]}-{sections_range[1]} sections, usually write "
        f"about {min_words_per_section}-{target_words_per_section} words per section. "
        "Write detailed, concrete narration — not filler."
    )
    revision_duration_guard = (
        f"Target about {target_words} total words. "
        f"Keep between {sections_range[0]} and {sections_range[1]} sections. "
        "Do NOT add or remove sections beyond this range."
    )
    thumbnail_strategies = _thumbnail_strategy_options(
        config,
        vt_config.allowed_thumbnail_strategies,
    )

    prompt = prompts.script_generation_prompt(
        topic=topic,
        video_type=video_type,
        angle=angle,
        channel_name=config.channel_name,
        audience=config.niche.audience,
        language=config.language,
        target_duration_minutes=target,
        sections_range=sections_range,
        section_style=vt_config.section_style,
        pacing=vt_config.pacing,
        style_prompt_suffix=config.image_sourcing.style_prompt_suffix,
        title_format_instruction=plan["title_format_instruction"],
        description_style_instruction=plan["description_style_instruction"],
        thumbnail_strategies=thumbnail_strategies,
        visual_guidance=config.video.visual_guidance,
        narrative_hook=narrative_hook,
        research_context=research_context,
        section_color_palette=config.style.text.get("section_color_palette"),
        music_pool=config.video.music_pool,
        voice_variations=config.voice.voice_prompt_variations,
        transition_pool=config.style.video.get("transition_pool", ["fade"]),
        numbering_order=numbering_order,
        duration_requirements=generation_duration_requirements,
        channel_goal=plan.get("channel_goal", ""),
        content_family=plan.get("content_family", ""),
        lead_magnet=plan.get("lead_magnet", ""),
        low_ticket_offer=plan.get("low_ticket_offer", ""),
        mid_ticket_offer=plan.get("mid_ticket_offer", ""),
        later_offers=plan.get("later_offers", []),
        video_jobs=plan.get("video_jobs", []),
        cta_rules=plan.get("cta_rules", []),
        cta_angle=plan.get("cta_angle", ""),
        min_visible_beat_seconds=config.rendering_defaults.image_slot_min_duration,
        max_visual_hold_seconds=max_visual_hold_seconds,
    )
    system_inst = prompts.script_system(
        tone=config.script_style.tone,
        instructions=config.script_style.instructions,
    )

    def _validate_generated_script(
        content: dict,
    ) -> tuple[list[str], list[dict], int, int, int, int]:
        _apply_word_based_duration_estimates(
            content,
            timing_profile=timing_profile,
        )
        n_sections, total_words = _script_word_totals(content)
        current_section_count = max(n_sections, min_sections)
        min_words, max_words = _duration_word_bounds(
            min_duration=min_duration,
            max_duration=max_duration,
            section_count=current_section_count,
            timing_profile=timing_profile,
        )
        errors, pacing_issues = _script_validation_errors(
            content,
            numbering_order=numbering_order,
            min_sections=min_sections,
            min_words=min_words,
            max_words=max_words,
            max_visual_hold_seconds=max_visual_hold_seconds,
            crossfade=intra_crossfade,
            timing_profile=timing_profile,
        )
        return errors, pacing_issues, n_sections, total_words, min_words, max_words

    def _script_validation_feedback(
        *,
        errors: list[str],
        pacing_issues: list[dict],
        n_sections: int,
        total_words: int,
        min_words: int,
        max_words: int,
    ) -> str:
        lines = [
            "Script failed validation after generation.",
            f"Current sections: {n_sections}; allowed range: {sections_range[0]}-{sections_range[1]}.",
            f"Current narration words: {total_words}; allowed range: {min_words}-{max_words}; target about {target_words}.",
            "Validation failures:",
            *[f"- {error}" for error in errors],
        ]
        if pacing_issues:
            lines.append("Pacing-specific slot budgets:")
            lines.extend(
                f"- Section {issue['section_id']}: {issue['current_slots']} slots now, "
                f"needs at least {issue['minimum_slots']}."
                for issue in pacing_issues
            )
        return "\n".join(lines)

    script_data = await clients.generate_json(
        prompt,
        system_instruction=system_inst,
        temperature=0.8,
        max_output_tokens=16384,
        operation_label="script_generate",
    )

    # ── Word-budget validation loop ───────────────────────────────

    for retry in range(max_duration_retries + 1):
        (
            errors,
            pacing_issues,
            n_sections,
            total_words,
            min_words,
            max_words,
        ) = _validate_generated_script(script_data)

        if not errors:
            logger.info(
                f"Script structure OK: {n_sections} sections, "
                f"{total_words} words "
                f"(target about {target_words}, allowed {min_words}-{max_words})"
            )
            break

        if retry == max_duration_retries:
            raise ValueError(
                f"Script validation failed after {max_duration_retries} retries: "
                + "; ".join(errors)
            )

        logger.warning(
            f"Script validation failed (attempt {retry + 1}/{max_duration_retries}): "
            f"{n_sections} sections, {total_words} words "
            f"(target about {target_words}, allowed {min_words}-{max_words}): "
            + "; ".join(errors)
        )

        revision_prompt = prompts.script_revision_prompt(
            script_json=json.dumps(script_data, ensure_ascii=False, indent=2),
            feedback=_script_validation_feedback(
                errors=errors,
                pacing_issues=pacing_issues,
                n_sections=n_sections,
                total_words=total_words,
                min_words=min_words,
                max_words=max_words,
            ),
            sections_range=tuple(sections_range),
            duration_guard=revision_duration_guard,
        )

        script_data = await clients.generate_json(
            revision_prompt,
            system_instruction=system_inst,
            temperature=0.7,
            max_output_tokens=16384,
            operation_label="script_validation_revision",
        )

    # ── Gate #1: Script Quality Review ────────────────────────────
    min_score = config.review_thresholds.script_min_score
    max_attempts = config.review_thresholds.script_max_attempts

    async def _regenerate(content: dict, feedback) -> dict:
        feedback_str = feedback.get("feedback", "") if isinstance(feedback, dict) else feedback
        revision_prompt = prompts.script_revision_prompt(
            script_json=json.dumps(content, ensure_ascii=False, indent=2),
            feedback=feedback_str,
            sections_range=tuple(sections_range),
            duration_guard=revision_duration_guard,
        )
        revised = await clients.generate_json(
            revision_prompt,
            system_instruction=system_inst,
            temperature=0.7,
            max_output_tokens=16384,
            operation_label="script_revision",
        )
        for retry in range(max_duration_retries + 1):
            (
                errors,
                pacing_issues,
                n_sections,
                total_words,
                min_words,
                max_words,
            ) = _validate_generated_script(revised)
            if not errors:
                return revised
            if retry == max_duration_retries:
                raise ValueError("Script revision failed validation: " + "; ".join(errors))

            logger.warning(
                "Script revision failed validation "
                f"(attempt {retry + 1}/{max_duration_retries}): "
                + "; ".join(errors)
            )
            revision_prompt = prompts.script_revision_prompt(
                script_json=json.dumps(revised, ensure_ascii=False, indent=2),
                feedback=_script_validation_feedback(
                    errors=errors,
                    pacing_issues=pacing_issues,
                    n_sections=n_sections,
                    total_words=total_words,
                    min_words=min_words,
                    max_words=max_words,
                ),
                sections_range=tuple(sections_range),
                duration_guard=revision_duration_guard,
            )
            revised = await clients.generate_json(
                revision_prompt,
                system_instruction=system_inst,
                temperature=0.7,
                max_output_tokens=16384,
                operation_label="script_revision_validation_correction",
            )
        return revised

    def _review_prompt(content: dict) -> str:
        return prompts.script_review_prompt(
            script_json=json.dumps(content, ensure_ascii=False, indent=2),
            min_score=min_score,
            numbering_order=numbering_order,
            max_visual_hold_seconds=max_visual_hold_seconds,
        )

    try:
        result = await review_gate(
            content=script_data,
            review_prompt_fn=_review_prompt,
            system_instruction=prompts.script_review_system(),
            regenerate_fn=_regenerate,
            max_attempts=max_attempts,
            gate_name="script_review",
        )
    except ReviewGateError as e:
        if not allow_review_failure:
            raise
        logger.warning(
            "[script_review] Continuing with best rejected script because "
            "allow_review_failure=True"
        )
        result = e.result

    # Parse into Script model
    final_data = result["content"]
    final_errors, _, _, _, _, _ = _validate_generated_script(final_data)
    if final_errors:
        raise ValueError("Reviewed script failed validation: " + "; ".join(final_errors))
    chosen_thumbnail_strategy = _validate_thumbnail_strategy_choice(
        final_data.get("thumbnail_strategy", ""),
        video_type=video_type,
        allowed_names=vt_config.allowed_thumbnail_strategies,
    )
    script = Script(
        title=final_data.get("title", plan.get("topic", "Untitled")),
        video_type=final_data.get("video_type", video_type),
        description=final_data.get("description", ""),
        tags=final_data.get("tags", []),
        hook=final_data.get("hook", ""),
        content_family=plan.get("content_family", final_data.get("content_family", "")),
        lead_magnet=plan.get("lead_magnet", final_data.get("lead_magnet", "")),
        low_ticket_offer=plan.get("low_ticket_offer", final_data.get("low_ticket_offer", "")),
        mid_ticket_offer=plan.get("mid_ticket_offer", final_data.get("mid_ticket_offer", "")),
        thumbnail_text=final_data.get("thumbnail_text", ""),
        thumbnail_brief=final_data.get("thumbnail_brief", ""),
        thumbnail_strategy=chosen_thumbnail_strategy,
        total_estimated_duration_seconds=final_data.get("total_estimated_duration_seconds", 0),
        music_track="",
        voice_variation=0,
        intra_transition="fade",
        sections=[
            ScriptSection(**s) for s in final_data.get("sections", [])
        ],
    )

    # Validate LLM visual slots
    for s in script.sections:
        if not s.slots:
            raise ValueError(f"Section {s.id} has no visual slots")
        if s != script.sections[0] and not s.transition_type:
            raise ValueError(f"Section {s.id} missing transition_type")

    # Per-section colors only when the channel opts in via section_color_palette.
    # Without a palette, clear any AI-emitted accent_color so the channel's
    # title_accent_color is used consistently — both section-level and
    # per-slot props (InfoSlide, backdrop figure scenes).
    channel_accent = config.style.text.get("title_accent_color")
    palette = config.style.text.get("section_color_palette")
    if palette:
        for i, section in enumerate(script.sections):
            if not section.accent_color:
                section.accent_color = palette[i % len(palette)]
    else:
        for section in script.sections:
            section.accent_color = None
            for slot in section.slots:
                if "accent_color" in slot.props and channel_accent:
                    slot.props["accent_color"] = channel_accent

    _inject_forced_slots(script, config.forced)
    save_script(workspace, script)
    logger.info(f"Script saved: {script.title} ({len(script.sections)} sections)")

    return script, result


_FORCED_SLOT_DEFAULTS: dict[str, dict] = {
    "TitleCard": {
        "visual": "title_card",
        "props": {"title": "", "subtitle": "", "accent_color": "#00D4FF"},
    },
    "FactHighlight": {
        "visual": "fact_highlight",
        "props": {"value": "42", "label": "test stat", "unit": "%", "accent_color": "#FFE500"},
    },
}

# Map from force name to visual type for lookup
_FORCE_TO_VISUAL = {"TitleCard": "title_card", "FactHighlight": "fact_highlight"}
FORCED_SLOT_NAMES = set(_FORCED_SLOT_DEFAULTS)


def _forced_slot_media(script: Script, section: ScriptSection) -> tuple[str, str]:
    title = next(
        (
            str(slot.props.get("title", "")).strip()
            for slot in section.slots
            if slot.visual == "title_banner" and slot.props.get("title")
        ),
        "",
    )
    subject = title or section.narration.split(".", 1)[0].strip() or script.title
    return (
        f"Realistic photo of {subject.rstrip('. ')}.",
        f"{subject} real photo".strip(),
    )


def _inject_forced_slots(script: Script, forced: set[str]) -> None:
    """Inject forced backdrop figure slots into sections that don't already have one."""
    forced_slot_names = forced & FORCED_SLOT_NAMES
    if not forced_slot_names:
        return

    present = set()
    for section in script.sections:
        for slot in section.slots:
            if slot.visual in VisualSlot.BACKDROP_FIGURE_TYPES:
                present.add(slot.visual)

    missing_visuals = {_FORCE_TO_VISUAL[name] for name in forced_slot_names}
    missing_visuals -= present
    if not missing_visuals:
        return

    available = list(script.sections)
    visual_to_force = {v: k for k, v in _FORCE_TO_VISUAL.items()}

    for visual_type in sorted(missing_visuals):
        if not available:
            logger.warning(f"test.force: no available section for {visual_type}")
            break
        section = available.pop(0)
        force_name = visual_to_force[visual_type]
        slot_data = dict(_FORCED_SLOT_DEFAULTS[force_name])
        prompt, keywords = _forced_slot_media(script, section)
        slot_data["prompt"] = prompt
        slot_data["keywords"] = keywords
        if force_name == "TitleCard":
            slot_data["props"] = {"title": script.title, "subtitle": "", "accent_color": "#00D4FF"}
        if visual_type == "title_card":
            section.slots.insert(0, VisualSlot(**slot_data))
        else:
            section.slots.append(VisualSlot(**slot_data))
        logger.info(f"test.force: injected {force_name} into section {section.id}")
