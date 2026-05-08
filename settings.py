"""Global settings — paths, defaults, thresholds."""

import functools
import re
import subprocess
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field


PROJECT_ROOT = Path(__file__).resolve().parent


def _resolve_main_repo_root() -> Path:
    """Find the main repo root, even when running from a git worktree.

    Bundled assets (music, SFX) live in the main repo and are gitignored,
    so they aren't copied into worktrees. This resolves to the main repo
    so assets are always found.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        )
        if result.returncode == 0:
            git_common = Path(result.stdout.strip())
            if not git_common.is_absolute():
                git_common = (PROJECT_ROOT / git_common).resolve()
            main_root = git_common.parent
            if (main_root / "assets").exists():
                return main_root
    except Exception as e:
        import logging
        logging.getLogger("video_factory").debug(f"Worktree detection skipped: {e}")
    return PROJECT_ROOT


MAIN_REPO_ROOT = _resolve_main_repo_root()
ASSETS_DIR = MAIN_REPO_ROOT / "assets"

CHANNELS_DIR = PROJECT_ROOT / "config" / "channels"
DATA_DIR = MAIN_REPO_ROOT / "data"
LOGS_DIR = MAIN_REPO_ROOT / "logs"
WORKSPACE_DIR = MAIN_REPO_ROOT / "workspace"

# Ensure runtime dirs exist
for _d in (DATA_DIR, LOGS_DIR, WORKSPACE_DIR):
    _d.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    """Environment-driven settings (override via env vars or .env)."""

    # Google AI
    google_project_id: str = Field(default="", alias="GOOGLE_PROJECT_ID")

    # Image sourcing
    serper_api_key: str = Field(default="", alias="SERPER_API_KEY")
    pexels_api_key: str = Field(default="", alias="PEXELS_API_KEY")

    # Gemini models
    gemini_primary_model: str = "gemini-3.1-pro-preview"
    gemini_review_model: str = "gemini-3-flash-preview"
    gemini_tts_model: str = "gemini-2.5-pro-tts"
    gemini_image_model: str = "gemini-3.1-flash-image-preview"

    # Vertex AI
    google_cloud_location: str = Field(default="global", alias="GOOGLE_CLOUD_LOCATION")
    google_stt_location: str = Field(default="us-central1", alias="GOOGLE_STT_LOCATION")

    # Rendering
    ffmpeg_path: str = "ffmpeg"
    remotion_project_path: str = str(PROJECT_ROOT / "rendering" / "remotion")

    model_config = {"env_file": str(PROJECT_ROOT / ".env"), "extra": "ignore"}


settings = Settings()


@functools.lru_cache(maxsize=1)
def get_remotion_compositions() -> tuple[str, ...]:
    """Read available Remotion composition IDs from Root.tsx (single source of truth)."""
    root_tsx = Path(settings.remotion_project_path) / "src" / "Root.tsx"
    if not root_tsx.exists():
        return ()
    return tuple(re.findall(r'id="(\w+)"', root_tsx.read_text(encoding="utf-8")))
