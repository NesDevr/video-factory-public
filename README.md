# Video Factory

Multi-agent AI video production system that turns a topic into a YouTube-ready
video package: script, visuals, narration, rendered MP4, thumbnail, metadata,
review reports, and cost traces.

Video Factory coordinates specialized AI-assisted stages for planning, script
writing, visual sourcing/generation, narration, rendering, thumbnail creation,
and final QA. It is designed as a practical agentic media system, not a simple
prompt wrapper.

What it does:

- Plans channel-aware topics from JSON configuration and topic history
- Generates scripts, metadata, visual briefs, and thumbnail strategy
- Sources or generates images and B-roll, then reviews them for relevance
- Generates TTS narration with word-level timing for subtitles
- Renders animated sections with Remotion and assembles the final MP4
- Creates and reviews YouTube thumbnails
- Tracks checkpoints, retries, validation failures, AI traces, and estimated cost

<!-- Screenshot: generated thumbnail + a rendered video frame side by side, showing the final output -->
![Sample output](docs/screenshots/sample_output.png)

Video Factory is a personal project. It is not affiliated with YouTube, Google,
Gemini, Remotion, Pexels, Serper, or any other referenced platform or provider.

This public repo includes a generic `demo_channel` configuration. Production
channel configs, generated workspaces, private research notes, API keys, and
runtime media outputs are intentionally excluded.

## Architecture

The system runs 9 named stages. Image and audio sourcing run in parallel after
script generation:

```text
planning -> script -> image_source + audio_source -> process
         -> render_sections -> assemble -> thumbnail -> final_review
```

**Review gates** validate script quality, image relevance, thumbnail clickability,
and the final package. Script and thumbnail failures trigger regeneration with
feedback, up to a configurable max attempts. Image relevance failures fail
closed after review attempts instead of rewriting sourced slots behind the
scenes.

## Prerequisites

- Python 3.11+
- Node.js 18+ and npm (for Remotion rendering)
- FFmpeg on PATH
- Google Cloud project with Application Default Credentials configured
- Provider keys:
  - **Serper** — web image search
  - **Pexels** — stock photo and B-roll sourcing

## Setup

```bash
git clone https://github.com/Nesgc/video-factory-public.git
cd video-factory

python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

pip install -r requirements.txt

# Install Remotion dependencies. Studio requires runtime deps such as @babel/parser,
# so use npm install rather than an omit-dev/pruned install.
cd rendering/remotion && npm install && cd ../..

cp .env.example .env
# Edit .env with your project ID and provider keys
```

Authenticate Google Cloud locally before running AI or speech stages:

```bash
gcloud auth application-default login
gcloud config set project your-gcp-project-id
```

## Usage

```bash
# Full pipeline
python factory.py --channel demo_channel

# Run up to a specific stage
python factory.py --channel demo_channel --stage ..script

# Run only one stage through the normal pipeline path
python factory.py --channel demo_channel --stage image_source

# Run a range of stages (uses latest workspace)
python factory.py --channel demo_channel --stage process..thumbnail

# Target a specific workspace
python factory.py --channel demo_channel --workspace workspace/path --stage script

# Override config fields ad-hoc
python factory.py --channel demo_channel --set video.target_duration_minutes=1

# Force a video type
python factory.py --channel demo_channel --set plan.video_type=narrative

# Force a content family for a configured channel
python factory.py --channel demo_channel --set plan.content_family=practical_checklist

# Replay fixtures (zero-cost re-runs using cached API responses)
python factory.py --channel demo_channel --fixtures replay

# Open the latest workspace in Remotion Studio after process (fast preview path)
python factory.py --channel demo_channel --preview-remotion --set video.target_duration_minutes=1 --set gemini_tts_model=gemini-2.5-flash-tts

# Preview AI image prompts as slides instead of calling image generation
python factory.py --channel demo_channel --preview-remotion --set test.preview_ai_image_prompts=true --set video.target_duration_minutes=1 --set gemini_tts_model=gemini-2.5-flash-tts

```

`--stage script` is equivalent to `--stage script..script`. It still uses the
normal pipeline orchestrator, so it writes `pipeline.log`, `pipeline.html`, and
the same consolidated `reports/ai_trace_report.json` artifact as any other run.

### Full-video Remotion preview

