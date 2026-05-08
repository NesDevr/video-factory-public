"""Prompt templates for all pipeline stages and review gates."""

import json
from textwrap import dedent

from settings import get_remotion_compositions


def _color_palette_instruction(palette: list[str] | None) -> str:
    """Build the per-section color assignment instruction if a palette is configured."""
    if not palette:
        return ""
    colors = ", ".join(palette)
    return f"""SECTION COLORS — Assign each section an accent_color from this palette: [{colors}]
Choose the color that best fits each section's mood or topic (e.g., green for health/nature,
red for warnings/urgency, blue for science/data, amber for warmth/nostalgia). You may reuse
colors, but try to vary them across consecutive sections for visual rhythm.

"""


def _available_components_str() -> str:
    """Format available Remotion compositions for prompt injection."""
    comps = get_remotion_compositions()
    if not comps:
        raise RuntimeError("No Remotion compositions found — is Root.tsx missing?")
    return ", ".join(f'"{c}"' for c in comps)


def _system_prompt(
    *,
    role: str,
) -> str:
    return f"You are a {role}."


# ---------------------------------------------------------------------------
# Stage 0 — Topic selection
# ---------------------------------------------------------------------------

def topic_selection_system() -> str:
    return _system_prompt(role="topic strategist")


def topic_selection_prompt(
    channel_name: str,
    niche_focus: str,
    audience: str,
    example_topics: list[str],
    avoid_topics: list[str],
    video_types: dict,
    past_topics: list[str],
    language: str,
    preferred_type: str = "",
    target_duration_minutes: float = 7,
    sections_range: list[int] | None = None,
    content_families: list[dict[str, str]] | None = None,
    preferred_content_family: str = "",
) -> str:
    examples_str = "\n".join(f"  - {t}" for t in example_topics) if example_topics else "  (none)"
    avoid_str = "\n".join(f"  - {t}" for t in avoid_topics) if avoid_topics else "  (none)"
    past_str = "\n".join(f"  - {t}" for t in past_topics[-20:]) if past_topics else "  (none yet)"
    type_names = [name for name, cfg in video_types.items() if cfg.get("enabled", False)]
    types_str = "\n".join(
        f"  - {name}: {cfg.get('section_style', '')} | {cfg.get('pacing', '')} (example: {cfg.get('example', '')})"
        + (" ← PREFERRED" if name == preferred_type else "")
        for name, cfg in video_types.items()
        if cfg.get("enabled", False)
    )
    preferred_line = (
        f"\nPREFERRED VIDEO TYPE: {preferred_type}\n"
        f"Pick a topic that works well as a \"{preferred_type}\" video. You MAY choose a different\n"
        f"type if the topic truly doesn't fit, but prefer \"{preferred_type}\" when possible.\n"
        if preferred_type else ""
    )
    video_type_enum = "|".join(type_names) if type_names else "listicle|narrative"
    sr = sections_range or [3, 8]
    content_family_block = _format_content_family_options(
        content_families,
        preferred_content_family,
    )
    if content_families:
        has_family_offers = any(
            family.get("lead_magnet") or family.get("low_ticket_offer")
            for family in content_families
        )
        content_family_instruction = (
            "3. If content families are provided, the topic MUST fit exactly one of them"
            + (
                " and the selected family should make sense for the lead magnet / low-ticket offer pairing.\n"
                if has_family_offers else ".\n"
            )
            + "4. Write a brief angle/hook that makes it clickable\n"
            + "5. Self-validate: confirm this topic fits the niche, audience, content family, and doesn't repeat\n"
            + "6. For listicle topics, the number in the title MUST match the section count"
        )
        content_family_json_line = '  "content_family": "chosen content family name",\n'
    else:
        content_family_instruction = (
            "3. Write a brief angle/hook that makes it clickable\n"
            "4. Self-validate: confirm this topic fits the niche, audience, and doesn't repeat\n"
            "5. For listicle topics, the number in the title MUST match the section count"
        )
        content_family_json_line = ""

    return f"""Select a topic and video type for the next video on "{channel_name}".

CHANNEL CONTEXT:
- Niche: {niche_focus}
- Audience: {audience}
- Language: {language}
- Target duration: {target_duration_minutes} minutes
- Section count: the video will have {sr[0]}-{sr[1]} content sections

EXAMPLE TOPICS (for reference):
{examples_str}

TOPICS TO AVOID:
{avoid_str}

PAST TOPICS (don't repeat):
{past_str}

AVAILABLE VIDEO TYPES:
{types_str}
{preferred_line}
{content_family_block}INSTRUCTIONS:
1. Pick a fresh, compelling topic that fits the channel niche
2. Choose the video type that best suits this topic
{content_family_instruction}
   (e.g. "{sr[0]} Best Foods", not "20 Best Foods"). The video only has room for
   {sr[0]}-{sr[1]} items — never promise more items than sections.

Respond in JSON:
{{
  "topic": "the topic title",
  "video_type": "{video_type_enum}",
{content_family_json_line}  "angle": "the specific angle or hook",
  "why_it_fits": "brief validation of why this topic works for this channel",
  "estimated_sections": {sr[1]},
  "language": "{language}"
}}"""


# ---------------------------------------------------------------------------
# Stage 1 — Script generation
# ---------------------------------------------------------------------------

def script_system(tone: str, instructions: str) -> str:
    return _system_prompt(role="scriptwriter")


def _format_visual_guidance(guidance: dict[str, str]) -> str:
    """Format channel visual guidance as prompt text."""
    if not guidance:
        return ""
    lines = ["CHANNEL-SPECIFIC VISUAL GUIDANCE:"]
    for visual_type, hint in guidance.items():
        lines.append(f"  - {visual_type}: {hint}")
    return "\n".join(lines) + "\n\n"


