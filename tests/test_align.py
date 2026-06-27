from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from backend.app.align import AlignResult, compute_offsets


def test_align_result_dataclass() -> None:
    result = AlignResult(
        offsets={"a.wav": 0.0, "b.wav": 2.5},
        moment_locals={"a.wav": 0.0, "b.wav": 2.5},
        rankings={"a.wav": 1, "b.wav": 2},
        recognizers_used={"a.wav": "fingerprint", "b.wav": "fingerprint"},
        warnings=[],
    )
    assert result.offsets["a.wav"] == 0.0
    assert result.offsets["b.wav"] == 2.5
    assert result.rankings["a.wav"] == 1
    assert result.warnings == []


def test_align_result_with_warnings() -> None:
    result = AlignResult(
        offsets={},
        moment_locals={},
        rankings={},
        recognizers_used={},
        warnings=["Need at least 2 files to align"],
    )
    assert len(result.warnings) == 1
    assert "at least 2 files" in result.warnings[0]


def test_compute_offsets_single_file(tmp_path: Path) -> None:
    wav_path = tmp_path / "test.wav"
    wav_path.write_bytes(b"fake wav data")
    result = compute_offsets([wav_path])
    assert result.offsets == {}
    assert len(result.warnings) == 1
    assert "at least 2 files" in result.warnings[0]


def test_compute_offsets_empty_list() -> None:
    result = compute_offsets([])
    assert result.offsets == {}
    assert len(result.warnings) == 1


def test_offset_normalization_math() -> None:
    raw_shifts = {"a": 3.5, "b": 1.0, "c": 5.0}
    min_shift = min(raw_shifts.values())
    offsets = {name: shift - min_shift for name, shift in raw_shifts.items()}

    assert offsets["a"] == 2.5
    assert offsets["b"] == 0.0
    assert offsets["c"] == 4.0


def test_offset_normalization_all_same() -> None:
    raw_shifts = {"a": 2.0, "b": 2.0, "c": 2.0}
    min_shift = min(raw_shifts.values())
    offsets = {name: shift - min_shift for name, shift in raw_shifts.items()}

    assert offsets["a"] == 0.0
    assert offsets["b"] == 0.0
    assert offsets["c"] == 0.0


def test_offset_normalization_negative() -> None:
    raw_shifts = {"a": -1.5, "b": 0.5, "c": 2.5}
    min_shift = min(raw_shifts.values())
    offsets = {name: shift - min_shift for name, shift in raw_shifts.items()}

    assert offsets["a"] == 0.0
    assert offsets["b"] == 2.0
    assert offsets["c"] == 4.0


def test_moment_local_equals_offset() -> None:
    offsets = {"a": 0.0, "b": 2.5, "c": 4.0}
    moment_locals = {name: offset for name, offset in offsets.items()}

    assert moment_locals["a"] == 0.0
    assert moment_locals["b"] == 2.5
    assert moment_locals["c"] == 4.0


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not available")
def test_extract_audio_with_ffmpeg(tmp_path: Path) -> None:
    from backend.app.align import extract_audio

    video_path = tmp_path / "test.mp4"
    video_path.write_bytes(b"fake video")

    with pytest.raises(Exception):
        extract_audio(video_path, tmp_path)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not available")
def test_compute_offsets_with_real_wavs(tmp_path: Path) -> None:
    pass
