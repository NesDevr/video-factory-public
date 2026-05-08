"""Stage 2a: Image sourcing — direct dispatch per script-specified source.

Each section gets script-specified image/video slots that rotate during playback.
After all images are sourced, Gate #2 reviews them with Gemini Vision.
"""

import asyncio
import hashlib
import io
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Literal

import httpx
from PIL import Image, ImageFilter, ImageOps

import clients
import prompts
from core.utils import meets_minimum_source_size, minimum_source_size
from core.reviewer import review_gate
from core.utils import (
    Script,
    ChannelConfig,
    VisualSlot,
    save_script,
    slot_requires_sourced_still,
)
from settings import settings

logger = logging.getLogger("video_factory")

GenerationLane = Literal["photo", "illustration"]

# Map unified visual types to image_source dispatch strings
_VISUAL_TO_SOURCE = {
    "google_photo": "serper",
    "stock_photo": "pexels",
    "ai_photo": "ai_gen",
    "ai_illustration": "ai_gen",
    "info_card": "ai_gen",
    "info_slide": "ai_gen",
    "b_roll": "pexels",
}

# Domains that serve watermarked previews — skip these in search results
_STOCK_DOMAINS = {
    "shutterstock.com", "gettyimages.com", "istockphoto.com",
    "alamy.com", "dreamstime.com", "123rf.com", "depositphotos.com",
    "stock.adobe.com",
}

_MAX_CONCURRENT_SOURCES = 6
_PEXELS_CANDIDATE_COUNT = 8
_SERPER_CANDIDATE_COUNT = 8