def _numbering_order_instruction(numbering_order: str | None) -> str:
    """Return numbering rules for title_banner slots."""
    if not numbering_order:
        return ""
    if numbering_order == "ascending":
        return (
            "NUMBERED SECTION ORDER:\n"
            "- If the script uses numbered title_banner sections, the first numbered section viewers\n"
            "  watch MUST be #1, then #2, then #3 in strict ascending order.\n"
            "- Never open on #2/#7 and then restart later.\n"
            "- If you tease a later item in the hook, tease it WITHOUT speaking or displaying its\n"
            "  number until its real section.\n"
            '- The visible title_banner text itself MUST include the matching item number '
            '(for example "Step 2: The Seated March").\n'
            '- "section_number" and the spoken narration must use the same item number.\n\n'
        )
    if numbering_order == "descending":
        return (
            "NUMBERED SECTION ORDER:\n"
            "- If the script uses numbered title_banner sections, numbering must move in strict\n"
            "  descending order without resets or skips.\n"
            '- The visible title_banner text itself MUST include the matching item number.\n'
            '- "section_number" and the spoken narration must use the same item number.\n\n'
        )
    raise ValueError(f"Unsupported numbering_order: {numbering_order}")


def _format_thumbnail_strategy_options(strategies: list[dict[str, str]]) -> str:
    """Format allowed thumbnail strategies for the scriptwriter prompt."""
    if not strategies:
        raise ValueError("thumbnail strategies are required")
    lines = []
    for strategy in strategies:
        lines.append(f'- "{strategy["name"]}": {strategy["instruction"]}')
    return "\n".join(lines)


def _format_content_family_options(
    content_families: list[dict[str, str]] | None,
    preferred_content_family: str = "",
) -> str:
    """Format allowed content families for the planner prompt."""
    if not content_families:
        return ""
    lines = ["ALLOWED CONTENT FAMILIES (pick one and return its exact name in content_family):"]
    for family in content_families:
        preferred = " ← PREFERRED" if family["name"] == preferred_content_family else ""
        details = [family["planning_focus"]]
        if family.get("lead_magnet"):
            details.append(f'Lead magnet: {family["lead_magnet"]}')
        if family.get("low_ticket_offer"):
            details.append(f'Low-ticket offer: {family["low_ticket_offer"]}')
        lines.append(
            f'  - {family["name"]}: {" | ".join(details)}{preferred}'
        )
    return "\n".join(lines) + "\n\n"


def _format_business_strategy_context(
    *,
    channel_goal: str = "",
    content_family: str = "",
    lead_magnet: str = "",
    low_ticket_offer: str = "",
    mid_ticket_offer: str = "",
    later_offers: list[str] | None = None,
    video_jobs: list[str] | None = None,
    cta_rules: list[str] | None = None,
    cta_angle: str = "",
) -> str:
    """Format business-strategy context for planning and scripting prompts."""
    if not channel_goal:
        return ""
    later = ", ".join(later_offers or [])
    jobs = "\n".join(f"  - {job}" for job in (video_jobs or [])) or "  - (none)"
    rules = "\n".join(f"  - {rule}" for rule in (cta_rules or [])) or "  - (none)"
    lines = [
        "BUSINESS STRATEGY:",
        f"- Channel goal: {channel_goal}",
        f"- Selected content family: {content_family}",
    ]
    if lead_magnet:
        lines.append(f"- Primary lead magnet: {lead_magnet}")
    else:
        lines.append("- Primary CTA: subscribe")
    if low_ticket_offer:
        lines.append(f"- Low-ticket offer: {low_ticket_offer}")
    if mid_ticket_offer:
        lines.append(f"- Mid-ticket offer: {mid_ticket_offer}")
    if later:
        lines.append(f"- Later offers: {later}")
    if cta_angle:
        lines.append(f"- CTA angle: {cta_angle}")
    lines.extend([
        "VIDEO JOBS:",
        jobs,
        "CTA RULES:",
        rules,
        "",
    ])
    return "\n".join(lines)


def _script_strategy_blocks(
    *,
    channel_goal: str,
    content_family: str,
    lead_magnet: str,
    low_ticket_offer: str,
    mid_ticket_offer: str,
    advice_word: str,
    lead_magnet_rule: str,
    subscribe_rule: str,
    first_index: int,
) -> tuple[str, str]:
    if channel_goal and lead_magnet:
        return (
            f"""{first_index}. The video has two jobs: earn the click and move the viewer toward the primary lead magnet "{lead_magnet}".
{first_index + 1}. Keep the {advice_word} tightly aligned with the selected content family "{content_family}".
{first_index + 2}. {lead_magnet_rule} Keep "{low_ticket_offer}" and "{mid_ticket_offer}" as downstream offers rather than hard-selling them in narration.
""",
            (
                f'  "content_family": "{content_family}",\n'
                f'  "lead_magnet": "{lead_magnet}",\n'
                f'  "low_ticket_offer": "{low_ticket_offer}",\n'
                f'  "mid_ticket_offer": "{mid_ticket_offer}",\n'
            ),
        )
    if channel_goal:
        return (
            f"""{first_index}. The video has two jobs: earn the click and earn a subscribe from the right viewer.
{first_index + 1}. Keep the {advice_word} tightly aligned with the selected content family "{content_family}".
{first_index + 2}. {subscribe_rule}
""",
            f'  "content_family": "{content_family}",\n',
        )
    return "", ""


def _script_input_context(
    *,
    topic: str,
    video_type: str,
    angle: str,
    language: str,
    audience: str,
    target_duration_minutes: int,
    section_style: str,
    pacing: str,
    narrative_hook: str,
) -> str:
    return _block(f"""
        TOPIC: {topic}
        VIDEO TYPE: {video_type}
        ANGLE/HOOK: {angle}
        LANGUAGE: {language}
        AUDIENCE: {audience}
        TARGET LENGTH: about {target_duration_minutes} minute(s) of finished video. Follow the word budget in the rules.
        SECTION STYLE: {section_style}
        PACING: {pacing}
        {f"NARRATIVE APPROACH: {narrative_hook}" if narrative_hook else ""}
    """)