Use `--preview-remotion` to stop after `process`, build a real
workspace-backed preview manifest, write the live copy with the staged assets
under `rendering/remotion/public/_preview/{workspace-name}/`, update Remotion's
generated active-preview pointer, and open the
`FullVideoPreview` composition in Remotion Studio.

```bash
python factory.py --channel demo_channel --preview-remotion --set video.target_duration_minutes=1 --set gemini_tts_model=gemini-2.5-flash-tts

# Show AI image prompts/model choices as Remotion slides without calling image generation
python factory.py --channel demo_channel --preview-remotion --set test.preview_ai_image_prompts=true --set video.target_duration_minutes=1 --set gemini_tts_model=gemini-2.5-flash-tts

# Preview already continues past script_review and image_review by default; use this only for additional gates
python factory.py --channel demo_channel --preview-remotion --allow-review-failures thumbnail,final_review --set video.target_duration_minutes=1 --set gemini_tts_model=gemini-2.5-flash-tts
```

Preview mode:

- stages ready images, raw B-roll clips, watermark assets, and full-length
  audio tracks into `rendering/remotion/public/_preview/{workspace-name}/`
- writes that run's live manifest to
  `rendering/remotion/public/_preview/{workspace-name}/preview_manifest.json`
- always launches the browser preview on `http://localhost:3005`
- if Remotion Studio is already running on `3005`, preview mode leaves it up
  and rewrites a generated active-preview module so Studio hot-reloads that
  run's manifest instead of reopening
- plain `npx remotion studio` also loads the latest preview because
  `FullVideoPreview` fetches the active `_preview/{workspace-name}` manifest via
  `staticFile()`

Add `--set test.preview_ai_image_prompts=true` when you want preview mode to
skip AI image generation during image sourcing. AI-backed slots become text
slides showing the model, operation label, and prompt.
- keeps only the latest 10 staged preview bundles in `_preview/`; older staged
  bundles are pruned automatically
- already continues past rejected `script_review` and `image_review` by
  default so preview generation still reaches Studio; those gates stay flagged
  in `checkpoint.json`, and use `--allow-review-failures` only for additional
  gates
- skips `thumbnail`, `render_sections`, `assemble`, `final_review`, and
  final export
- is meant for timing, layout, subtitle, overlay, and audio reviewability, not
  bit-exact parity with the final FFmpeg export

<!-- Screenshot: Remotion Studio browser showing FullVideoPreview with subtitles, watermark, and animated image sections visible -->
![Remotion Studio preview](docs/screenshots/remotion_preview.png)

`--preview-remotion` cannot be combined with `--stage`.

### Windows Remotion GPU rendering

On Windows, `render_sections` now performs a mandatory Remotion GPU preflight
before any section render starts. The pipeline uses Chrome for Testing with the
ANGLE backend for Chromium frame rendering, then keeps the existing
JPEG-sequence + FFmpeg `h264_nvenc` path for section clip encoding.

- the preflight runs the equivalent of `remotion gpu --chrome-mode="chrome-for-testing" --gl=angle`
- if Chromium reports software-only rendering for the key GPU-backed features,
  the pipeline fails before `render_sections` instead of silently falling back
  to CPU rendering
- the default `render_concurrency` is now `4`; override it per run with
  `--set rendering_defaults.render_concurrency=<n>` if a machine needs a
  different value
- the default frame-sequence format is now `jpeg` at quality `80`; override with
  `--set rendering_defaults.frame_sequence_image_format=png` or
  `--set rendering_defaults.frame_sequence_jpeg_quality=<0-100>` if a machine or
  channel needs a different tradeoff
- `--preview-remotion` is unchanged; this GPU gate only applies to
  `render_sections`

### Remotion Studio color preview

For fast visual comparison in Remotion Studio, preview compositions now show a
top-right color panel with a picker button. Opening the picker shows channel
swatches from configs in `config/channels/*.json`, a larger spectrum
grid, a browser color picker, and exact hex entry.

```bash
cd rendering/remotion
npm run preview
```

Use the panel to:

- pick which color prop you are editing for the current composition
- open the picker menu for visual color selection
- apply a channel swatch to that specific target
- choose from a larger palette grid or the browser color picker
- type an exact `#RRGGBB` value
- copy the active hex for reuse in channel config or component props
- reset the current target or reset all preview overrides