def _is_blank_media_prompt(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    return normalized in {"", "empty", "none", "null", "n/a", "placeholder"}


def _generation_style(config: ChannelConfig, is_illustration: bool) -> str:
    img_cfg = config.image_sourcing
    if is_illustration:
        return (
            img_cfg.illustration_style_prompt_suffix
            or img_cfg.style_prompt_suffix
        )
    return img_cfg.style_prompt_suffix


def _generation_lane_for_slot(
    slot: VisualSlot,
    config: ChannelConfig,
    *,
    respect_component_flags: bool = True,
) -> GenerationLane | None:
    """Classify a slot into the photo or illustration generation lane."""
    if slot.visual not in VisualSlot.SOURCEABLE_TYPES:
        return None
    if respect_component_flags and not slot_requires_sourced_still(slot, config):
        return None

    if slot.visual == "info_slide" and bool((slot.props or {}).get("source_as_photo")):
        return "photo"
    if slot.visual in VisualSlot.ILLUSTRATION_TYPES:
        return "illustration"
    return "photo"


def _generation_model(
    config: ChannelConfig,
    lane: GenerationLane,
) -> str:
    return config.image_sourcing.generation_model


def _generation_operation(lane: GenerationLane, *, retry: bool = False) -> str:
    if lane == "illustration":
        return "image_regeneration_illustration" if retry else "image_generate_illustration"
    return "image_regeneration" if retry else "image_generate"


def _minimum_reframe_source_size(target_size: tuple[int, int]) -> tuple[int, int]:
    min_w, min_h = minimum_source_size(target_size)
    return (max(640, min_w // 2), max(360, min_h // 2))


def _normalize_photo_bytes_for_target(
    image_bytes: bytes,
    *,
    target_size: tuple[int, int],
) -> bytes:
    with Image.open(io.BytesIO(image_bytes)) as source:
        img = source.convert("RGB")
    target_w, target_h = target_size
    if img.size == (target_w, target_h):
        return image_bytes

    background = ImageOps.fit(
        img,
        (target_w, target_h),
        method=Image.Resampling.LANCZOS,
    ).filter(ImageFilter.GaussianBlur(24))
    foreground = ImageOps.contain(
        img,
        (target_w, target_h),
        method=Image.Resampling.LANCZOS,
    )
    x = (target_w - foreground.width) // 2
    y = (target_h - foreground.height) // 2
    background.paste(foreground, (x, y))

    buffer = io.BytesIO()
    background.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def _generation_prompt(
    *,
    keywords: str,
    prompt: str,
    use_illustration: bool,
) -> str:
    base_prompt = (prompt or keywords).strip()
    if not base_prompt:
        raise ValueError("Image generation requires a prompt or keywords")
    if not use_illustration:
        return base_prompt
    return f"Simple non-photoreal illustration of {base_prompt}."


def _generation_request_preview(
    *,
    keywords: str,
    prompt: str,
    lane: GenerationLane,
    config: ChannelConfig,
    retry: bool = False,
) -> dict[str, str]:
    gen_prompt = _generation_prompt(
        keywords=keywords,
        prompt=prompt,
        use_illustration=lane == "illustration",
    )
    suffix = _generation_style(config, lane == "illustration")
    if suffix:
        gen_prompt += f", {suffix}"
    return {
        "model": _generation_model(config, lane),
        "operation": _generation_operation(lane, retry=retry),
        "prompt": gen_prompt,
    }


def _build_sections_context(
    script: Script,
    raw_dir: Path,
    videos_dir: Path,
    *,
    visual_overrides: dict[tuple[int, int], str] | None = None,
    prompt_overrides: dict[tuple[int, int], str] | None = None,
) -> list[dict]:
    sections_context = []
    for section in script.sections:
        non_overlay_slots = section.non_overlay_slots
        for sub_idx, slot in enumerate(non_overlay_slots, start=1):
            if slot.visual in VisualSlot.CHART_TYPES:
                continue

            file_label = f"section_{section.id:03d}_{sub_idx:02d}"
            img_path = raw_dir / f"{file_label}.jpg"
            if not img_path.exists():
                img_path = raw_dir / f"{file_label}.png"
            if not img_path.exists():
                continue

            visual_type = (
                visual_overrides.get((section.id, sub_idx), slot.visual)
                if visual_overrides else slot.visual
            )
            is_b_roll = visual_type == "b_roll" and (videos_dir / f"{file_label}.mp4").exists()
            key = (section.id, sub_idx)
            sections_context.append({
                "section_id": section.id,
                "sub_image_index": sub_idx,
                "narration": section.narration[:400],
                "visual_type": visual_type,
                "is_section_opener": sub_idx == 1,
                "text_only": slot.visual == "text_only_slide",
                "prompt": (
                    prompt_overrides.get(key, slot.prompt)
                    if prompt_overrides else slot.prompt
                ),
                "image_search_keywords": slot.keywords,
                "image_filename": img_path.name,
                "is_b_roll": is_b_roll,
            })
    return sections_context


def _is_stock_domain(url: str) -> bool:
    """Check if a URL belongs to a known stock-photo domain."""
    url_lower = url.lower()
    return any(domain in url_lower for domain in _STOCK_DOMAINS)


def _slot_marker(slot: VisualSlot) -> tuple[str, str, str, str, str]:
    return (
        slot.visual,
        slot.prompt,
        slot.keywords,
        slot.visual_policy,
        repr(slot.props or {}),
    )


def _apply_slot_rewrite(
    slot: VisualSlot,
    *,
    visual: str | None = None,
    prompt: str | None = None,
    keywords: str | None = None,
    visual_policy: str | None = None,
    props: dict | None = None,
) -> bool:
    before = _slot_marker(slot)
    if visual is not None:
        slot.visual = visual
    if prompt is not None:
        slot.prompt = prompt
    if keywords is not None:
        slot.keywords = keywords
    if visual_policy is not None:
        slot.visual_policy = visual_policy
    if props is not None:
        slot.props = props
    return before != _slot_marker(slot)


def _image_source_for_slot(slot: VisualSlot) -> str:
    preferred_photo_source = str((slot.props or {}).get("photo_source", "")).strip()
    if preferred_photo_source:
        return _VISUAL_TO_SOURCE.get(preferred_photo_source, "ai_gen")
    return _VISUAL_TO_SOURCE.get(slot.visual, "ai_gen")


def _apply_ai_prompt_preview_slide(
    *,
    section,
    slot: VisualSlot,
    sub_idx: int,
    lane: GenerationLane,
    config: ChannelConfig,
    retry: bool = False,
) -> tuple[dict[str, str], bool]:
    request = _generation_request_preview(
        keywords=slot.keywords,
        prompt=slot.prompt,
        lane=lane,
        config=config,
        retry=retry,
    )
    title = f"AI Image Prompt s{section.id}.{sub_idx + 1}"
    text = "\n".join(
        [
            f"Model: {request['model']}",
            f"Operation: {request['operation']}",
            f"Visual: {slot.visual}",
            f"Policy: {slot.visual_policy}",
            "",
            "Prompt:",
            request["prompt"],
        ]
    )
    changed = _apply_slot_rewrite(
        slot,
        visual="text_only_slide",
        prompt="",
        keywords="",
        props={"title": title, "text": text},
    )
    slot.props.update({
        "variant": "ai_prompt_preview",
        "model": request["model"],
        "operation": request["operation"],
        "prompt_text": request["prompt"],
    })
    return request, changed


def _apply_source_miss_preview_slide(
    *,
    section,
    slot: VisualSlot,
    sub_idx: int,
    image_source: str,
) -> tuple[dict[str, str], bool]:
    title = f"Image Source Request s{section.id}.{sub_idx + 1}"
    prompt_text = slot.prompt.strip() or "(none)"
    keywords_text = slot.keywords.strip() or "(none)"
    text = "\n".join(
        [
            f"Source: {image_source}",
            f"Visual: {slot.visual}",
            f"Policy: {slot.visual_policy}",
            "",
            "Prompt:",
            prompt_text,
            "",
            "Search keywords:",
            keywords_text,
        ]
    )
    changed = _apply_slot_rewrite(
        slot,
        visual="text_only_slide",
        prompt="",
        keywords="",
        props={"title": title, "text": text},
    )
    slot.props.update({
        "variant": "ai_prompt_preview",
        "model": f"(none; {image_source} source)",
        "operation": "image_source_preview",
        "prompt_text": f"{prompt_text}\n\nSearch keywords:\n{keywords_text}",
    })
    return {
        "model": slot.props["model"],
        "operation": slot.props["operation"],
    }, changed


def _plan_slot_visual(*, section, slot: VisualSlot) -> tuple[str, bool]:
    policy = slot.visual_policy or "source_as_written"
    if policy not in VisualSlot.VISUAL_POLICIES:
        raise ValueError(f"Unknown visual_policy '{policy}' for section {section.id}")

    if slot.visual == "text_only_slide" and (slot.props or {}).get("variant") != "ai_prompt_preview":
        raise ValueError(
            f"Section {section.id}: text_only_slide is reserved for internal AI prompt preview only"
        )

    if slot.visual == "info_slide" and _is_blank_media_prompt(slot.prompt):
        raise ValueError(
            f"Section {section.id}: info_slide requires an image prompt; "
            "use an image-backed slot instead of an image-less text slide"
        )

    if policy == "source_as_written":
        return policy, False

    if policy == "photo_backed_info_slide":
        if slot.visual != "info_slide":
            raise ValueError(
                f"visual_policy photo_backed_info_slide requires info_slide in section {section.id}"
            )
        props = dict(slot.props or {})
        props["source_as_photo"] = True
        props["photo_source"] = "google_photo"
        return policy, _apply_slot_rewrite(
            slot,
            prompt=slot.prompt,
            keywords=slot.keywords,
            props=props,
        )

    if policy in {"google_photo_exact_action", "literal_google_photo"}:
        return policy, _apply_slot_rewrite(
            slot,
            visual="google_photo",
            prompt=slot.prompt,
            keywords=slot.keywords,
        )

    if policy == "single_pose_ai_photo":
        return policy, _apply_slot_rewrite(
            slot,
            visual="ai_photo",
            prompt=slot.prompt,
            keywords=slot.keywords,
        )

    raise ValueError(f"Unhandled visual_policy '{policy}' for section {section.id}")


async def source_images(
    script: Script,
    config: ChannelConfig,
    workspace: Path,
) -> dict:
    """Source multiple images per section using the script-specified source.

    Returns review gate result dict.
    """
    raw_dir = workspace / "images" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    sourcing_log = []  # tracks per-image sourcing actions
    seen_hashes: set[str] = set()  # content-hash dedup across sections

    videos_dir = workspace / "videos" / "raw"
    videos_dir.mkdir(parents=True, exist_ok=True)
    target_size = tuple(config.video.resolution)
    fps = config.video.fps
    script_mutated = False

    # Build task descriptors, filtering out cached images/videos
    descriptors = []
    for section in script.sections:
        non_overlay_slots = section.non_overlay_slots
        num_subs = len(non_overlay_slots) or 1

        for sub_idx, slot in enumerate(non_overlay_slots):
            file_label = f"section_{section.id:03d}_{sub_idx + 1:02d}"
            policy, changed = _plan_slot_visual(section=section, slot=slot)
            script_mutated = script_mutated or changed
            keywords = slot.keywords
            prompt = slot.prompt

            # Components rendered by Remotion — no sourced still needed
            if slot.visual in VisualSlot.COMPONENT_TYPES and not slot_requires_sourced_still(slot, config):
                logger.info(
                    f"Inline component slot s{section.id}.{sub_idx + 1} "
                    f"({slot.visual}) — skipping image source"
                )
                sourcing_log.append({
                    "section_id": section.id,
                    "sub_image_index": sub_idx + 1,
                    "file": None,
                    "keywords": keywords,
                    "source": "remotion_inline",
                })
                continue

            lane = _generation_lane_for_slot(slot, config)
            if lane is None:
                logger.info(
                    f"Inline component slot s{section.id}.{sub_idx + 1} "
                    f"({slot.visual}) — illustration disabled, skipping image source"
                )
                sourcing_log.append({
                    "section_id": section.id,
                    "sub_image_index": sub_idx + 1,
                    "file": None,
                    "keywords": keywords,
                    "source": "remotion_component",
                })
                continue

            image_source = _image_source_for_slot(slot)
            if config.test.preview_ai_image_prompts and image_source == "ai_gen":
                request, changed = _apply_ai_prompt_preview_slide(
                    section=section,
                    slot=slot,
                    sub_idx=sub_idx,
                    lane=lane,
                    config=config,
                )
                script_mutated = script_mutated or changed
                sourcing_log.append({
                    "section_id": section.id,
                    "sub_image_index": sub_idx + 1,
                    "file": None,
                    "keywords": "",
                    "source": "ai_prompt_preview",
                    "model": request["model"],
                    "operation": request["operation"],
                })
                continue

            # B-roll video slots
            if slot.visual == "b_roll":
                video_path = videos_dir / f"{file_label}.mp4"
                if video_path.exists():
                    logger.info(f"B-roll already exists: {video_path.name}")
                    sourcing_log.append({
                        "section_id": section.id,
                        "sub_image_index": sub_idx + 1,
                        "file": video_path.name,
                        "keywords": keywords,
                        "source": "pexels_video_cached",
                    })
                    continue
                target_dur = section.estimated_duration_seconds / num_subs
                descriptors.append({
                    "section": section,
                    "sub_idx": sub_idx,
                    "slot": slot,
                    "keywords": keywords,
                    "prompt": "",
                    "img_path": None,
                    "b_roll": True,
                    "lane": "photo",
                    "fallback_to_illustration": False,
                    "video_path": video_path,
                    "target_duration": target_dur,
                })
                continue

            # Image-based slots (google_photo, stock_photo, ai_photo, ai_illustration, info_card, info_slide)
            # Check for cached video (e.g. from a previous run)
            video_path = videos_dir / f"{file_label}.mp4"
            if video_path.exists():
                logger.info(f"Video exists for slot: {video_path.name} — skipping image source")
                sourcing_log.append({
                    "section_id": section.id,
                    "sub_image_index": sub_idx + 1,
                    "file": video_path.name,
                    "keywords": keywords,
                    "source": "video_cached",
                })
                continue

            img_path = raw_dir / f"{file_label}.jpg"
            if img_path.exists():
                logger.info(f"Image already exists: {img_path.name}")
                sourcing_log.append({
                    "section_id": section.id,
                    "sub_image_index": sub_idx + 1,
                    "file": img_path.name,
                    "keywords": keywords,
                    "source": "cached",
                })
                continue

            descriptors.append({
                "section": section,
                "sub_idx": sub_idx,
                "slot": slot,
                "keywords": keywords,
                "prompt": prompt,
                "img_path": img_path,
                "b_roll": False,
                "lane": lane,
                "allow_generation_fallback": (
                    slot.visual not in {"google_photo"}
                    and policy not in {
                        "literal_google_photo",
                        "google_photo_exact_action",
                        "photo_backed_info_slide",
                    }
                ),
                "fallback_to_illustration": False,
            })

    # Source all non-cached images/videos in parallel (capped by semaphore)
    sem = asyncio.Semaphore(_MAX_CONCURRENT_SOURCES)

    async def _source_one(desc: dict, client: httpx.AsyncClient) -> None:
        nonlocal script_mutated
        section = desc["section"]
        sub_idx = desc["sub_idx"]
        keywords = desc["keywords"]

        if desc["b_roll"]:
            # B-roll video sourcing
            video_path = desc["video_path"]
            async with sem:
                success = await _search_pexels_video(
                    keywords=keywords,
                    output_path=video_path,
                    client=client,
                    seen_hashes=seen_hashes,
                    target_duration=desc["target_duration"],
                    target_size=target_size,
                    fps=fps,
                )

            if success:
                # Extract a frame to images/raw/ so the review gate can check relevance
                frame_path = raw_dir / f"section_{section.id:03d}_{sub_idx + 1:02d}.jpg"
                _extract_video_frame(video_path, frame_path)
                sourcing_log.append({
                    "section_id": section.id,
                    "sub_image_index": sub_idx + 1,
                    "file": video_path.name,
                    "keywords": keywords,
                    "source": "pexels_video",
                })
                return

            # Fallback: source as normal image instead
            logger.warning(
                f"Section {section.id} B-roll failed, falling back to image"
            )
            desc["img_path"] = raw_dir / f"section_{section.id:03d}_{sub_idx + 1:02d}.jpg"

        # Normal image sourcing — dispatch on slot.visual
        img_path = desc["img_path"]
        slot = desc["slot"]
        image_source = _image_source_for_slot(slot)
        lane = desc["lane"]

        async with sem:
            source_used = await _source_single_image(
                keywords=desc.get("keywords", keywords),
                prompt=desc.get("prompt", ""),
                image_source=image_source,
                config=config,
                output_path=img_path,
                client=client,
                seen_hashes=seen_hashes,
                lane=lane,
                allow_generation_fallback=desc.get("allow_generation_fallback", True),
                fallback_to_illustration=desc.get("fallback_to_illustration", False),
            )

        if source_used:
            sourcing_log.append({
                "section_id": section.id,
                "sub_image_index": sub_idx + 1,
                "file": img_path.name,
                "keywords": keywords,
                "source": source_used,
            })
        else:
            if (
                config.test.preview_ai_image_prompts
            ):
                if desc.get("allow_generation_fallback", True):
                    request, changed = _apply_ai_prompt_preview_slide(
                        section=section,
                        slot=slot,
                        sub_idx=sub_idx,
                        lane=lane,
                        config=config,
                    )
                else:
                    request, changed = _apply_source_miss_preview_slide(
                        section=section,
                        slot=slot,
                        sub_idx=sub_idx,
                        image_source=image_source,
                    )
                script_mutated = script_mutated or changed
                sourcing_log.append({
                    "section_id": section.id,
                    "sub_image_index": sub_idx + 1,
                    "file": None,
                    "keywords": "",
                    "source": "ai_prompt_preview",
                    "model": request["model"],
                    "operation": request["operation"],
                })
                return
            raise RuntimeError(
                f"Section {section.id} sub-image {sub_idx + 1}: "
                f"source failed for visual {slot.visual} with policy {slot.visual_policy}"
            )

    if descriptors:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(60, connect=10),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            follow_redirects=True,
        ) as client:
            await asyncio.gather(*[
                _source_one(desc, client) for desc in descriptors
            ])

    # ── Gate #2: Image Relevance Review ───────────────────────────
    image_paths = sorted(raw_dir.glob("section_*_*.jpg"))
    if not image_paths:
        image_paths = sorted(raw_dir.glob("section_*_*.png"))

    sections_context = _build_sections_context(script, raw_dir, videos_dir)

    def _review_prompt(content):
        return prompts.image_review_prompt(sections_context)

    try:
        result = await review_gate(
            content=None,
            review_prompt_fn=_review_prompt,
            system_instruction=prompts.image_review_system(),
            max_attempts=1,
            gate_name="image_review",
            image_paths=image_paths,
        )
        result["sourcing_log"] = sourcing_log
        return result
    finally:
        if script_mutated:
            save_script(workspace, script)


async def _source_single_image(
    keywords: str,
    prompt: str,
    image_source: str,
    config: ChannelConfig,
    output_path: Path,
    client: httpx.AsyncClient,
    seen_hashes: set[str],
    lane: GenerationLane,
    allow_generation_fallback: bool = True,
    fallback_to_illustration: bool = False,
) -> str | None:
    """Use the script-specified source, falling back to generation when allowed.

    When *lane* is illustration, skip web/stock sources and go straight to AI
    generation with the illustration style prompt. Photo lanes fall back to AI
    generation unless allow_generation_fallback is false.
    """
    if lane == "photo":
        try:
            if image_source == "serper":
                success = await _search_serper(
                    keywords,
                    prompt,
                    output_path,
                    client,
                    seen_hashes,
                    tuple(config.video.resolution),
                )
            elif image_source == "pexels":
                success = await _search_pexels(
                    keywords,
                    prompt,
                    output_path,
                    client,
                    seen_hashes,
                    tuple(config.video.resolution),
                )
            elif image_source == "ai_gen":
                success = False  # handled below
            else:
                return None

            if success:
                logger.info(f"Sourced {output_path.name} from {image_source}")
                return image_source
        except Exception as e:
            logger.warning(f"{output_path.name}: {image_source} failed: {e}")
        if not allow_generation_fallback:
            return None
        if config.test.preview_ai_image_prompts:
            return None

    if config.test.preview_ai_image_prompts:
        return None

    # Generate with AI generation. Use illustration style when flagged.
    try:
        effective_lane: GenerationLane = (
            "illustration"
            if lane == "illustration" or fallback_to_illustration
            else "photo"
        )
        request = _generation_request_preview(
            keywords=keywords,
            prompt=prompt,
            lane=effective_lane,
            config=config,
        )
        if effective_lane == "illustration":
            logger.info(f"Sourcing illustration for {output_path.name}")
        result = await clients.generate_image_gemini(
            request["prompt"], output_path,
            model=request["model"],
            aspect_ratio="16:9",
            image_size="1K",
            operation_label=request["operation"],
        )
        if result is not None:
            logger.info(
                f"Sourced {output_path.name} from ai_gen"
                f"{'(illustration)' if effective_lane == 'illustration' else ''}"
            )
            return "ai_gen"
    except Exception as e:
        logger.warning(f"{output_path.name}: ai_gen fallback failed: {e}")

    return None


async def _search_serper(
    keywords: str,
    prompt: str,
    output_path: Path,
    client: httpx.AsyncClient,
    seen_hashes: set[str],
    target_size: tuple[int, int],
) -> bool:
    """Search for images using Serper.dev (Google Image Search wrapper)."""
    with tempfile.TemporaryDirectory(prefix="vf_serper_candidates_") as tmp_dir:
        candidate_records = await _collect_serper_candidates(
            keywords=keywords,
            output_name=output_path.name,
            client=client,
            seen_hashes=seen_hashes,
            target_size=target_size,
            tmp_dir=Path(tmp_dir),
        )
        candidate_paths = [record["path"] for record in candidate_records]

        if not candidate_paths:
            return False

        winner = await _select_photo_candidate(
            source_name="Serper",
            keywords=keywords,
            prompt=prompt,
            candidate_paths=candidate_paths,
            operation_label="serper_candidate_selection",
        )
        if winner is None:
            logger.info(f"No acceptable Serper candidate for {output_path.name}")
            return False

        return _finalize_selected_photo_candidate(
            winner=winner,
            output_path=output_path,
            seen_hashes=seen_hashes,
            source_name="Serper",
        )



async def _search_pexels(
    keywords: str,
    prompt: str,
    output_path: Path,
    client: httpx.AsyncClient,
    seen_hashes: set[str],
    target_size: tuple[int, int],
) -> bool:
    """Search Pexels API and select the best image candidate."""
    with tempfile.TemporaryDirectory(prefix="vf_pexels_candidates_") as tmp_dir:
        candidate_records = await _collect_pexels_candidates(
            keywords=keywords,
            output_name=output_path.name,
            client=client,
            seen_hashes=seen_hashes,
            target_size=target_size,
            tmp_dir=Path(tmp_dir),
        )
        candidate_paths = [record["path"] for record in candidate_records]

        if not candidate_paths:
            return False

        winner = await _select_photo_candidate(
            source_name="Pexels",
            keywords=keywords,
            prompt=prompt,
            candidate_paths=candidate_paths,
            operation_label="pexels_candidate_selection",
        )
        if winner is None:
            logger.info(f"No acceptable Pexels candidate for {output_path.name}")
            return False

        return _finalize_selected_photo_candidate(
            winner=winner,
            output_path=output_path,
            seen_hashes=seen_hashes,
            source_name="Pexels",
        )


def _finalize_selected_photo_candidate(
    *,
    winner: Path,
    output_path: Path,
    seen_hashes: set[str],
    source_name: str,
) -> bool:
    selected_bytes = winner.read_bytes()
    seen_hashes.add(hashlib.md5(selected_bytes).hexdigest())
    output_path.write_bytes(selected_bytes)
    logger.info(
        f"Selected {source_name} candidate {winner.name} for {output_path.name}"
    )
    return True


async def _select_photo_candidate(
    *,
    source_name: str,
    keywords: str,
    prompt: str,
    candidate_paths: list[Path],
    operation_label: str,
) -> Path | None:
    review = await clients.review_with_vision(
        prompt=prompts.pexels_candidate_selection_prompt(
            keywords=keywords,
            prompt=prompt,
            num_images=len(candidate_paths),
        ),
        image_paths=candidate_paths,
        operation_label=operation_label,
    )
    if not review.get("approved", False):
        logger.info(
            f"{source_name} candidates rejected "
            f"(reason: {review.get('reason', 'n/a')})"
        )
        return None

    winner_index = review.get("winner_index")
    if type(winner_index) is not int:
        raise ValueError(f"{source_name} candidate review missing winner_index: {review}")
    if winner_index < 1 or winner_index > len(candidate_paths):
        raise ValueError(f"{source_name} candidate winner_index out of range: {review}")

    logger.info(
        f"{source_name} candidate {winner_index}/{len(candidate_paths)} selected "
        f"(reason: {review.get('reason', 'n/a')})"
    )
    return candidate_paths[winner_index - 1]


async def _collect_serper_candidates(
    *,
    keywords: str,
    output_name: str,
    client: httpx.AsyncClient,
    seen_hashes: set[str],
    target_size: tuple[int, int],
    tmp_dir: Path,
    limit: int = _SERPER_CANDIDATE_COUNT,
) -> list[dict[str, str | Path]]:
    if not settings.serper_api_key:
        return []

    resp = await client.post(
        "https://google.serper.dev/images",
        headers={
            "X-API-KEY": settings.serper_api_key,
            "Content-Type": "application/json",
        },
        json={
            "q": keywords,
            "num": 10,
            "imageType": "photo",
        },
    )
    resp.raise_for_status()
    data = resp.json()
    images = data.get("images", [])
    if not images:
        return []

    candidate_hashes: set[str] = set()
    candidates: list[dict[str, str | Path]] = []
    for idx, img_result in enumerate(images, start=1):
        if len(candidates) >= limit:
            break

        img_url = img_result.get("imageUrl", "")
        source_url = img_result.get("source", "")
        if not img_url:
            continue
        if _is_stock_domain(img_url) or _is_stock_domain(source_url):
            logger.debug(f"Skipping stock domain: {source_url}")
            continue

        try:
            image_bytes = await _download_valid_image_bytes(
                client,
                img_url,
                target_size,
                output_name,
            )
        except Exception as e:
            logger.debug(f"Skipping Serper candidate download failure: {e}")
            continue
        if image_bytes is None:
            continue

        content_hash = hashlib.md5(image_bytes).hexdigest()
        if content_hash in seen_hashes or content_hash in candidate_hashes:
            continue
        candidate_hashes.add(content_hash)

        candidate_path = tmp_dir / f"serper_{idx:02d}.jpg"
        candidate_path.write_bytes(image_bytes)
        candidates.append({"path": candidate_path, "source": "serper"})

    return candidates


async def _collect_pexels_candidates(
    *,
    keywords: str,
    output_name: str,
    client: httpx.AsyncClient,
    seen_hashes: set[str],
    target_size: tuple[int, int],
    tmp_dir: Path,
    limit: int = _PEXELS_CANDIDATE_COUNT,
) -> list[dict[str, str | Path]]:
    if not settings.pexels_api_key:
        return []

    resp = await client.get(
        "https://api.pexels.com/v1/search",
        params={
            "query": keywords,
            "per_page": limit,
            "orientation": "landscape",
        },
        headers={"Authorization": settings.pexels_api_key},
    )
    resp.raise_for_status()
    data = resp.json()
    photos = data.get("photos", [])
    if not photos:
        return []

    candidate_hashes: set[str] = set()
    candidates: list[dict[str, str | Path]] = []
    for idx, photo in enumerate(photos, start=1):
        img_url = photo.get("src", {}).get("large2x", "")
        if not img_url:
            continue

        try:
            image_bytes = await _download_valid_image_bytes(
                client,
                img_url,
                target_size,
                output_name,
            )
        except Exception as e:
            logger.debug(f"Skipping Pexels candidate download failure: {e}")
            continue
        if image_bytes is None:
            continue

        content_hash = hashlib.md5(image_bytes).hexdigest()
        if content_hash in seen_hashes or content_hash in candidate_hashes:
            continue
        candidate_hashes.add(content_hash)

        candidate_path = tmp_dir / f"pexels_{idx:02d}.jpg"
        candidate_path.write_bytes(image_bytes)
        candidates.append({"path": candidate_path, "source": "pexels"})

    return candidates


def _validated_candidate_record(
    review: dict,
    *,
    key: str,
    candidate_records: list[dict[str, str | Path]],
    source_name: str,
) -> dict[str, str | Path] | None:
    index = review.get(key)
    if index is None:
        return None
    if type(index) is not int:
        raise ValueError(f"{source_name} review missing valid {key}: {review}")
    if index < 1 or index > len(candidate_records):
        raise ValueError(f"{source_name} review {key} out of range: {review}")
    return candidate_records[index - 1]


def _extract_video_frame(video_path: Path, frame_path: Path) -> bool:
    """Extract a frame from a video at 1s for review purposes."""
    cmd = [
        settings.ffmpeg_path, "-y",
        "-i", str(video_path),
        "-ss", "1", "-frames:v", "1",
        "-q:v", "2",
        str(frame_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning(f"Frame extraction failed for {video_path.name}")
        return False
    return True


async def _search_pexels_video(
    keywords: str,
    output_path: Path,
    client: httpx.AsyncClient,
    seen_hashes: set[str],
    target_duration: float,
    target_size: tuple[int, int],
    fps: int,
) -> bool:
    """Search Pexels Video API and download+prepare a B-roll clip."""
    if not settings.pexels_api_key:
        return False

    try:
        resp = await client.get(
            "https://api.pexels.com/v1/videos/search",
            params={"query": keywords, "per_page": 5, "orientation": "landscape"},
            headers={"Authorization": settings.pexels_api_key},
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        status = e.response.status_code if e.response is not None else "unknown"
        logger.warning(
            f"Pexels video search failed ({status}) for query {keywords!r}; "
            "falling back to still image sourcing"
        )
        return False
    except httpx.HTTPError as e:
        logger.warning(
            f"Pexels video search transport error for query {keywords!r}: {e}; "
            "falling back to still image sourcing"
        )
        return False
    data = resp.json()

    videos = data.get("videos", [])
    if not videos:
        return False

    tw, th = target_size

    for video in videos:
        # Skip videos shorter than what we need
        video_duration = video.get("duration", 0)
        if video_duration < target_duration:
            continue

        # Find best HD video file (closest to target width, >= 1280px)
        candidates = [
            vf for vf in video.get("video_files", [])
            if vf.get("width", 0) >= 1280
            and vf.get("file_type", "") == "video/mp4"
        ]
        if not candidates:
            continue

        # Pick the file closest to target width (prefer smaller to save bandwidth)
        candidates.sort(key=lambda vf: abs(vf["width"] - tw))
        best_file = candidates[0]
        download_url = best_file.get("link", "")
        if not download_url:
            continue

        # Dedup by video ID
        video_id = str(video.get("id", ""))
        if video_id and video_id in seen_hashes:
            continue
        if video_id:
            seen_hashes.add(video_id)

        success = await _download_and_prepare_video(
            client, download_url, output_path,
            target_duration, target_size, fps,
        )
        if success:
            return True

    return False


async def _download_and_prepare_video(
    client: httpx.AsyncClient,
    url: str,
    output_path: Path,
    target_duration: float,
    target_size: tuple[int, int],
    fps: int,
) -> bool:
    """Download a video and prepare it (trim, scale, crop) for the assembler."""
    try:
        resp = await client.get(url, timeout=60)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"B-roll download failed: {e}")
        return False

    # Write to temp file, then FFmpeg process into final output
    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    try:
        tmp.write(resp.content)
        tmp.close()

        cmd = _build_browser_safe_broll_encode_cmd(
            input_path=Path(tmp.name),
            output_path=output_path,
            target_duration=target_duration,
            target_size=target_size,
            fps=fps,
        )
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.warning(f"B-roll encode failed: {result.stderr[-300:]}")
            return False

        logger.info(f"B-roll prepared: {output_path.name} ({target_duration:.1f}s)")
        return True
    finally:
        Path(tmp.name).unlink(missing_ok=True)


def _build_browser_safe_broll_encode_cmd(
    *,
    input_path: Path,
    output_path: Path,
    target_duration: float,
    target_size: tuple[int, int],
    fps: int,
) -> list[str]:
    w, h = target_size
    vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
    return [
        settings.ffmpeg_path,
        "-y",
        "-i",
        str(input_path),
        "-vf",
        vf,
        "-t",
        f"{target_duration:.3f}",
        "-r",
        str(fps),
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "18",
        "-profile:v",
        "high",
        "-level:v",
        "4.0",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-an",
        str(output_path),
    ]


async def _try_download_image(
    client: httpx.AsyncClient,
    img_url: str,
    output_path: Path,
    seen_hashes: set[str],
    target_size: tuple[int, int],
) -> bool:
    """Download an image URL and validate it's a real image with PIL before saving."""
    try:
        image_bytes = await _download_valid_image_bytes(
            client,
            img_url,
            target_size,
            output_path.name,
        )
        if image_bytes is None:
            return False

        # Content-hash dedup: skip if we already saved this exact image
        content_hash = hashlib.md5(image_bytes).hexdigest()
        if content_hash in seen_hashes:
            return False
        seen_hashes.add(content_hash)

        output_path.write_bytes(image_bytes)
        return True
    except Exception:
        return False


async def _download_valid_image_bytes(
    client: httpx.AsyncClient,
    img_url: str,
    target_size: tuple[int, int],
    output_name: str,
) -> bytes | None:
    img_resp = await client.get(img_url, timeout=20)
    img_resp.raise_for_status()

    try:
        img = Image.open(io.BytesIO(img_resp.content))
        width, height = img.size
        img.verify()
    except Exception:
        return None

    if width == target_size[0] and height == target_size[1]:
        return img_resp.content

    if not meets_minimum_source_size(width, height, target_size):
        reframe_min_w, reframe_min_h = _minimum_reframe_source_size(target_size)
        if width >= reframe_min_w and height >= reframe_min_h:
            logger.info(
                f"Reframing lower-resolution image for {output_name}: "
                f"{width}x{height} into {target_size[0]}x{target_size[1]}"
            )
            return _normalize_photo_bytes_for_target(
                img_resp.content,
                target_size=target_size,
            )
        min_w, min_h = minimum_source_size(target_size)
        logger.info(
            f"Skipping low-resolution image for {output_name}: "
            f"{width}x{height} below {min_w}x{min_h}"
        )
        return None

    return _normalize_photo_bytes_for_target(
        img_resp.content,
        target_size=target_size,
    )