def _block(text: str) -> str:
    """Normalize a multiline prompt fragment."""
    return dedent(text).strip()


def _tag(name: str, body: str) -> str:
    """Wrap prompt content in a simple XML-style tag."""
    body = _block(body)
    if not body:
        return ""
    return f"<{name}>\n{body}\n</{name}>"


def _join_prompt_sections(*sections: str) -> str:
    """Join non-empty prompt fragments with blank lines."""
    return "\n\n".join(section.strip() for section in sections if section and section.strip())


def _shared_visual_policy(
    *,
    numbering_order: str | None = None,
    include_title_banner_rules: bool = True,
    min_visible_beat_seconds: float = 5.0,
    max_visual_hold_seconds: float = 16.0,
) -> str:
    blocks: list[str] = [
        _block(f"""
            Slot pacing:
            - After drafting each section's narration, use its word count to decide how many slots it needs.
            - Longer narrations need more slots so no visual beat lingers too long.
            - Keep every visible beat under {max_visual_hold_seconds:.0f} seconds on screen.
            - Aim for roughly {min_visible_beat_seconds:.0f}-{max_visual_hold_seconds:.0f} seconds per visible beat.
            - Shorter sections often land at 2-4 slots.
            - A section with roughly 50-70 narration words usually needs about 3+ slots.
            - A section that would need more than 5 visible beats should usually be split into more sections
              instead of parking one visual for too long.
        """),
        _block("""
            Backdrop figure scene rules:
            - title_card, fact_highlight, title_banner, and subscribe_cta are normal full-screen slots, not overlays.
            - NEVER output "overlay": true.
            - Those slot types MUST include a background-image "prompt" and "keywords" for the still behind the figure.
            - title_banner must be the first slot in its section.
            - subscribe_cta should usually be a short final beat or subsection.
            - Do NOT use title_card and title_banner in the same section.
            - Prefer visuals over text-heavy sections. Use at most ONE info_slide per section unless there is a strong source-backed reason.
        """),
    ]

    if include_title_banner_rules:
        numbering_rule = ""
        if numbering_order == "ascending":
            numbering_rule = (
                "For numbered title_banner sections, numbering MUST follow strict ascending order "
                "(#1, #2, #3, ...) in the order sections appear."
            )
        elif numbering_order == "descending":
            numbering_rule = (
                "For numbered title_banner sections, numbering MUST follow strict descending order "
                "with no resets or skips."
            )

        title_banner_policy = [
            "Title banner rules:",
            "- title MUST be a plain-language, visually obvious label for the exact observable action or sign in everyday language.",
            "- Do NOT use shorthand, metaphor, clinical jargon, mechanism labels, or optimization phrasing when a viewer could understand a simpler literal label.",
            "- For numbered list/countdown sections, title MUST visibly include that section's item number.",
            "- If the narration includes both a plain-language symptom and a clinical term, use the plain-language symptom on the banner and keep the clinical term in narration or an info_card/info_slide.",
            '- The title_banner slot itself MUST include "prompt" and "keywords" for the background image behind the banner.',
        ]
        if numbering_rule:
            title_banner_policy.insert(1, f"- {numbering_rule}")
        blocks.append("\n".join(title_banner_policy))

    return _join_prompt_sections(*blocks)


def _content_safety_rules() -> str:
    return _block("""
        Content safety:
        - Completely avoid tobacco/smoking, weapons, drugs/alcohol, explosives/pyrotechnics,
          violence, children in risky situations, sexual content, and shocking content.
        - Never use real named people in image prompts or narration.
        - Avoid topics that could get the video misclassified as made-for-kids without adult framing.
        - If a topic naturally involves banned content, skip that item and choose a different example.
    """)


def _script_visual_toolkit() -> str:
    return _block("""
        IMAGE TYPES (sourced externally — need "prompt" and/or "keywords"):
        - "google_photo" — Real photo from Google. For recognizable brands, products, famous places,
          historical events, and exact real-person action shots where the contact/action matters.
          Provide "keywords" (5-8 word search query with disambiguating context)
          and "prompt" (description of what the image should show). KEYWORD TIPS: Include what the
          subject IS + context (country, era, category) + "photograph".
        - "stock_photo" — Stock photo from Pexels. For generic everyday scenes. NOT for specific brands.
          Provide "keywords" and "prompt". If the exact support object, hand placement, or body-contact
          action matters, prefer google_photo instead.
        - "ai_photo" — AI-generated realistic image. For fictional scenes, abstract concepts, or moments
          that cannot be found online. Use this for exercise/stretch/movement demos when you need
          a realistic older adult doing the motion. Show one clear pose only. Do NOT ask for
          multiple poses, repeated subjects, arrows, labels, or embedded text. Do NOT use this for
          support-contact scenes where exact hand/object contact matters.
        - "ai_illustration" — Educational illustration. Use for anatomy, circulation,
          balance, body-mechanics, source-backed explainers, and concept support visuals.
          Do NOT use as the first visual for exact exercise demos; open those with
          google_photo, stock_photo, b_roll, or ai_photo.
        - "b_roll" — Stock VIDEO clip from Pexels. For scenes with natural movement. Only use when
          generic motion footage exists for the topic. Do NOT use this for precise exercise sections
          unless the clip clearly shows the same named movement and setting. Do NOT use this for
          support-contact scenes like furniture walking or pushing up from armrests when the exact
          hand placement matters. BAD: "busy market" — GOOD:
          "elderly woman doing leg stretches outdoors"

        COMPONENT TYPES (rendered by the video engine — use "props" for component-specific data):
        - "info_card" — Stylized split-layout card: illustration + text box. Use for short callouts,
          concept beats, and visual breaks between photo-heavy sections.
        - "info_slide" — Structured titled slide with required sourced illustration/photo. Use for
          practical tips, safety cues, source-backed takeaways, or concise concept explanations.
        - "text_only_slide" — Reserved for internal AI prompt preview diagnostics. NEVER output it.
        - "bar_chart" — Animated vertical bar chart. For rankings, scores, comparing 3-8 items.
        - "donut_gauge" — Circular progress ring. For a single dramatic percentage (0-100).
        - "comparison_bars" — Horizontal comparison bars. For comparing 2-6 items on one metric.

        BACKDROP FIGURE SCENE TYPES (normal full-screen slots with a required background image):
        - "title_card" — Animated title text scene. Provide "prompt", "keywords", and props.title.
        - "fact_highlight" — Big animated number/stat scene. Provide "prompt", "keywords", and props.value/props.label.
        - "title_banner" — Banner scene for numbered sections. Provide "prompt", "keywords", props.title
          with the visible item number in the title text,
          and optional props.section_number / props.accent_color.
        - "subscribe_cta" — CTA scene. Provide "prompt", "keywords", and props.cta_text / props.subtext.

        VISUAL POLICY:
        - Every slot should include "visual_policy".
        - Use "source_as_written" when the selected visual type already says how to source it.
        - Use "google_photo_exact_action" for real-world actions where exact contact, support objects,
          or body placement must be visible.
        - Use "literal_google_photo" for concrete treatment or object scenes that should be searched
          literally as a real photo.
        - Use "photo_backed_info_slide" when an info_slide should keep its text/card treatment but
          use a real photo as the sourced backing image.
        - Use "single_pose_ai_photo" when ai_photo must show one realistic person in one clear pose.
    """)