This is Studio-only preview behavior: pipeline renders still use the composition
props and channel JSON config until you change those sources directly.

`InfoSlide` preview comps expose separate `Background`, `Backdrop Tint`,
`Title`, `Body`, `Accent`, and keyword `Highlight` targets so you can tune the
card palette directly in Studio without editing code first. `InfoSlide` is
image-backed; `TextOnlySlide` is reserved for test prompt previews that show the
AI image model and prompt without calling image generation.

### CLI flags

| Flag | Purpose |
|---|---|
| `--channel` | Channel slug to load from `config/channels/` (required) |
| `--stage` | Stage control: `script` (that stage only, through the normal pipeline), `..script` (up to), `process..thumbnail` (range) |
| `--workspace` | Target a specific workspace (skips auto-detection) |
| `--preview-remotion` | Run through `process`, stage `_preview/{workspace-name}/` with its own `preview_manifest.json`, update Remotion's active-preview pointer, and open or reuse `FullVideoPreview` in Remotion Studio |
| `--allow-review-failures` | Comma-separated review gates to continue after max retries, such as `image_review,thumbnail,final_review`; failed gates remain flagged in the checkpoint |
| `--fixtures` | Record or replay API responses via `.fixtures/` (`record` or `replay`) |
| `--set` | Override channel config fields with dot notation or top-level global settings such as `gemini_tts_model` (repeatable) |

Useful test override: `--set test.preview_ai_image_prompts=true` skips AI image
generation during image sourcing and shows prompt-preview slides in Remotion.

Stages in order: `planning`, `script`, `image_source`, `audio_source`, `process`, `render_sections`, `assemble`, `thumbnail`, `final_review`.

## Project Structure

```text
video-factory/
├── factory.py                  # CLI entry point + pipeline orchestrator
├── settings.py                 # Global paths + env-driven settings (Pydantic)
├── clients.py                  # Google AI client, fixture replay, and AI traces
├── prompts.py                  # Prompt templates for all stages and review gates
├── core/
│   ├── scripter.py             # Stage 1: Script generation + review loop
│   ├── image_sourcer.py        # Stage 2a: Multi-source image acquisition + review
│   ├── audio_sourcer.py        # Stage 2b: TTS narration + STT timestamps + music
│   ├── processor.py            # Stage 3: Smart crop, face detection, resize
│   ├── render_sections.py      # Stage 4: Per-section Remotion rendering
│   ├── preview_remotion.py     # Workspace-backed Remotion preview manifest + Studio launcher
│   ├── assembler.py            # Stage 5: FFmpeg concat + xfade + audio mix
│   ├── thumbnailer.py          # Stage 6: Thumbnail generation + review
│   ├── reviewer.py             # Universal AI review gate engine
│   ├── costs.py                # Per-run cost ledger, pricing, reconciliation helpers
│   ├── validator.py            # Post-stage invariant checks
│   └── utils.py                # Pydantic models, file I/O, logging
├── tools/
│   ├── log_viewer.py           # Admin HTML report rendering
│   ├── reconcile_gcp_costs.py  # Query Cloud Billing export for actual run cost
│   └── sql/
│       └── reconcile_gcp_costs.sql
├── config/
│   ├── pricing/                # Canonical Google AI pricing catalog
│   └── channels/               # Per-channel JSON configs
│       └── demo_channel.json
├── rendering/remotion/         # Remotion rendering engine (Node.js)
│   ├── src/
│   │   ├── Root.tsx            # Composition registry (entry point)
│   │   ├── components/         # Video components (ImageScene, TitleCard, etc.)
│   │   ├── design/             # Design tokens + Studio palette preview helpers
│   │   └── lib/                # Utilities, types, transitions
│   └── package.json
├── assets/                     # Small static assets; generated/runtime media is gitignored
├── tests/
├── requirements.txt
└── workspace/                  # Runtime output (one folder per run)
```

## How It Works

### Planning

Gemini selects a topic and video type based on the channel's niche, audience, past
topic history (no repeats), and any channel `business_strategy`. When a channel
defines content families, the orchestrator picks one exact `content_family`
randomly by default, or uses `--set plan.content_family=...` when you want to force
one. The plan is enriched with the selected family plus any optional CTA/product
metadata already configured for that channel. The planner still rotates
least-recently-used video type and title format for diversity. When a video type
does not set its own `sections_range`, the auto-derived range now stays capped at
`8-12` sections for long-form videos instead of expanding linearly to 20+ sections.

