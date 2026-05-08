"""Generate a self-contained HTML log viewer from a pipeline log file."""

import base64
import html
import json
import re
from io import BytesIO
from pathlib import Path
from typing import Any

LOG_LINE_RE = re.compile(
    r"^(?:\d{4}-\d{2}-\d{2}\s+)?(\d{2}:\d{2}:\d{2})(?:[,\.]\d+)?\s*\|\s*(\w+)\s*\|\s*(.*)$"
)
TRACE_RE = re.compile(r"trace=([^\s]+)")

TAG_COLORS = {
    "stage":  "#00bcd4",
    "gemini": "#64b5f6",
    "ai_gen": "#ce93d8",
    "tts":    "#81c784",
}

LEVEL_CLASSES = {
    "INFO":    "info",
    "WARNING": "warn",
    "ERROR":   "error",
    "DEBUG":   "debug",
}

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Pipeline Log — {title}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: #0d1117; color: #c9d1d9; font-family: 'Cascadia Code', 'JetBrains Mono', 'Consolas', monospace;
    font-size: 13px; line-height: 1.6; padding: 0;
  }}
  .header {{
    position: sticky; top: 0; z-index: 10; background: #161b22; border-bottom: 1px solid #30363d;
    padding: 12px 20px; display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
  }}
  .header h1 {{ font-size: 15px; color: #e6edf3; font-weight: 600; }}
  .filters {{ display: flex; gap: 6px; flex-wrap: wrap; }}
  .filters button {{
    background: #21262d; color: #8b949e; border: 1px solid #30363d; border-radius: 6px;
    padding: 3px 10px; font-size: 12px; cursor: pointer; font-family: inherit;
  }}
  .filters button:hover {{ background: #30363d; color: #c9d1d9; }}
  .filters button.active {{ background: #1f6feb; color: #fff; border-color: #1f6feb; }}
  .search {{
    background: #0d1117; color: #c9d1d9; border: 1px solid #30363d; border-radius: 6px;
    padding: 4px 10px; font-size: 12px; font-family: inherit; width: 220px; margin-left: auto;
  }}
  .search:focus {{ outline: none; border-color: #1f6feb; }}
  .log {{ padding: 8px 0; }}
  .stage-group {{ margin: 0; }}
  .stage-header {{
    background: #161b22; padding: 6px 20px; cursor: pointer; display: flex;
    align-items: center; gap: 8px; border-top: 1px solid #21262d;
    position: sticky; top: 52px; z-index: 5;
  }}
  .stage-header:hover {{ background: #1c2128; }}
  .stage-header .arrow {{ color: #484f58; transition: transform 0.15s; font-size: 11px; }}
  .stage-header.collapsed .arrow {{ transform: rotate(-90deg); }}
  .stage-header .name {{ color: #00bcd4; font-weight: 600; }}
  .stage-header .dur {{ color: #8b949e; font-size: 12px; }}
  .stage-body {{ }}
  .stage-body.hidden {{ display: none; }}
  .line {{
    padding: 1px 20px; display: flex; gap: 0; white-space: pre-wrap; word-break: break-all;
  }}
  .line:hover {{ background: #161b22; }}
  .line.warn {{ background: #2d1b00; }}
  .line.warn:hover {{ background: #3b2300; }}
  .line.error {{ background: #2d0000; }}
  .line.error:hover {{ background: #3b0000; }}
  .line.hidden {{ display: none; }}
  .ts {{ color: #484f58; min-width: 70px; flex-shrink: 0; }}
  .lv {{ min-width: 62px; flex-shrink: 0; }}
  .lv.info {{ color: #8b949e; }}
  .lv.warn {{ color: #d29922; }}
  .lv.error {{ color: #f85149; }}
  .lv.debug {{ color: #484f58; }}
  .msg {{ flex: 1; }}
  .tag {{ font-weight: 600; }}
  .tag-stage {{ color: #00bcd4; }}
  .tag-gemini {{ color: #64b5f6; }}
  .tag-ai_gen {{ color: #ce93d8; }}
  .tag-tts {{ color: #81c784; }}
  .dur-val {{ color: #d2a8ff; }}
  .tok {{ color: #7ee787; }}
  .trace-link {{ color: #58a6ff; text-decoration: none; }}
  .trace-link:hover {{ text-decoration: underline; }}
  .artifacts {{
    padding: 16px 20px 0;
    display: grid;
    gap: 16px;
  }}
  .artifact-section {{
    border: 1px solid #30363d;
    border-radius: 10px;
    background: #0f1520;
    overflow: hidden;
  }}
  .artifact-section > summary,
  .artifact-title {{
    cursor: pointer;
    padding: 10px 14px;
    color: #e6edf3;
    font-weight: 600;
    background: #161b22;
    border-bottom: 1px solid #30363d;
  }}
  .artifact-section > summary {{
    list-style: none;
  }}
  .artifact-section > summary::-webkit-details-marker {{ display: none; }}
  .artifact-body {{
    padding: 14px;
  }}
  .artifact-empty {{
    color: #8b949e;
  }}
  .artifact-body pre {{
    margin: 0;
    padding: 14px;
    border: 1px solid #30363d;
    border-radius: 8px;
    background: #161b22;
    overflow: auto;
    white-space: pre-wrap;
    word-break: break-word;
  }}
  .trace-report-meta {{
    margin: 0 0 12px;
    color: #8b949e;
    font-size: 12px;
  }}
  .trace-nav {{
    display: grid;
    gap: 8px;
    margin: 0 0 16px;
  }}
  .trace-card {{
    margin: 0 0 18px;
    border: 1px solid #30363d;
    border-radius: 10px;
    background: #0d1117;
    overflow: hidden;
  }}
  .trace-card-header {{
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 0;
    padding: 14px 16px;
    cursor: pointer;
    list-style: none;
    background: #111821;
    border-bottom: 1px solid #30363d;
  }}
  .trace-card-header::-webkit-details-marker {{ display: none; }}
  .trace-card-header h2 {{
    margin: 0;
    font-size: 16px;
    color: #e6edf3;
  }}
  .trace-card-body {{ padding: 16px; }}
  .pill {{
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 12px;
  }}
  .pill-ok {{ background: #16351f; color: #7ee787; }}
  .pill-error {{ background: #3b1113; color: #f85149; }}
  .pill-empty {{ background: #372b12; color: #d29922; }}
  .trace-card table {{
    width: 100%;
    border-collapse: collapse;
    margin: 0 0 14px;
  }}
  .trace-card th, .trace-card td {{
    border: 1px solid #30363d;
    padding: 8px 10px;
    vertical-align: top;
    text-align: left;
  }}
  .trace-card th {{
    width: 180px;
    color: #8b949e;
    background: #161b22;
  }}
  .trace-card td {{ background: #0d1117; }}
  .trace-block {{ margin: 0 0 14px; }}
  .trace-block h3 {{
    margin: 0 0 8px;
    color: #7ee787;
    font-size: 13px;
  }}
  .summary {{
    background: #161b22; border-top: 1px solid #30363d; padding: 12px 20px;
    display: flex; gap: 24px; flex-wrap: wrap; font-size: 12px; color: #8b949e;
  }}
  .summary .val {{ color: #e6edf3; font-weight: 600; }}
</style>
</head>
<body>
<div class="header">
  <h1>{title}</h1>
  <div class="filters" id="filters">
    <button class="active" data-filter="all">All</button>
    <button data-filter="stage">stage</button>
    <button data-filter="gemini">gemini</button>
    <button data-filter="ai_gen">ai_gen</button>
    <button data-filter="tts">tts</button>
    <button data-filter="warn">warnings</button>
    <button data-filter="error">errors</button>
  </div>
  <input type="text" class="search" id="search" placeholder="Search logs…">
</div>
<div class="artifacts">{artifact_body}</div>
<div class="log" id="log">{log_body}</div>
<div class="summary">{summary}</div>
<script>
document.querySelectorAll('.stage-header').forEach(h => {{
  h.addEventListener('click', () => {{
    h.classList.toggle('collapsed');
    h.nextElementSibling.classList.toggle('hidden');
  }});
}});
function revealHashTarget() {{
  if (!window.location.hash) return;
  const target = document.querySelector(window.location.hash);
  if (!target) return;
  const details = target.closest('details');
  if (details) details.open = true;
}}
const lines = document.querySelectorAll('.line');
const btns = document.querySelectorAll('#filters button');
const search = document.getElementById('search');
function applyFilters() {{
  const active = document.querySelector('#filters button.active');
  const f = active ? active.dataset.filter : 'all';
  const q = search.value.toLowerCase();
  lines.forEach(el => {{
    let show = true;
    if (f !== 'all') {{
      if (f === 'warn' || f === 'error') show = el.classList.contains(f);
      else show = el.dataset.tags && el.dataset.tags.includes(f);
    }}
    if (show && q) show = el.textContent.toLowerCase().includes(q);
    el.classList.toggle('hidden', !show);
  }});
  document.querySelectorAll('.stage-group').forEach(g => {{
    const body = g.querySelector('.stage-body');
    if (!body) return;
    const hasVisible = body.querySelector('.line:not(.hidden)');
    g.style.display = hasVisible || f === 'all' ? '' : 'none';
  }});
}}
btns.forEach(b => b.addEventListener('click', () => {{
  btns.forEach(x => x.classList.remove('active'));
  b.classList.add('active');
  applyFilters();
}}));
search.addEventListener('input', applyFilters);
window.addEventListener('hashchange', revealHashTarget);
revealHashTarget();
</script>
</body>
</html>
"""

TAG_RE = re.compile(r"^\[(\w+)\]")
STAGE_START_RE = re.compile(r"^\[stage\]\s+(.+?)\s+started$")
STAGE_COMPLETE_RE = re.compile(r"^\[stage\]\s+(.+?)\s+completed in\s+(\d+\.\d+s)$")

_STAGE_TAG_TARGETS = {
    "tts": "audio_source",
    "ai_gen": "image_source",
    "script_review": "script",
    "image_review": "image_source",
    "thumbnail_review": "thumbnail",
    "final_review": "final_review",
}

_GEMINI_HINTS = {
    "planning": (
        "select a topic and video type",
    ),
    "script": (
        "write a full youtube narration script",
        "your script duration is outside the allowed range",
        "review this youtube video script",
    ),
    "image_source": (
        "review these images sourced",
    ),
    "thumbnail": (
        "generate the final 1280x720 youtube thumbnail image",
        "review this youtube thumbnail",
        "thumbnail.png",
    ),
    "final_review": (
        "final review before youtube upload",
    ),
}

_STAGE_HINTS = {
    "planning": (
        "content family selected randomly",
        "content family:",
        "lead magnet:",
        "low-ticket offer:",
        "topic selected:",
        "video type:",
        "angle:",
        "title format:",
        "description style:",
        "tag pool:",
        "narrative hook:",
    ),
    "script": (
        "generating script:",
        "script duration invalid",
        "script duration ok",
        "script saved:",
    ),
    "image_source": (
        "sourcing illustration for",
        "sourced section_",
        "b-roll prepared:",
        "removing rejected b-roll",
        "rejected - generating with ai_gen",
    ),
    "audio_source": (
        "voice variation",
        "voice prompt selected",
        "generating tts per section",
        "stt transcribed",
        "(offset ",
        "section durations from stt",
        "full narration:",
        "music pool:",
        "background music",
    ),
    "process": (
        "processed:",
        "processed ",
    ),
    "thumbnail": (
        "thumbnail strategy:",
    ),
    "render_sections": (
        "rendering ",
        "slots [",
    ),
    "assemble": (
        "per-section transitions from script",
        "concatenating ",
        "final encode:",
        "video assembled:",
        "output:",
    ),
}



def generate_image_source_html_report(report_data: dict, workspace: Path, report_path: Path) -> Path:
    """Generate a standalone HTML visual report for image_source results."""
    from PIL import Image as PILImage

    result = report_data.get("result") or {}
    sourcing_log = result.get("sourcing_log", [])
    review_history = result.get("review_history", [])
    raw_dir = workspace / "images" / "raw"
    rejected_dir = raw_dir / "rejected"

    def _encode_image(path: Path) -> str:
        """Encode an image as a base64 data URI, resized to ~800px."""
        if not path.exists():
            return ""
        try:
            img = PILImage.open(path)
            img.thumbnail((800, 800))
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=80)
            b64 = base64.b64encode(buf.getvalue()).decode()
            return f"data:image/jpeg;base64,{b64}"
        except Exception:
            return ""

    # Build lookup: (section_id, sub_idx) -> sourcing info
    sourcing_by_key: dict[tuple[int, int], list[dict]] = {}
    for entry in sourcing_log:
        key = (entry["section_id"], entry.get("sub_image_index", 1))
        sourcing_by_key.setdefault(key, []).append(entry)

    # Build lookup: (section_id, sub_idx) -> latest review result per attempt
    review_by_key: dict[tuple[int, int], list[dict]] = {}
    for attempt_data in review_history:
        for img_r in attempt_data.get("image_results", []):
            key = (img_r["section_id"], img_r.get("sub_image_index", 1))
            review_by_key.setdefault(key, []).append({
                "attempt": attempt_data.get("attempt", 0),
                **img_r,
            })

    # Collect all unique image keys
    all_keys: list[tuple[int, int]] = []
    seen = set()
    for entry in sourcing_log:
        key = (entry["section_id"], entry.get("sub_image_index", 1))
        if key not in seen:
            all_keys.append(key)
            seen.add(key)

    # Counts
    total = len(all_keys)
    approved_count = 0
    rejected_count = 0
    warning_count = 0

    cards_html = []
    for section_id, sub_idx in all_keys:
        sources = sourcing_by_key.get((section_id, sub_idx), [])
        reviews = review_by_key.get((section_id, sub_idx), [])
        latest_review = reviews[-1] if reviews else {}
        latest_source = sources[-1] if sources else {}

        # Determine status from latest review
        is_approved = latest_review.get("approved", True)
        severity = latest_review.get("severity", "ok" if is_approved else "error")
        issues = latest_review.get("issues", [])
        suggestion = latest_review.get("suggestion", "")

        if severity == "error":
            rejected_count += 1
            badge_color = "#e74c3c"
            badge_label = "REJECTED"
        elif severity == "warning":
            warning_count += 1
            badge_color = "#f39c12"
            badge_label = "WARNING"
            approved_count += 1
        else:
            approved_count += 1
            badge_color = "#27ae60"
            badge_label = "OK"

        # Encode current image as base64
        filename = latest_source.get("file", f"section_{section_id:03d}_{sub_idx:02d}.jpg")
        img_path = raw_dir / filename
        if not img_path.exists():
            for ext in (".png", ".jpeg", ".webp"):
                alt = raw_dir / (img_path.stem + ext)
                if alt.exists():
                    img_path = alt
                    break

        img_data_uri = _encode_image(img_path)

        # Source info
        source = latest_source.get("source", "unknown")
        keywords = latest_source.get("keywords") or latest_source.get("original_keywords") or latest_source.get("ai_gen_prompt", "")

        # Regeneration info, including the rejected original image.
        regen_html = ""
        regen_entries = [s for s in sources if s.get("phase") == "regeneration"]
        if regen_entries:
            r = regen_entries[-1]
            # Try to find the rejected original in rejected/ folder
            rejected_path = rejected_dir / filename
            rejected_uri = _encode_image(rejected_path)
            rejected_img_html = (
                f'<img src="{rejected_uri}" class="rejected-thumb" onclick="zoom(this)" />'
                if rejected_uri else '<span class="no-img">Original not saved</span>'
            )
            regen_html = f"""<div class="regen">
                <span class="regen-label">Regenerated</span>
                <div>Original keywords: <code>{r.get('original_keywords', '')}</code></div>
                <div>AI generation prompt: <code>{r.get('ai_gen_prompt', '')}</code></div>
                <div>Reason: {r.get('rejection_reason', '')}</div>
                <div class="rejected-original">
                    <div class="rejected-label">Rejected original:</div>
                    {rejected_img_html}
                </div>
            </div>"""

        issues_html = ""
        if issues:
            items = "".join(f"<li>{iss}</li>" for iss in issues)
            issues_html = f'<ul class="issues">{items}</ul>'

        suggestion_html = ""
        if suggestion:
            suggestion_html = f'<div class="suggestion">{suggestion}</div>'

        img_tag = (
            f'<img src="{img_data_uri}" class="thumb" onclick="zoom(this)" />'
            if img_data_uri else '<div class="no-img">No image</div>'
        )

        cards_html.append(f"""<div class="card">
            <div class="card-img">{img_tag}</div>
            <div class="card-info">
                <div class="card-header">
                    <span class="filename">{filename}</span>
                    <span class="badge" style="background:{badge_color}">{badge_label}</span>
                </div>
                <div class="meta">Section {section_id}.{sub_idx} &middot; Source: <b>{source}</b> &middot; Keywords: <code>{keywords}</code></div>
                {issues_html}
                {suggestion_html}
                {regen_html}
            </div>
        </div>""")

    cards_joined = "\n".join(cards_html)
    ran_at = report_data.get("ran_at", "")
    duration = report_data.get("duration_seconds", 0)
    attempts = result.get("attempts", 0)

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>Image Source Report</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#1a1a2e;color:#e0e0e0;font-family:system-ui,-apple-system,sans-serif;padding:24px}}
.summary{{display:flex;gap:16px;margin-bottom:24px;flex-wrap:wrap}}
.stat{{background:#16213e;border-radius:8px;padding:16px 24px;text-align:center;min-width:120px}}
.stat .num{{font-size:2em;font-weight:bold}}
.stat.approved .num{{color:#27ae60}}
.stat.rejected .num{{color:#e74c3c}}
.stat.warning .num{{color:#f39c12}}
.stat.total .num{{color:#3498db}}
.meta-bar{{color:#888;margin-bottom:24px;font-size:0.9em}}
.card{{display:flex;gap:16px;background:#16213e;border-radius:8px;margin-bottom:12px;overflow:hidden}}
.card-img{{flex:0 0 280px;background:#0f0f23;display:flex;align-items:center;justify-content:center;min-height:180px}}
.card-img img.thumb{{width:280px;height:auto;display:block;cursor:pointer}}
.no-img{{color:#555;font-style:italic}}
.card-info{{padding:16px;flex:1;min-width:0}}
.card-header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}}
.filename{{font-weight:bold;font-size:1.1em}}
.badge{{padding:4px 12px;border-radius:4px;color:#fff;font-size:0.8em;font-weight:bold}}
.meta{{color:#999;font-size:0.85em;margin-bottom:8px}}
.meta code{{background:#0f0f23;padding:2px 6px;border-radius:3px;color:#ccc}}
.issues{{list-style:disc;padding-left:20px;color:#f39c12;font-size:0.9em;margin:6px 0}}
.suggestion{{color:#3498db;font-size:0.9em;margin:4px 0}}
.regen{{background:#1a1a3e;border-left:3px solid #9b59b6;padding:8px 12px;margin-top:8px;border-radius:0 4px 4px 0;font-size:0.85em}}
.regen-label{{color:#9b59b6;font-weight:bold}}
.regen code{{background:#0f0f23;padding:2px 6px;border-radius:3px;color:#ccc}}
.rejected-original{{margin-top:8px}}
.rejected-label{{color:#e74c3c;font-weight:bold;font-size:0.85em;margin-bottom:4px}}
.rejected-thumb{{max-width:220px;height:auto;border:2px solid #e74c3c;border-radius:4px;cursor:pointer;opacity:0.85}}
h1{{margin-bottom:8px}}
#overlay{{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.9);z-index:1000;cursor:pointer;justify-content:center;align-items:center}}
#overlay img{{max-width:95%;max-height:95%;object-fit:contain}}
</style></head><body>
<h1>Image Source Report</h1>
<div class="meta-bar">{ran_at} &middot; {duration}s &middot; {attempts} review attempt(s)</div>
<div class="summary">
    <div class="stat total"><div class="num">{total}</div><div>Total</div></div>
    <div class="stat approved"><div class="num">{approved_count}</div><div>Approved</div></div>
    <div class="stat rejected"><div class="num">{rejected_count}</div><div>Rejected</div></div>
    <div class="stat warning"><div class="num">{warning_count}</div><div>Warnings</div></div>
</div>
{cards_joined}
<div id="overlay" onclick="this.style.display='none'"><img id="overlay-img"></div>
<script>
function zoom(el){{var o=document.getElementById('overlay');document.getElementById('overlay-img').src=el.src;o.style.display='flex'}}
</script>
</body></html>"""

    html_path = report_path.with_suffix(".html")
    html_path.write_text(html, encoding="utf-8")
    return html_path



def _format_usd(value: float | None) -> str:
    return f"${value:.6f}" if value is not None else "n/a"


def render_estimate_html(report: dict[str, Any]) -> str:
    summary = report["summary"]
    rows = []
    for row in report["top_contributors"]:
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(row['stage']))}</td>"
            f"<td>{html.escape(str(row['operation']))}</td>"
            f"<td>{html.escape(str(row['model']))}</td>"
            f"<td>{row['event_count']}</td>"
            f"<td>{_format_usd(row['estimated_usd'])}</td>"
            "</tr>"
        )
    missing_items = "".join(
        f"<li>{html.escape(item['service'])} / {html.escape(item['model'])}: {html.escape(item['reason'])}</li>"
        for item in report["missing_pricing"]
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Cost Estimate</title>
<style>
:root {{
  --bg: #0d1117;
  --panel: #161b22;
  --panel-strong: #1c2128;
  --text: #e6edf3;
  --muted: #8b949e;
  --border: #30363d;
  --accent: #58a6ff;
  --accent-soft: rgba(88, 166, 255, 0.12);
  --warn-text: #ffb4a8;
  --warn-border: #6e2f2f;
  --warn-bg: rgba(248, 81, 73, 0.12);
}}
* {{ box-sizing: border-box; }}
body {{
  font-family: Arial, sans-serif;
  margin: 0;
  background: var(--bg);
  color: var(--text);
}}
.page {{
  max-width: 1080px;
  margin: 0 auto;
  padding: 24px;
}}
.card {{
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 20px 22px;
  box-shadow: 0 12px 30px rgba(0, 0, 0, 0.18);
}}
h1, h2 {{
  margin: 0 0 14px;
}}
h1 {{
  font-size: 28px;
}}
h2 {{
  font-size: 18px;
  margin-top: 28px;
}}
p {{
  margin: 10px 0;
  color: var(--muted);
}}
strong {{
  color: var(--text);
}}
a {{
  color: var(--accent);
}}
table {{
  border-collapse: collapse;
  width: 100%;
  margin-top: 16px;
  overflow: hidden;
  border-radius: 12px;
  border: 1px solid var(--border);
}}
th, td {{
  border-bottom: 1px solid var(--border);
  padding: 10px 12px;
  text-align: left;
}}
th {{
  background: var(--panel-strong);
  color: var(--text);
}}
tr:last-child td {{
  border-bottom: none;
}}
tr:nth-child(even) td {{
  background: rgba(255, 255, 255, 0.015);
}}
.warn {{
  color: var(--warn-text);
  background: var(--warn-bg);
  border: 1px solid var(--warn-border);
  border-radius: 12px;
  padding: 14px 16px;
  margin-top: 18px;
}}
.warn h2 {{
  margin-top: 0;
}}
.mono {{ font-family: Consolas, monospace; color: var(--text); }}
.note {{
  margin-top: 18px;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: var(--accent-soft);
  color: var(--muted);
}}
</style>
</head>
<body>
<div class="page">
<div class="card">
<h1>Per-Run Cost Estimate</h1>
<p><strong>Run:</strong> <span class="mono">{html.escape(report['run_id'])}</span></p>
<p><strong>Channel:</strong> <span class="mono">{html.escape(report['channel'])}</span></p>
<p><strong>Total estimated:</strong> {_format_usd(summary['estimated_usd'])}</p>
<p><strong>Fixed overhead:</strong> {_format_usd(summary['fixed_overhead_usd'])}</p>
<p><strong>Variable media:</strong> {_format_usd(summary['variable_media_usd'])}</p>
<p><strong>Cache hits:</strong> {summary['cache_hit_count']}</p>
<p><strong>Incomplete:</strong> {report['incomplete']}</p>
{f'<div class="warn"><h2>Missing pricing</h2><ul>{missing_items}</ul></div>' if missing_items else ''}
<h2>Top Contributors</h2>
<table>
<thead>
<tr><th>Stage</th><th>Operation</th><th>Model</th><th>Events</th><th>Estimated USD</th></tr>
</thead>
<tbody>
{''.join(rows) if rows else '<tr><td colspan="5">No cost events recorded.</td></tr>'}
</tbody>
</table>
<div class="note">
  Serper and Pexels subscription or API-plan fees are not included in this AI estimate.
</div>
</div>
</div>
</body>
</html>"""

def _format_message(msg: str) -> tuple[str, str]:
    """Add color spans to tags, durations, and token counts in the message."""
    escaped = html.escape(msg)

    # Color tags like [gemini], [stage], etc.
    tag_match = TAG_RE.match(msg)
    tag_name = ""
    if tag_match:
        tag_name = tag_match.group(1)
        tag_class = f"tag-{tag_name}" if tag_name in TAG_COLORS else "tag"
        escaped_tag = html.escape(tag_match.group(0))
        escaped = escaped.replace(escaped_tag, f'<span class="tag {tag_class}">{escaped_tag}</span>', 1)

    # Color durations like "17.2s"
    escaped = re.sub(
        r"(\d+\.\d+)s",
        r'<span class="dur-val">\1s</span>',
        escaped,
    )

    # Color token counts like "1840 in + 3200 out tokens"
    escaped = re.sub(
        r"(\d+) in \+ (\d+) out tokens",
        r'<span class="tok">\1 in + \2 out tokens</span>',
        escaped,
    )

    escaped = TRACE_RE.sub(
        lambda match: (
            'trace=<a class="trace-link" href="'
            f'{html.escape(match.group(1), quote=True)}">'
            f'{html.escape(match.group(1))}</a>'
        ),
        escaped,
    )

    return escaped, tag_name


def _match_any(lower_msg: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern in lower_msg for pattern in patterns)


def _parse_stage_start(msg: str) -> str | None:
    match = STAGE_START_RE.match(msg)
    return match.group(1) if match else None


def _parse_stage_complete(msg: str) -> tuple[str, str] | None:
    match = STAGE_COMPLETE_RE.match(msg)
    if not match:
        return None
    return match.group(1), match.group(2)


def _infer_validate_stage(msg: str, active_stages: list[str]) -> list[str]:
    lower = msg.lower()
    if "script:" in lower:
        return ["script"]
    if "raw_images:" in lower:
        return ["image_source"]
    if "ready_images:" in lower:
        if "process" in active_stages:
            return ["process"]
        if "assemble" in active_stages:
            return ["assemble"]
        return ["process"]
    if "audio:" in lower:
        if "assemble" in active_stages:
            return ["assemble"]
        return ["audio_source"]
    if "video:" in lower:
        return ["assemble"]
    if "thumbnail:" in lower:
        return ["thumbnail"]
    return []


def _infer_stage_targets(
    msg: str,
    tag_name: str,
    active_stages: list[str],
    last_stage_by_tag: dict[str, str],
) -> list[str]:
    lower = msg.lower()

    if tag_name == "validate":
        return _infer_validate_stage(msg, active_stages)

    target = _STAGE_TAG_TARGETS.get(tag_name)
    if target:
        return [target]

    if tag_name == "gemini":
        for stage, patterns in _GEMINI_HINTS.items():
            if _match_any(lower, patterns):
                return [stage]

    for stage, patterns in _STAGE_HINTS.items():
        if _match_any(lower, patterns):
            return [stage]

    if tag_name:
        remembered = last_stage_by_tag.get(tag_name)
        if remembered and remembered in active_stages:
            return [remembered]

    if len(active_stages) == 1:
        return [active_stages[0]]

    return []


def _load_json_text(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return json.dumps(payload, ensure_ascii=False, indent=2)
    except Exception:
        return path.read_text(encoding="utf-8")


def _artifact_block(title: str, body: str, *, open_by_default: bool = False) -> str:
    if not body:
        return ""
    open_attr = " open" if open_by_default else ""
    return (
        f'<details class="artifact-section"{open_attr}>'
        f"<summary>{html.escape(title)}</summary>"
        f'<div class="artifact-body">{body}</div>'
        f"</details>"
    )


def _render_json_artifact(title: str, path: Path, *, open_by_default: bool = False) -> str:
    json_text = _load_json_text(path)
    if not json_text:
        return ""
    return _artifact_block(title, f"<pre>{html.escape(json_text)}</pre>", open_by_default=open_by_default)


def _render_trace_artifact(path: Path) -> str:
    import clients as ai_trace

    report = ai_trace.load_report(path)
    if not report:
        return ""
    body = ai_trace.render_embedded_html(report)
    return (
        '<details class="artifact-section" id="ai-traces" open>'
        '<summary>AI Traces</summary>'
        f'<div class="artifact-body">{body}</div>'
        "</details>"
    )


def _render_workspace_artifacts(workspace: Path) -> str:
    reports = workspace / "reports"
    parts = [
        _render_json_artifact("Checkpoint", workspace / "checkpoint.json"),
        _render_json_artifact("Plan", workspace / "plan.json"),
        _render_json_artifact("Script", workspace / "script.json"),
        _render_json_artifact("Cost Estimate", reports / "cost_estimate.json", open_by_default=True),
        _render_json_artifact("Cost Actual", reports / "cost_actual.json"),
        _render_trace_artifact(reports / "ai_trace_report.json"),
    ]
    return "".join(part for part in parts if part)


def generate_log_html(log_path: Path, output_path: Path) -> Path:
    """Parse a log file and generate an HTML viewer.

    Returns the output path.
    """
    lines = log_path.read_text(encoding="utf-8").splitlines()

    stage_order: list[str] = []
    stage_lines: dict[str, list[str]] = {}
    stage_durations: dict[str, str] = {}
    active_stages: list[str] = []
    last_stage_by_tag: dict[str, str] = {}
    total_lines = 0
    warn_count = 0
    error_count = 0

    # Lines outside any stage
    pre_stage_lines: list[str] = []

    for raw_line in lines:
        m = LOG_LINE_RE.match(raw_line)
        if not m:
            continue

        ts, level, msg = m.group(1), m.group(2).strip(), m.group(3).strip()
        total_lines += 1
        lv_class = LEVEL_CLASSES.get(level, "info")
        if level == "WARNING":
            warn_count += 1
        elif level == "ERROR":
            error_count += 1

        stage_started = _parse_stage_start(msg)
        if stage_started:
            if stage_started not in stage_order:
                stage_order.append(stage_started)
            stage_lines.setdefault(stage_started, [])
            if stage_started not in active_stages:
                active_stages.append(stage_started)
            continue

        stage_completed = _parse_stage_complete(msg)
        if stage_completed:
            stage_name, stage_duration = stage_completed
            if stage_name not in stage_order:
                stage_order.append(stage_name)
            stage_lines.setdefault(stage_name, [])
            stage_durations[stage_name] = stage_duration
            if stage_name in active_stages:
                active_stages.remove(stage_name)
            continue

        formatted_msg, tag_name = _format_message(msg)
        tags = tag_name if tag_name else ""

        line_html = (
            f'<div class="line {lv_class}" data-tags="{tags}">'
            f'<span class="ts">{ts}</span>'
            f'<span class="lv {lv_class}">{level:<7s}</span>'
            f'<span class="msg">{formatted_msg}</span>'
            f'</div>'
        )

        targets = _infer_stage_targets(msg, tag_name, active_stages, last_stage_by_tag)
        if targets:
            for target_stage in targets:
                if target_stage not in stage_order:
                    stage_order.append(target_stage)
                stage_lines.setdefault(target_stage, []).append(line_html)
            if tag_name:
                last_stage_by_tag[tag_name] = targets[0]
        else:
            pre_stage_lines.append(line_html)

    body_parts: list[str] = []
    stages_seen: list[tuple[str, str]] = []
    for stage_name in stage_order:
        lines_for_stage = stage_lines.get(stage_name, [])
        stage_duration = stage_durations.get(stage_name, "")
        if not lines_for_stage and not stage_duration:
            continue
        dur_display = f" — {stage_duration}" if stage_duration else ""
        body_parts.append(
            f'<div class="stage-group">'
            f'<div class="stage-header">'
            f'<span class="arrow">▼</span>'
            f'<span class="name">{html.escape(stage_name)}</span>'
            f'<span class="dur">{dur_display}</span>'
            f'</div>'
            f'<div class="stage-body">{"".join(lines_for_stage)}</div>'
            f'</div>'
        )
        stages_seen.append((stage_name, stage_duration))

    full_body = "".join(pre_stage_lines) + "".join(body_parts)

    # Summary
    summary_parts = [
        f'<span><span class="val">{total_lines}</span> log lines</span>',
        f'<span><span class="val">{len(stages_seen)}</span> stages</span>',
    ]
    if warn_count:
        summary_parts.append(f'<span style="color:#d29922"><span class="val">{warn_count}</span> warnings</span>')
    if error_count:
        summary_parts.append(f'<span style="color:#f85149"><span class="val">{error_count}</span> errors</span>')
    for sname, sdur in stages_seen:
        if sdur:
            summary_parts.append(f'<span>{html.escape(sname)}: <span class="val">{sdur}</span></span>')

    title = log_path.stem
    workspace = output_path.parent
    output_path.write_text(
        HTML_TEMPLATE.format(
            title=html.escape(title),
            artifact_body=_render_workspace_artifacts(workspace),
            log_body=full_body,
            summary=" ".join(summary_parts),
        ),
        encoding="utf-8",
    )
    return output_path