def _prompt_scaffold(
    *,
    task: str,
    rules: str,
    examples: str,
    schema: str,
    input_block: str,
    research_context: str = "",
) -> str:
    sections = [
        _tag("task", task),
        _tag("rules", rules),
        _tag("examples", examples),
        _tag("schema", schema),
        _tag("input", input_block),
    ]
    if research_context:
        sections.append(
            _tag(
                "research_context",
                f"Use these verified facts, data points, and sources when writing or reviewing content:\n{research_context}",
            )
        )
    return _join_prompt_sections(*sections)


def _script_schema(
    *,
    video_type: str,
    strategy_json_block: str,
    include_accent_color: bool,
) -> str:
    accent_line = '\n      "accent_color": "#HEX",' if include_accent_color else ""
    return f"""Respond in JSON with this exact structure:
{{
  "title": "Video title (SEO optimized, clickable)",
  "video_type": "{video_type}",
  "description": "YouTube description with SEO keywords (2-3 paragraphs)",
  "tags": ["tag1", "tag2", "..."],
  "hook": "The opening hook sentence",
{strategy_json_block}  "thumbnail_strategy": "chosen strategy name from the allowed options",
  "thumbnail_text": "EXACT THUMBNAIL TEXT",
  "thumbnail_brief": "Concrete thumbnail visual concept that follows the selected strategy",
  "sections": [
    {{
      "id": 1,
      "narration": "Full narration text for this section...",
      "transition_type": "fade",
      "highlighted_keywords": ["keyword1", "keyword2"],{accent_line}
      "slots": [
        {{"visual": "google_photo", "prompt": "Detailed image description...", "keywords": "5-8 word search query with context"}},
        {{"visual": "b_roll", "keywords": "topically relevant motion footage query"}},
        {{"visual": "ai_photo", "prompt": "Realistic photo-style image description..."}},
        {{"visual": "title_card", "prompt": "Realistic photo of the main section subject in a clean setting.", "keywords": "main section subject real photo", "props": {{"title": "Section Title", "accent_color": "#00D4FF"}}}}
      ]
    }}
  ]
}}"""