### Script Generation

Gemini writes a full narration script with per-section image prompts and search
keywords. Script length is now a word-budget contract first: prompts ask for
target total/per-section words, the LLM no longer returns guessed duration
fields, and the pipeline computes `estimated_duration_seconds` from narration
word count after generation. Scripts that are too short or too long by word
budget are revised before review. Optionally receives research context to
ground the script in facts. If the channel plan
includes business context, the script prompt also receives `content_family`, CTA
rules, and any optional offer fields already configured. Channels without real
offers yet can still use the same strategy layer and end on a normal subscribe CTA.
The script stage still asks Gemini for title, description, tags, and thumbnail inputs so
the selected title format and description style are actually applied in the
final package. The simplification only removed music choice, voice variation,
and intra-section transition from the script prompt; those continue to use
their runtime defaults unless another stage overrides them. Gate #1 scores the
script across dimensions such as hook strength, pacing, SEO, factual grounding,
visual structure, content safety, and CTA fit. The demo channel generates
`InfoSlide` media by default, and an `InfoSlide` without sourced media fails
loudly instead of falling back to a text-only layout. Script prompts describe
pacing from narration length instead of asking the LLM for timing math: longer
narration needs more slots, the system enforces the visual hold cap, and
sections that need too many beats should be split. Bad AI output is revised
through the normal script-correction loop instead of being silently normalized
before image/audio work begins.

### Image Sourcing

Each section specifies its image source in the script:

- **google_photo** — real photos via Serper web search
- **stock_photo** — stock photos via Pexels
- **b_roll** — stock video via Pexels
- **ai_photo / ai_illustration** — generated visuals using the channel's
  configured Gemini image model.

Images are sourced in parallel (max 6 concurrent), deduplicated by content hash, and checked against a deterministic minimum source size before processing. For 1920x1080 output, source images must be at least 1280x720 before they can be upscaled. Pexels stock photo results are downloaded as candidates and ranked by Gemini Vision against the slot prompt/keywords before the selected image is saved. Gate #2 reviews relevance via Gemini vision. Slots now carry an explicit `visual_policy` such as `source_as_written`, `photo_backed_info_slide`, `google_photo_exact_action`, `literal_google_photo`, or `single_pose_ai_photo`; image sourcing normalizes that policy once before dispatch instead of applying keyword rescue rules. Authored `text_only_slide` slots are rejected; the only allowed `TextOnlySlide` path is `test.preview_ai_image_prompts=true`, where it renders the model/prompt that would have gone to image generation. `title_card`, `fact_highlight`, `title_banner`, and `subscribe_cta` source their own still backgrounds like any other image-backed slot. If sourcing, relevance review, or required `info_slide` media fails after the configured attempts, the run stops before processing or rendering.

### Audio Sourcing

Per-section TTS via Gemini with configurable voice (name + prompt). Google Cloud STT provides word-level timestamps. Audio is cached by content fingerprint — unchanged sections are skipped on re-runs. Background music is selected from the channel's music pool with audio ducking.

### Per-Run Cost Tracking

Every pipeline run now gets a stable `run_id` in `checkpoint.json`. The orchestrator
records Google AI spend into a workspace-local ledger from the centralized client
layer:

- Gemini text/review calls use `usage_metadata` token counts
- Gemini TTS combines prompt tokens with audio-output-token estimates
- Gemini image generation combines token usage with generated-image count
- STT estimates from billed audio minutes
- fixture replay and supported workspace cache hits are recorded as zero-cost events

The workspace always gets:

- `reports/cost_estimate.json`
- `reports/cost_estimate.html`
- `reports/ai_trace_report.json`

The estimate separates fixed overhead (`planning`, `script`, `thumbnail`,
`final_review`) from variable media spend (`image_source`, `audio_source`) so short
videos make their fixed AI overhead visible.
`reports/cost_estimate.html` now renders in dark mode by default, and the estimate
explicitly excludes Serper/Pexels subscription-plan fees.

<!-- Screenshot: cost_estimate.html dark mode report showing per-stage USD breakdown table -->
![Cost estimate report](docs/screenshots/cost_report.png)

