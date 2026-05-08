"""Tests for API call efficiency optimizations (N-25)."""

import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

from settings import Settings


# ── Settings: gemini_review_model replaces thumbnail_model ────────


def test_settings_has_gemini_review_model():
    s = Settings(GOOGLE_API_KEY="x", GOOGLE_PROJECT_ID="p")
    assert s.gemini_review_model == "gemini-3-flash-preview"


def test_settings_no_thumbnail_model():
    assert "thumbnail_model" not in Settings.model_fields


def test_review_model_is_distinct_from_primary():
    s = Settings(GOOGLE_API_KEY="x", GOOGLE_PROJECT_ID="p")
    assert s.gemini_review_model != s.gemini_primary_model


# ── review_with_vision defaults to review model ──────────────────


def test_review_with_vision_uses_review_model():
    """review_with_vision should default to gemini_review_model, not primary."""
    import clients as clients_mod
    import inspect

    src = inspect.getsource(clients_mod.review_with_vision.__wrapped__)
    assert "gemini_review_model" in src
    assert "gemini_primary_model" not in src


# ── STT parallelization ──────────────────────────────────────────


def _make_test_wav(path: Path, duration_seconds: float, framerate: int = 24000):
    """Create a minimal WAV file with silence."""
    n_frames = int(duration_seconds * framerate)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(framerate)
        wf.writeframes(b"\x00\x00" * n_frames)


def _make_mock_response(words: list[tuple[str, float, float]]):
    """Build a mock STT response with word timestamps."""
    mock_response = MagicMock()
    mock_results = []
    for word, start, end in words:
        mock_word = MagicMock()
        mock_word.word = word
        mock_word.start_offset.total_seconds.return_value = start
        mock_word.end_offset.total_seconds.return_value = end
        mock_alt = MagicMock()
        mock_alt.words = [mock_word]
        mock_result = MagicMock()
        mock_result.alternatives = [mock_alt]
        mock_results.append(mock_result)
    mock_response.results = mock_results
    return mock_response


@patch("core.audio_sourcer.settings")
@patch("core.audio_sourcer.SpeechClient")
def test_stt_transcribes_all_chunks(mock_speech_cls, mock_settings, tmp_path):
    """All audio chunks should be transcribed and merged."""
    from core.audio_sourcer import _transcribe_with_timestamps

    mock_settings.google_project_id = "test-project"
    mock_settings.google_cloud_location = "us-central1"

    # 170s audio → 4 chunks (55, 55, 55, 5)
    wav_path = tmp_path / "test.wav"
    _make_test_wav(wav_path, duration_seconds=170.0)

    mock_client = MagicMock()
    mock_speech_cls.return_value = mock_client
    mock_client.recognize.return_value = _make_mock_response([("word", 0.0, 0.5)])

    with patch("google.auth.default", return_value=(None, "test-project")):
        words = _transcribe_with_timestamps(wav_path, "en")

    assert mock_client.recognize.call_count == 4
    assert len(words) == 4


@patch("core.audio_sourcer.settings")
@patch("core.audio_sourcer.SpeechClient")
def test_stt_preserves_chunk_order_by_timestamps(mock_speech_cls, mock_settings, tmp_path):
    """Words must be merged in chunk order — timestamps should increase."""
    from core.audio_sourcer import _transcribe_with_timestamps

    mock_settings.google_project_id = "test-project"
    mock_settings.google_cloud_location = "us-central1"

    # 120s → 3 chunks at 55s boundaries (0-55, 55-110, 110-120)
    wav_path = tmp_path / "test.wav"
    _make_test_wav(wav_path, duration_seconds=120.0)

    # Each chunk returns one word at local offset 0.0-0.5
    # After time_offset adjustment: chunk0→0.0, chunk1→55.0, chunk2→110.0
    mock_client = MagicMock()
    mock_speech_cls.return_value = mock_client
    mock_client.recognize.return_value = _make_mock_response([("word", 0.0, 0.5)])

    with patch("google.auth.default", return_value=(None, "test-project")):
        words = _transcribe_with_timestamps(wav_path, "en")

    assert len(words) == 3
    # Timestamps must be in ascending order (proves chunk ordering is preserved)
    starts = [w["start"] for w in words]
    assert starts == sorted(starts)
    # First chunk starts at 0, second at ~55, third at ~110
    assert starts[0] == 0.0
    assert 54.0 < starts[1] < 56.0
    assert 109.0 < starts[2] < 111.0


@patch("core.audio_sourcer.settings")
@patch("core.audio_sourcer.SpeechClient")
def test_stt_cleans_up_temp_chunks(mock_speech_cls, mock_settings, tmp_path):
    """Temporary chunk WAV files should be deleted after transcription."""
    from core.audio_sourcer import _transcribe_with_timestamps

    mock_settings.google_project_id = "test-project"
    mock_settings.google_cloud_location = "us-central1"

    wav_path = tmp_path / "test.wav"
    _make_test_wav(wav_path, duration_seconds=120.0)

    mock_client = MagicMock()
    mock_speech_cls.return_value = mock_client
    mock_client.recognize.return_value = _make_mock_response([("word", 0.0, 0.5)])

    with patch("google.auth.default", return_value=(None, "test-project")):
        _transcribe_with_timestamps(wav_path, "en")

    # No .chunk*.wav files should remain
    chunk_files = list(tmp_path.glob("*.chunk*.wav"))
    assert chunk_files == []


def test_stt_max_workers_constant():
    """The STT worker cap should be defined and reasonable."""
    from core.audio_sourcer import _STT_MAX_WORKERS
    assert 1 <= _STT_MAX_WORKERS <= 10


def test_stt_uses_threadpool_executor():
    """_transcribe_with_timestamps should use ThreadPoolExecutor (not sequential)."""
    import inspect
    from core.audio_sourcer import _transcribe_with_timestamps
    src = inspect.getsource(_transcribe_with_timestamps)
    assert "ThreadPoolExecutor" in src