def script_generation_prompt(
    topic: str,
    video_type: str,
    angle: str,
    channel_name: str,
    audience: str,
    language: str,
    target_duration_minutes: int,
    sections_range: list[int],
    section_style: str,
    pacing: str,
    style_prompt_suffix: str,
    title_format_instruction: str,
    description_style_instruction: str,
    thumbnail_strategies: list[dict[str, str]],
    visual_guidance: dict[str, str] | None = None,
    narrative_hook: str = "",
    research_context: str = "",
    section_color_palette: list[str] | None = None,
    music_pool: list[str] | None = None,
    voice_variations: list[str] | None = None,
    transition_pool: list[str] | None = None,
    numbering_order: str | None = None,
    duration_requirements: str = "",
    channel_goal: str = "",
    content_family: str = "",
    lead_magnet: str = "",
    low_ticket_offer: str = "",
    mid_ticket_offer: str = "",
    later_offers: list[str] | None = None,
    video_jobs: list[str] | None = None,
    cta_rules: list[str] | None = None,
    cta_angle: str = "",
    min_visible_beat_seconds: float = 5.0,
    max_visual_hold_seconds: float = 16.0,
) -> str:
    business_context = _format_business_strategy_context(
        channel_goal=channel_goal,
        content_family=content_family,
        lead_magnet=lead_magnet,
        low_ticket_offer=low_ticket_offer,
        mid_ticket_offer=mid_ticket_offer,
        later_offers=later_offers,
        video_jobs=video_jobs,
        cta_rules=cta_rules,
        cta_angle=cta_angle,
    )
    strategy_requirements, strategy_json_block = _script_strategy_blocks(
        channel_goal=channel_goal,
        content_family=content_family,
        lead_magnet=lead_magnet,
        low_ticket_offer=low_ticket_offer,
        mid_ticket_offer=mid_ticket_offer,
        advice_word="practical advice",
        lead_magnet_rule=(
            f'Mention "{lead_magnet}" naturally once after the viewer has received real '
            f'value and again in the closing CTA. Use this CTA angle: {cta_angle}.'
        ),
        subscribe_rule=(
            "Mention subscribing naturally only after the viewer has received real value "
            f"and again in the closing CTA. Use this CTA angle: {cta_angle} Do not invent "
            "guides, checklists, downloads, lead magnets, or products that are not provided "
            "in the channel strategy."
        ),
        first_index=14,
    )
    task = (
        f'Write a full YouTube narration script for the channel "{channel_name}". '
        "Return a complete JSON payload with narration, slots, SEO metadata, and thumbnail inputs."
    )
    core_requirements = _block(f"""
        Core requirements:
        1. Write the full narration text for each section.
        2. Start with a powerful hook in the first section (first 30 seconds).
        3. For each section, build a "slots" list — each slot is one visual moment.
        4. For each section, pick 2-3 highlighted_keywords that appear in the narration text.
        5. Include SEO-optimized title, description, and tags.
        6. Think in word budgets, not timing guesses. The system computes timing from narration words after generation.
        7. Write a short "thumbnail_text" — 2-5 punchy words of exact visible text.
        8. Choose "thumbnail_strategy" from the allowed options.
        9. Write "thumbnail_brief" as one concrete visual concept that follows the chosen strategy.
        10. "transition_type" means the transition INTO this section from the previous one.
            Section 1 must omit transition_type (it's the opening).
        {duration_requirements.strip() if duration_requirements else _block(f'''
            11. TOTAL WORD COUNT: You MUST write at least {target_duration_minutes * 160} words of narration across ALL sections combined. This is NON-NEGOTIABLE — we measure by counting words, not your time estimates.
            12. SECTIONS: You MUST write at least {sections_range[0]} sections (up to {sections_range[1]}). DO NOT write fewer than {sections_range[0]}.
            13. PER-SECTION NARRATION: each section MUST have at least {target_duration_minutes * 160 // sections_range[1]} words. Aim for {target_duration_minutes * 160 // sections_range[0]} words per section. Write LONG, detailed, storytelling narrations — not short summaries.
        ''')}
        {strategy_requirements.strip() if strategy_requirements else ""}
    """)
    policy = "SHARED VISUAL POLICY:\n" + _shared_visual_policy(
        numbering_order=numbering_order,
        min_visible_beat_seconds=min_visible_beat_seconds,
        max_visual_hold_seconds=max_visual_hold_seconds,
    )
    visual_rules = _block("""
        Additional visual rules:
        - subscribe_cta: 1 per video, keep it short (~5s), needs images behind it.
          If the channel strategy includes a lead magnet, set cta_text/subtext to that offer
          instead of a generic subscribe message.
        - info_card/info_slide: alternate with image sections. "prompt" describes the illustration/photo to source.
        - Do not output text_only_slide; it is reserved for internal AI prompt preview diagnostics.
        - Charts: bar_chart bars=3-8 items, comparison_bars items=2-6, donut_gauge value=0-100.
        - Vary accent_color across backdrop figure scenes and components for visual variety.
    """)
    toolkit = _script_visual_toolkit()

    rules = _join_prompt_sections(
        core_requirements,
        "VISUAL TOOLKIT:\n" + toolkit,
        policy,
        visual_rules,
        _content_safety_rules(),
    )
    input_block = _join_prompt_sections(
        _script_input_context(
            topic=topic,
            video_type=video_type,
            angle=angle,
            language=language,
            audience=audience,
            target_duration_minutes=target_duration_minutes,
            section_style=section_style,
            pacing=pacing,
            narrative_hook=narrative_hook,
        ),
        business_context.strip(),
        _numbering_order_instruction(numbering_order).strip(),
        _format_visual_guidance(visual_guidance or dict()).strip(),
        _color_palette_instruction(section_color_palette).strip(),
        _block(f"""
            IMAGE STYLE CONTEXT: {style_prompt_suffix}

            TITLE FORMAT (you MUST follow this): {title_format_instruction}

            THUMBNAIL STRATEGY OPTIONS (choose exactly one and return its name in "thumbnail_strategy"):
            {_format_thumbnail_strategy_options(thumbnail_strategies)}

            DESCRIPTION STYLE (you MUST follow this): {description_style_instruction}
        """),
    )
    return _prompt_scaffold(
        task=task,
        rules=rules,
        examples="",
        schema=_script_schema(
            video_type=video_type,
            strategy_json_block=strategy_json_block,
            include_accent_color=bool(section_color_palette),
        ),
        input_block=input_block,
        research_context=research_context,
    )


def script_revision_prompt(
    script_json: str,
    feedback: str,
    sections_range: tuple[int, int] = (2, 10),
    duration_guard: str = "",
) -> str:
    task = "Revise this script to fix the flagged issues while keeping unflagged material intact."
    rules = _join_prompt_sections(
        _block(f"""
            Revision scope:
            - Fix only the broken sections or fields called out below.
            - Keep title, description, tags, hook, thumbnail fields, section numbering, and unflagged sections materially unchanged unless a listed issue requires a change.
            - Return the complete revised script in the same JSON structure.
            - Keep the section count within {sections_range[0]} to {sections_range[1]} unless an explicit fix requires adding one neighboring section.
            {f"- DURATION GUARDRAILS: {duration_guard}" if duration_guard else ""}
        """),
        _block("""
            Visual-structure rules:
            - NEVER output text_only_slide.
            - NEVER output overlay=true.
            - Every slot should include visual_policy.
            - Allowed visual_policy values are source_as_written, photo_backed_info_slide, google_photo_exact_action, literal_google_photo, and single_pose_ai_photo.
            - visual_policy is not the same as visual. Do not output visual_policy values like google_photo, stock_photo, ai_photo, info_slide, or b_roll.
            - Keep enough slots in every revised section so no visual beat stays up too long; if you add narration to a section, add slots too.
        """),
    )
    examples = ""
    schema = "Return the complete revised script in the same JSON format as the input script. Output JSON only."
    input_block = _join_prompt_sections(
        f"REVIEWER FEEDBACK:\n{feedback or '(none)'}",
        f"CURRENT SCRIPT:\n{script_json}",
    )
    return _prompt_scaffold(
        task=task,
        rules=rules,
        examples=examples,
        schema=schema,
        input_block=input_block,
    )


# ---------------------------------------------------------------------------
# Gate #1 — Script quality review
# ---------------------------------------------------------------------------

def script_review_system() -> str:
    return _system_prompt(role="script reviewer")