`pipeline.html` is now the main run report. It embeds the checkpoint, plan,
script (when present), cost JSON, and all AI trace details in one page.
`pipeline.log` keeps the short one-line summary, and each `trace=pipeline.html#...`
suffix jumps straight to the matching AI call inside that page. The raw trace
data also stays available in `reports/ai_trace_report.json`.

### Image Processing

Smart crop using OpenCV face detection to preserve subjects. Resizes to target resolution (default 1920x1080).

### Render Sections

Each script section is rendered as a standalone video clip using Remotion's
`SectionComposition`. A shared section-plan builder now produces the canonical
per-section Remotion props, transition metadata, subtitle suppression ranges,
watermark props, and staged static assets for both the production section render
path and the workspace-backed Studio preview path. Each section gets its own
combination of image slots (with Ken Burns-style animation via `ImageScene`),
`InfoCard` `info_card` slots for stylized callouts, `InfoSlide` `info_slide`
slots for titled takeaways with sourced illustrations, and image-backed
`BackdropFigureScene` slots for `TitleCard`, `FactHighlight`, `TitleBanner`,
and `SubscribeCTA`. There is no separate overlay payload anymore. Narration
subtitles and the channel watermark still render as top-level layers. On
non-macOS hosts,
Remotion renders a JPEG sequence by default and FFmpeg encodes the section MP4 with
`h264_nvenc`, so section output does not go through Remotion's CPU `libx264`
path. `TitleBanner` is now just the first slot of its section, not a delayed
triggered overlay. Cached section clips are reused only when their probed
duration still matches the current script audio duration plus the assembler
crossfade pad. Rendering also enforces a hard `max_visual_hold_seconds` cap
(16s by default) across every slot; if a section would leave any visible beat
on screen longer than that, the run fails and the script must add more slots or
split the section. Any section render failure now stops the stage instead of
silently continuing with a partial set of clips.

### Assemble

FFmpeg concatenates section videos with xfade transitions. Mixes narration audio
with optional background music from the active channel's `music_pool`. Applies
overlay effects when configured.

### Thumbnail

Gemini generates the full finished thumbnail from the `thumbnail_strategy` chosen during the script stage, plus the script's exact `thumbnail_text`, `thumbnail_brief`, title, and section-subject context. Thumbnail strategies are defined at the channel level, while each enabled `video_type` whitelists which strategy names the script may choose. A strategy may include an assets-relative `reference_image` plus `reference_instruction` when a recurring subject should guide the image model. Gate #3 reviews exact text readability, strategy fit, title-thumbnail synergy, and content honesty before final package review. If the image model does not produce a thumbnail, the stage fails instead of falling back to a source image or local text overlay.

### Final Review

Extracts 8-12 frames from the video. Gemini vision reviews the full package (frames + thumbnail + metadata) for content-title alignment, policy compliance, and overall quality. A rejected final review fails the run so the workspace keeps the diagnostic frames and checkpoint feedback for investigation.

<!-- Screenshot: pipeline.html showing AI trace cards with Gemini call details, token counts, and stage timings -->
![Pipeline run report](docs/screenshots/pipeline_report.png)

After final review, the workspace contains the finished MP4, `thumbnail.png`,
and metadata for manual upload.

## Channel Configuration

Each channel is a JSON file in `config/channels/`. Key sections:

| Section | Purpose |
|---------|---------|
| `niche` | Category, audience, content style, example/avoid topics |
| `video` | Target duration, resolution, FPS, transitions, music pool, B-roll ratio |
| `video_types` | Listicle, narrative, countdown, explainer — each with pacing, style, optional `numbering_order`, and required `allowed_thumbnail_strategies` for enabled types |
| `voice` | TTS voice name, language, voice prompt (tone/style description) |
| `image_sourcing` | Gemini image model and style prompt suffix for visual consistency |
| `youtube` | Category, tags, title formats, and description styles |
| `script_style` | Tone and writing instructions for the scriptwriter |
| `business_strategy` | Optional channel-level strategy: channel goal, video jobs, content families, CTA rules, and an optional future offer ladder |
| `review_thresholds` | Min scores and max retry attempts per review gate |
| `thumbnail_strategies` | One or more channel-level AI thumbnail strategy definitions; enabled video types whitelist which names they may use, and optional `reference_image` paths are relative to `assets/` and require `reference_instruction` |
| `style` | Visual effects, text colors, transitions, watermark |

