"""Tests for audio sourcer helpers: WAV concatenation and duration reading."""

import wave
import struct
from pathlib import Path

import pytest
from core.audio_sourcer import (
    _concat_wavs,
    _wav_duration,
)
from core.utils import ScriptSection


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_silence_wav(path: Path, duration: float = 1.0, framerate: int = 24000) -> None:
    """Write a silent WAV file of the given duration."""
    n_frames = int(duration * framerate)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(framerate)
        wf.writeframes(struct.pack(f"<{n_frames}h", *([0] * n_frames)))


# ---------------------------------------------------------------------------
# _wav_duration
# ---------------------------------------------------------------------------

class TestWavDuration:
    def test_reads_duration(self, tmp_path):
        wav = tmp_path / "test.wav"
        _write_silence_wav(wav, duration=2.5)
        dur = _wav_duration(wav)
        assert abs(dur - 2.5) < 0.01


# ---------------------------------------------------------------------------
# _concat_wavs
# ---------------------------------------------------------------------------

class TestConcatWavs:
    def test_concat_two(self, tmp_path):
        a = tmp_path / "a.wav"
        b = tmp_path / "b.wav"
        out = tmp_path / "out.wav"
        _write_silence_wav(a, duration=1.0)
        _write_silence_wav(b, duration=2.0)
        _concat_wavs([a, b], out)
        assert abs(_wav_duration(out) - 3.0) < 0.01

    def test_concat_preserves_params(self, tmp_path):
        a = tmp_path / "a.wav"
        b = tmp_path / "b.wav"
        out = tmp_path / "out.wav"
        _write_silence_wav(a, duration=1.0, framerate=24000)
        _write_silence_wav(b, duration=1.0, framerate=24000)
        _concat_wavs([a, b], out)
        with wave.open(str(out), "rb") as wf:
            assert wf.getframerate() == 24000
            assert wf.getnchannels() == 1

    def test_concat_single(self, tmp_path):
        a = tmp_path / "a.wav"
        out = tmp_path / "out.wav"
        _write_silence_wav(a, duration=1.5)
        _concat_wavs([a], out)
        assert abs(_wav_duration(out) - 1.5) < 0.01

    def test_concat_many(self, tmp_path):
        wavs = []
        for i in range(5):
            p = tmp_path / f"s{i}.wav"
            _write_silence_wav(p, duration=0.5)
            wavs.append(p)
        out = tmp_path / "out.wav"
        _concat_wavs(wavs, out)
        assert abs(_wav_duration(out) - 2.5) < 0.01