def script_review_prompt(
    script_json: str,
    min_score: float = 7.0,
    numbering_order: str | None = None,
    max_visual_hold_seconds: float = 16.0,
) -> str:
    numbering_rule = ""
    if numbering_order == "ascending":
        numbering_rule = (
            "For numbered title_banner sections, numbering MUST follow strict ascending order "
            "(#1, #2, #3, ...) in the order sections appear."
        )
    elif numbering_order == "descending":
        numbering_rule = (
            "For numbered title_banner sections, numbering MUST follow strict descending order "
            "with no resets or skips in the order sections appear."
        )
    task = "Review this YouTube video script for quality."
    rules = _join_prompt_sections(
        _block(f"""
            Score each criterion from 1-10:
            1. Hook strength — Does the first 30 seconds grab attention?
            2. Pacing and flow — Is the rhythm engaging? No dead spots?
            3. Audience engagement — Will viewers watch until the end?
            4. SEO quality — Title, description, tags optimized for search?
            5. Cultural accuracy and tone — Appropriate for the target audience?
            6. Section balance — Are sections roughly proportional and well-structured?
            7. Overall watchability — Would you watch this video?
            8. Backdrop figure scene structure — title_banner, title_card, fact_highlight, and
               subscribe_cta must be normal slots with their own background-image prompt and
               keywords, not overlay=true payloads. {numbering_rule}
               Score 1 if any of those slots are missing required background media fields,
               numbered banners break the required order, a banner title is visually vague or
               uses mechanism jargon, a numbered banner title omits or mismatches its visible item
               number.
               Score 1 if a section packs so much narration into so few slots that any
               visible beat would need to stay on screen longer than about {max_visual_hold_seconds:.0f} seconds. The fix is
               to add more visual slots or split the section, not to park one image/component on screen.
            9. Content safety — Check ALL narration, slot prompts, slot keywords, title,
               description, tags, thumbnail_text, and thumbnail_brief fields. Score 1 (instant reject) if banned content appears
               anywhere. Score 10 only if the script is completely free of ALL banned content.
            10. Funnel alignment — If the script includes a non-empty lead_magnet,
                low_ticket_offer, or mid_ticket_offer field, the narration and description should
                support the lead magnet naturally. Score 1 if the script hard-sells downstream offers
                in the narration, ignores the lead magnet entirely, or feels spammy instead of useful.

            NOTE: Do NOT evaluate duration or script length. Duration is validated separately by the system.

            PASS CRITERIA: All scores ≥ {min_score}/10 and overall ≥ {min_score + 0.5}/10.
        """),
        "Shared visual policy reference:\n" + _shared_visual_policy(numbering_order=numbering_order),
        _content_safety_rules(),
    )
    examples = ""
    schema = """Respond in JSON:
{
  "approved": true/false,
  "scores": {
    "hook_strength": 8,
    "pacing_flow": 7,
    "audience_engagement": 8,
    "seo_quality": 7,
    "cultural_accuracy": 9,
    "section_balance": 7,
    "overall_watchability": 8,
    "overlay_narration_sync": 10,
    "content_safety": 10,
    "funnel_alignment": 8
  },
  "overall_score": 7.7,
  "feedback": "Specific, actionable feedback if rejected. What exactly needs to change and why.",
  "strengths": ["what works well"],
  "weaknesses": ["what needs improvement"]
}"""
    return _prompt_scaffold(
        task=task,
        rules=rules,
        examples=examples,
        schema=schema,
        input_block=f"SCRIPT:\n{script_json}",
    )


# ---------------------------------------------------------------------------
# Gate #2 — Image relevance review
# ---------------------------------------------------------------------------

def image_review_system() -> str:
    return _system_prompt(role="image reviewer")


