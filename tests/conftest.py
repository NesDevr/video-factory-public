"""Shared pytest fixtures for video-factory tests."""

import json
from pathlib import Path

import pytest

from core.utils import (
    WORKSPACE_DIR,
    ChannelConfig,
    load_channel_config,
    load_script,
    find_latest_workspace,
)

CHANNELS_DIR = Path(__file__).resolve().parent.parent / "config" / "channels"


def _channel_slugs() -> list[str]:
    return [
        p.stem for p in sorted(CHANNELS_DIR.glob("*.json"))
        if not p.stem.startswith("_")
    ]


@pytest.fixture(params=_channel_slugs())
def channel_slug(request):
    return request.param


@pytest.fixture
def channel_config(channel_slug):
    return load_channel_config(channel_slug)


@pytest.fixture
def latest_workspace(channel_slug):
    ws = find_latest_workspace(channel_slug)
    if ws is None:
        pytest.skip(f"No workspace for {channel_slug}")
    return ws


@pytest.fixture
def workspace_script(latest_workspace):
    script_path = latest_workspace / "script.json"
    if not script_path.exists():
        pytest.skip("No script.json in workspace")
    return load_script(latest_workspace)