### Strategy-Led Channels

Channels can stay purely editorial, but they can also define a `business_strategy`
section that turns the planner and script stages into channel-aware generation:

- `channel_goal` states what the channel is trying to build right now.
- `video_jobs` keeps each video focused on both retention and conversion.
- `content_families` define the only allowed topic families plus the matching lead
  magnet / offer metadata when those exist, and the CTA angle for each family.
- `cta_rules` tell the scriptwriter whether to use a simple subscribe CTA now or a
  lead magnet later without inventing offers that are not configured.
- The orchestrator chooses one family randomly for each new plan unless you force
  it with `--set plan.content_family=...`.

`demo_channel.json` uses this pattern with three generic families:
practical checklists, concept explainers, and workflow stories. It stays on
simple subscribe CTAs only; product fields can be added later in config when
they exist.

## Environment Variables

Configured via `.env` file at project root:

| Variable | Purpose |
|----------|---------|
| `GOOGLE_PROJECT_ID` | Vertex AI project |
| `GOOGLE_CLOUD_LOCATION` | Vertex AI region (default: global) |
| `GOOGLE_STT_LOCATION` | Speech-to-Text region (default: us-central1) |
| `SERPER_API_KEY` | Web image search |
| `PEXELS_API_KEY` | Stock photo fallback |

Model defaults can be overridden in `settings.py` (Gemini text, Gemini TTS, and Gemini image generation).

## GCP Services

Use your own Google Cloud project with billing enabled. The pipeline uses
Application Default Credentials locally.

| API | Service | Used for | Auth |
|-----|---------|----------|------|
| `aiplatform.googleapis.com` | Vertex AI | Gemini text, vision, TTS, and image generation | ADC + project ID |
| `speech.googleapis.com` | Speech-to-Text | Word-level narration timestamps | ADC + project ID |

### Billing Reconciliation

The runtime estimate is immediate. Cloud Billing export is the delayed source of
truth.

1. Enable Cloud Billing export to BigQuery.
2. Prefer the detailed resource export table (`gcp_billing_export_resource_v1_*`).
3. Reconcile a finished workspace:

```bash
python tools/reconcile_gcp_costs.py --workspace "workspace/my_run" --billing-project my-billing-project --dataset billing_export
```

This writes `reports/cost_actual.json` with:

- `gross_cost_usd`
- `credits_usd`
- `net_cost_usd`
- top matched service / SKU rows

Vertex AI requests are labeled with `vf_run`, `vf_stage`, `vf_op`, and
`vf_channel` so the billing export can attribute spend back to a workspace run.
Speech-to-Text remains estimate-only in v1 because it is not matched by the same
run labels.

## Workspace Output

Each run creates `workspace/{channel}_{timestamp}_{uuid}/`:

```text
├── checkpoint.json         # Pipeline state (enables resume via --stage, stores run_id)
├── plan.json               # Topic selection result
├── script.json             # Full script with sections
├── images/
│   ├── raw/                # Source images (downloaded/generated)
│   └── ready/              # Processed images (cropped, resized)
├── audio/
│   ├── sections/           # Per-section WAV + manifest.json (cache)
│   └── narration_full.wav  # Concatenated narration
├── videos/
│   └── sections/           # Per-section Remotion renders
├── YYYY-MM-DD_HHMMSS_title-slug.mp4  # Final assembled video
├── overlays/               # Film grain, color grade assets
├── thumbnail.png           # YouTube thumbnail
├── frames/                 # Extracted frames for final review
└── reports/                # Stage reports + cost_estimate.json/html + cost_actual.json + ai_trace_report.json
```

When preview mode runs, the matching staged static assets live outside the
workspace in `rendering/remotion/public/_preview/{workspace-name}/` so Remotion
Studio can load them via `staticFile()`. The live manifest Studio reads is
`rendering/remotion/public/_preview/{workspace-name}/preview_manifest.json`.
Each run rewrites `rendering/remotion/src/generated/previewManifestVersion.ts`
with the current `_preview/` run index and content hashes, so Remotion Studio
shows all retained preview runs as selectable compositions under the
`PreviewRuns` folder. The
worktree-side `_preview/` staging area keeps only the latest 10 preview bundles;
deleting a workspace does not remove its already-staged Remotion preview folder.