def image_review_prompt(sections_context: list[dict]) -> str:
    """Build the review prompt.

    sections_context: list of dicts with keys:
        - section_id: int
        - sub_image_index: int (1-based)
        - narration: str (brief)
        - visual_type: str
        - is_section_opener: bool
        - text_only: bool
        - prompt: str (exact target visual prompt)
        - image_search_keywords: str
        - image_filename: str
    """
    context_lines = []
    has_b_roll = False
    for s in sections_context:
        sub_idx = s.get("sub_image_index", 1)
        b_roll_tag = ""
        if s.get("is_b_roll"):
            b_roll_tag = " [B-ROLL]"
            has_b_roll = True
        target_prompt = s.get("prompt", "").strip()
        prompt_line = f"\n  Target prompt: {target_prompt}" if target_prompt else ""
        opener_tag = "yes" if s.get("is_section_opener") else "no"
        text_only_tag = "yes" if s.get("text_only") else "no"
        context_lines.append(
            f"Image {s['section_id']}.{sub_idx}{b_roll_tag} ({s['image_filename']}):\n"
            f"  Narration: {s['narration'][:400]}...\n"
            f"  Visual type: {s.get('visual_type', 'unknown')}\n"
            f"  Section opener: {opener_tag}\n"
            f"  Text-only component: {text_only_tag}\n"
            f"  Search keywords: {s['image_search_keywords']}{prompt_line}"
        )
    context_str = "\n\n".join(context_lines)

    b_roll_rules = ""
    if has_b_roll:
        b_roll_rules = _tag(
            "b_roll_rules",
            _block("""
                **B-ROLL IMAGES** (marked [B-ROLL] above): These are frames from stock video clips.

                For exercise, pose, physical therapy, or how-to movement B-roll, DO NOT judge by broad
                category alone. The body position and movement must match the narration. Reject generic seniors, chairs, talking heads, or generic exercise footage when the narration asks for a specific movement like seated marching, seated knee extension, ankle pumps, or shoulder rolls. The viewer should be able to see how to do the exercise, not just the general topic.

                For non-exercise atmospheric B-roll, judge by CATEGORY rather than exact subject. It only
                needs to stay in the same general topic area as the narration.
                - Narration about Motita candy → B-roll showing kids eating any candy = APPROVED
                - Narration about old TV shows → B-roll showing a family watching TV = APPROVED
                - Narration about Mexican markets → B-roll showing any busy market = APPROVED
                Reject non-exercise B-roll only if it is from a completely unrelated category.
            """),
        )

    task = (
        "Review these sourced images for subject relevance and instructional accuracy. "
        "Reject wrong-subject, wrong-pose, or broken-anatomy images."
    )
    rules = _join_prompt_sections(
        _block("""
            IMPORTANT: The images are numbered sequentially in the exact same order as the sections
            listed below. Image 1 corresponds to the first section, Image 2 to the second, and so on.

            Decision rules:
            - REJECT (approved: false, severity: "error") when the image shows a wrong or unrelated
              subject, impossible anatomy, or the wrong pose/body mechanics for the requested instructional visual.
            - When approved is false, failure_type is REQUIRED.
            - Each element in image_results must be one flat single-image object. Do NOT nest a
              top-level review payload (approved, image_results, feedback, scores) inside an item.
            - Use failure_type "wrong_subject" for the wrong subject/object/category.
            - Use failure_type "pose_mismatch" for the wrong exercise, wrong pose, or wrong body mechanics.
            - Use failure_type "anatomy_error" for extra limbs, extra feet/toes, duplicated shoes,
              malformed hands/feet, impossible joints, merged limbs, or distorted body parts.
            - Use failure_type "weak_match" when the image stays in the same broad category but still misses the named object, tool, symptom, or action.
            - WARNING (approved: true, severity: "warning") for watermark/text, low resolution, blur,
              or minor quality issues.
            - OK (approved: true, severity: "ok") when the image matches the narration well.
            - For the FIRST slot in an exercise/movement section, be strict: it must show the named movement accurately.
            - For later exercise support visuals, allow looser contextual/supportive imagery as long as it
              does not contradict the named movement, safety cue, or symptom.
            - Reject detached floating body-part inset layouts for exercise/support visuals unless the
              prompt explicitly asks for an isolated anatomy/body-part diagram. A floating foot or hand
              cutout next to the person is not an acceptable substitute for a clean full-scene demo.
            - If Text-only component is yes, it must be an internal prompt-preview diagnostic slide.
              Reject it if it appears to be authored teaching/support content instead of a prompt/model preview.
            - For photo-style warning-sign, symptom, or treatment scenes, be looser on minor AI-like blemishes.
              If the correct body part, object, and action are clear, treat small hand/finger oddities as warning-level.
              Reject only when the anatomy is clearly broken, changes the meaning of the scene, or makes the subject/action unreadable.
            - Be lenient on quality but strict on subject relevance and instructional accuracy.
            - Matching only the room, age group, or general lifestyle category is NOT enough when narration or
              prompt names a specific object, tool, body action, or symptom.
        """),
        b_roll_rules,
    )
    examples = _join_prompt_sections(
        _tag(
            "review_examples",
            _block("""
                Wrong subject: narration is about a heating pad on stiff joints but the image shows a building,
                room decor, or any other object that is not the heating pad/use action itself.
                Weak match: narration is about leg swings or toe wiggles but the image shows a gift box,
                blanket still life, or any object/environment without the named body action.
                Pose mismatch: prompt says both heels stay down, but the image lifts a heel or shows the wrong foot action.
                Anatomy error: extra limbs, extra feet/toes, duplicated shoes, malformed hands/feet, impossible joints.
                Detached inset failure: a seated person is shown next to a floating foot cutout with arrows. Reject it unless the prompt explicitly asked for an isolated foot diagram.
                Text_only_slide opener: the slide is a clear text guide for the requested movement, with readable steps and safety cues, so approve it even without a body pose demo.
                Later support visual: a chair-side context photo after the opener is acceptable if it does not show the wrong movement.
                Warning only: a photo-style symptom scene shows the correct shin bandage and action, but the fingers look slightly AI-ish while still readable.
                Warning only: watermark visible, low resolution, or blur while the subject is still correct.
            """),
        ),
    )
    schema = """Respond in JSON:
{
  "approved": true/false,
  "image_results": [
    {
      "section_id": 1,
      "sub_image_index": 1,
      "approved": true/false,
      "severity": "ok" | "warning" | "error",
      "failure_type": "wrong_subject" | "pose_mismatch" | "anatomy_error" | "weak_match",  // required when approved=false
      "issues": ["watermark visible", "low resolution"],
      "suggestion": "Search for 'more specific keywords' instead"
    }
  ],
  "feedback": "Overall summary"
}
Do not put top-level fields like approved, image_results, feedback, or scores inside any image_results item."""
    return _prompt_scaffold(
        task=task,
        rules=rules,
        examples=examples,
        schema=schema,
        input_block=f"SECTION CONTEXT:\n{context_str}",
    )


def pexels_candidate_selection_prompt(
    *,
    keywords: str,
    prompt: str,
    num_images: int,
) -> str:
    """Prompt for Vision API to pick the best Pexels candidate before saving."""
    prompt_line = f"\nDESIRED IMAGE: {prompt}" if prompt else ""
    return _prompt_scaffold(
        task=f"Review {num_images} candidate stock photos for a single visual slot.",
        rules=_block("""
            Pick a candidate only if it clearly matches the requested subject and action.
            For exercise or pose visuals, the body position and exercise type must match.
            Reject the whole set if the candidates only match generic words like "senior",
            "home", "exercise", or "chair" but show the wrong movement.
            Reject the whole set when the candidates match only the same general category,
            setting, or age group while missing the named object/action. If the request is
            for a heating pad, toe wiggles, leg swings, or a pillow under the knees, do not
            accept room decor, still-life objects, or unrelated lifestyle photos from the same
            general category.
        """),
        examples=_tag(
            "selection_examples",
            _block("""
                Approve example: "The person is seated and extending one leg as requested."
                Reject example: "All candidates show the wrong exercise."
            """),
        ),
        schema="""Respond in JSON:
{
  "approved": true,
  "winner_index": 2,
  "reason": "The person is seated and extending one leg as requested"
}

If none are good enough, respond:
{
  "approved": false,
  "reason": "All candidates show the wrong exercise"
}

winner_index is 1-based (1 = first image, 2 = second, etc.).""",
        input_block=f'The images are numbered 1 through {num_images} in the order they are provided.\nSEARCH KEYWORDS: {keywords}{prompt_line}',
    )


