"""Stage 8: full-AI thumbnail generation + Gate #3 review."""

import logging
from pathlib import Path

from PIL import Image

import clients
import prompts
from core.reviewer import review_gate
from core.utils import Script, ChannelConfig, ThumbnailStrategyConfig
from settings import ASSETS_DIR


logger = logging.getLogger("video_factory")

THUMBNAIL_SIZE = (1280, 720)


def _thumbnail_strategy_by_name(
    config: ChannelConfig,
    strategy_name: str,
) -> ThumbnailStrategyConfig:
    for strategy in config.thumbnail_strategies:
        if strategy.name == strategy_name:
            return strategy
    available = ", ".join(strategy.name for strategy in config.thumbnail_strategies)
    raise ValueError(f"Unknown thumbnail strategy '{strategy_name}'. Available: {available}")


def _thumbnail_content_context(script: Script) -> str:
    parts: list[str] = []
    for section in script.sections:
        titles = [
            str(slot.props["title"])
            for slot in section.slots
            if slot.visual == "title_banner" and slot.props.get("title")
        ]
        subject = titles[0] if titles else section.narration.split(".", 1)[0]
        parts.append(f"Section {section.id}: {subject}")
    return "; ".join(parts)


def _thumbnail_reference_image(strategy: ThumbnailStrategyConfig) -> Path | None:
    if not strategy.reference_image:
        return None

    ref_path = Path(strategy.reference_image)
    if not ref_path.is_absolute():
        ref_path = ASSETS_DIR / ref_path
    if not ref_path.exists():
        raise FileNotFoundError(
            f"Thumbnail strategy '{strategy.name}' reference_image not found: {ref_path}"
        )
    return ref_path


def _thumbnail_reference_instruction(strategy: ThumbnailStrategyConfig) -> str:
    if not strategy.reference_instruction:
        raise ValueError(
            f"Thumbnail strategy '{strategy.name}' reference_instruction is required "
            "when reference_image is set"
        )
    return strategy.reference_instruction


def _validate_thumbnail_script_fields(script: Script) -> None:
    missing = []
    if not script.thumbnail_text:
        missing.append("thumbnail_text")
    if not script.thumbnail_brief:
        missing.append("thumbnail_brief")
    if not script.thumbnail_strategy:
        missing.append("thumbnail_strategy")
    if missing:
        raise ValueError(f"Script missing thumbnail fields: {', '.join(missing)}")


async def create_thumbnail(
    script: Script,
    config: ChannelConfig,
    workspace: Path,
) -> dict:
    """Create and review a full AI-rendered YouTube thumbnail."""
    _validate_thumbnail_script_fields(script)
    thumbnail_path = workspace / "thumbnail.png"
    strategy = _thumbnail_strategy_by_name(config, script.thumbnail_strategy)
    reference_image = _thumbnail_reference_image(strategy)
    reference_instruction = (
        _thumbnail_reference_instruction(strategy)
        if reference_image is not None
        else None
    )
    content_context = _thumbnail_content_context(script)
    logger.info(f"Thumbnail strategy: {strategy.name}")

    await _generate_ai_thumbnail(
        title=script.title,
        thumbnail_text=script.thumbnail_text,
        thumbnail_brief=script.thumbnail_brief,
        strategy_instruction=strategy.instruction,
        content_context=content_context,
        config=config,
        output_path=thumbnail_path,
        reference_image=reference_image,
        reference_instruction=reference_instruction,
        revision_notes="",
    )

    async def _regenerate(content, feedback):
        feedback_str = feedback.get("feedback", "") if isinstance(feedback, dict) else feedback
        await _generate_ai_thumbnail(
            title=script.title,
            thumbnail_text=script.thumbnail_text,
            thumbnail_brief=script.thumbnail_brief,
            strategy_instruction=strategy.instruction,
            content_context=content_context,
            config=config,
            output_path=thumbnail_path,
            reference_image=reference_image,
            reference_instruction=reference_instruction,
            revision_notes=feedback_str,
        )
        return content

    def _review_prompt(content):
        return prompts.thumbnail_review_prompt(
            title=script.title,
            video_type=script.video_type,
            thumbnail_text=script.thumbnail_text,
            thumbnail_strategy=strategy.name,
            thumbnail_brief=script.thumbnail_brief,
            strategy_instruction=strategy.instruction,
            content_context=content_context,
        )

    return await review_gate(
        content=None,
        review_prompt_fn=_review_prompt,
        system_instruction=prompts.thumbnail_review_system(),
        regenerate_fn=_regenerate,
        max_attempts=config.review_thresholds.thumbnail_max_attempts,
        gate_name="thumbnail_review",
        image_paths=[thumbnail_path],
    )


async def _generate_ai_thumbnail(
    title: str,
    thumbnail_text: str,
    thumbnail_brief: str,
    strategy_instruction: str,
    content_context: str,
    config: ChannelConfig,
    output_path: Path,
    reference_image: Path | None = None,
    reference_instruction: str | None = None,
    revision_notes: str = "",
) -> None:
    prompt = prompts.thumbnail_generation_prompt(
        title=title,
        thumbnail_text=thumbnail_text,
        thumbnail_brief=thumbnail_brief,
        strategy_instruction=strategy_instruction,
        content_context=content_context,
        channel_style=config.style.name,
        image_style_prompt_suffix=config.image_sourcing.style_prompt_suffix,
        revision_notes=revision_notes,
    )
    if reference_image is not None:
        if not reference_instruction:
            raise ValueError("reference_instruction is required when reference_image is provided")
        prompt += (
            "\n\nREFERENCE IMAGE INSTRUCTION:\n"
            f"{reference_instruction}"
        )

    result = await clients.generate_image_gemini(
        prompt=prompt,
        output_path=output_path,
        reference_image=reference_image,
        operation_label="thumbnail_generate",
    )
    if result is None or not output_path.exists():
        raise RuntimeError("Gemini thumbnail generation did not produce an image")

    img = Image.open(output_path).convert("RGB")
    if img.size != THUMBNAIL_SIZE:
        img = img.resize(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
        img.save(output_path, "PNG")