# ---------------------------------------------------------------------------
# Gate #3 — Thumbnail quality review
# ---------------------------------------------------------------------------

def thumbnail_generation_prompt(
    *,
    title: str,
    thumbnail_text: str,
    thumbnail_brief: str,
    strategy_instruction: str,
    content_context: str,
    channel_style: str,
    image_style_prompt_suffix: str,
    revision_notes: str = "",
) -> str:
    revision_block = f"\nREVISION NOTES FROM REVIEWER:\n{revision_notes}\n" if revision_notes else ""
    return f"""Generate the final 1280x720 YouTube thumbnail image.

VIDEO TITLE:
{title}

EXACT THUMBNAIL TEXT:
{thumbnail_text}

THUMBNAIL VISUAL BRIEF:
{thumbnail_brief}

THUMBNAIL STRATEGY:
{strategy_instruction}

VIDEO CONTENT TO REPRESENT:
{content_context}

CHANNEL STYLE:
{channel_style}

IMAGE STYLE CONTEXT:
{image_style_prompt_suffix}
{revision_block}
STRICT RULES:
1. Render a complete finished YouTube thumbnail, not a background mockup.
2. Include the exact thumbnail text "{thumbnail_text}" once, spelled exactly.
3. Do not include extra readable words, captions, logos, watermarks, signatures, UI labels,
   badge text, name-tag text, packaging text, chart labels, or clipboard/form text.
4. For document, research, chart, or clinical-fragment styles, any background text must be abstract,
   clipped, or unreadable. Do not invent readable study titles, citations, journal names, dates, or claims.
5. Only depict subjects covered by the video content context. Do not add unrelated foods, remedies,
   supplements, exercises, body parts, charts, or medical props.
6. Make the main idea readable at mobile thumbnail size: high contrast, one strong focal point,
   simple composition, and strong title-thumbnail curiosity.
7. Do not show graphic medical procedures, suffering, injuries, blood, or miracle-cure implications."""


def thumbnail_review_system() -> str:
    return _system_prompt(role="thumbnail reviewer")


def thumbnail_review_prompt(
    *,
    title: str,
    video_type: str,
    thumbnail_text: str,
    thumbnail_strategy: str,
    thumbnail_brief: str,
    strategy_instruction: str,
    content_context: str = "",
) -> str:
    context_block = f"\nVIDEO CONTENT:\n{content_context}\n" if content_context else ""
    return f"""Review this YouTube thumbnail for click-worthiness.

VIDEO TITLE: {title}
VIDEO TYPE: {video_type}
THUMBNAIL TEXT THAT MUST APPEAR EXACTLY: {thumbnail_text}
THUMBNAIL STRATEGY: {thumbnail_strategy}
STRATEGY INSTRUCTION: {strategy_instruction}
THUMBNAIL BRIEF: {thumbnail_brief}
{context_block}

Evaluate:
1. **Clickability** — Would you click this thumbnail in a YouTube feed?
2. **Exact text** — Does the thumbnail include "{thumbnail_text}" exactly once, with no misspellings,
   distorted letters, missing words, or unreadable text at mobile size?
3. **No extra readable text** — Reject if there are extra readable words, fake study titles,
   citations, logos, watermarks, signatures, UI labels, badge text, name-tag text,
   packaging text, chart labels, or clipboard/form text.
4. **Strategy match** — Does the image follow the selected thumbnail strategy and brief?
5. **Visual clarity** — Is the main subject clear and not cluttered?
6. **Emotional impact** — Does it evoke curiosity, nostalgia, urgency, or surprise without fearmongering?
7. **Content honesty** — Does it avoid showing foods, products, exercises, body parts, data, or
   remedies that are not covered in the video?
8. **Thumbnail-title synergy** — Do the title and thumbnail work together without duplicating the
   exact same idea too weakly?

Respond in JSON:
{{
  "approved": true/false,
  "feedback": "Specific feedback on what to improve",
  "strengths": ["what works"],
  "weaknesses": ["what needs fixing"],
  "suggestion": "How to improve if rejected"
}}"""


# ---------------------------------------------------------------------------
# Gate #4 — Final package review
# ---------------------------------------------------------------------------

def package_review_system() -> str:
    return _system_prompt(role="package reviewer")


def package_review_prompt(
    title: str,
    description: str,
    tags: list[str],
    video_type: str,
    narration_summary: str,
) -> str:
    tags_str = ", ".join(tags)

    return f"""Final review before YouTube upload. You're seeing frame screenshots from the
video plus the thumbnail. Review the complete package.

VIDEO METADATA:
- Title: {title}
- Type: {video_type}
- Tags: {tags_str}
- Description: {description}

NARRATION SUMMARY:
{narration_summary}

The images provided are (in order):
1. Thumbnail (first image)
2. Frame screenshots from the video (remaining images)

REVIEW CRITERIA:
1. **Title-content alignment** — Does the video deliver what the title promises?
2. **Image quality** — Are the video frames visually acceptable?
3. **Policy compliance** — Any content that violates YouTube community guidelines?
4. **Metadata completeness** — Title, description, tags all present and relevant?
5. **Thumbnail-title synergy** — Do the thumbnail and title work together?
6. **Overall quality** — Would you be comfortable publishing this?

Respond in JSON:
{{
  "approved": true/false,
  "critical_issues": ["list of blocking issues, if any"],
  "minor_issues": ["list of non-blocking issues"],
  "feedback": "Summary of findings",
  "recommendation": "publish | fix_and_retry | flag_for_human_review"
}}"""
