from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import audalign  # type: ignore[import-untyped]


@dataclass
class AlignResult:
    offsets: dict[str, float]
    moment_locals: dict[str, float]
    rankings: dict[str, int]
    recognizers_used: dict[str, str]
    warnings: list[str] = field(default_factory=list)


def extract_audio(video_path: Path, work_dir: Path) -> Path:
    output_path = work_dir / f"{video_path.stem}.wav"
    try:
        audalign.convert_audio_file(str(video_path), str(output_path))
    except Exception:
        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            raise RuntimeError("ffmpeg not found on PATH")
        subprocess.run(
            [
                ffmpeg_path,
                "-i",
                str(video_path),
                "-ac",
                "1",
                "-ar",
                "44100",
                "-y",
                str(output_path),
            ],
            check=True,
            capture_output=True,
        )
    return output_path


def _try_align(wav_paths: list[Path], recognizer: object) -> Optional[dict]:
    try:
        result = audalign.align_files(*[str(p) for p in wav_paths], recognizer=recognizer)
        return result
    except Exception:
        return None


def compute_offsets(wav_paths: list[Path]) -> AlignResult:
    if len(wav_paths) < 2:
        return AlignResult(
            offsets={},
            moment_locals={},
            rankings={},
            recognizers_used={},
            warnings=["Need at least 2 files to align"],
        )

    rec_fp = audalign.FingerprintRecognizer()
    rec_fp.config.set_accuracy(3)

    result = _try_align(wav_paths, rec_fp)

    warnings: list[str] = []
    recognizers_used: dict[str, str] = {}

    if result is None or not result:
        rec_corr = audalign.CorrelationRecognizer()
        result = _try_align(wav_paths, rec_corr)
        if result is None or not result:
            names = [p.name for p in wav_paths]
            return AlignResult(
                offsets={n: 0.0 for n in names},
                moment_locals={n: 0.0 for n in names},
                rankings={},
                recognizers_used={n: "none" for n in names},
                warnings=["Alignment failed for all pairs"],
            )
        for p in wav_paths:
            recognizers_used[p.name] = "correlation"
    else:
        for p in wav_paths:
            recognizers_used[p.name] = "fingerprint"

    raw_shifts: dict[str, float] = {}
    for p in wav_paths:
        name = p.name
        if name in result and isinstance(result[name], (int, float)):
            raw_shifts[name] = float(result[name])
        else:
            raw_shifts[name] = 0.0
            warnings.append(f"No shift found for {name}")

    if not raw_shifts:
        names = [p.name for p in wav_paths]
        return AlignResult(
            offsets={n: 0.0 for n in names},
            moment_locals={n: 0.0 for n in names},
            rankings={},
            recognizers_used=recognizers_used,
            warnings=["No alignment results obtained"],
        )

    min_shift = min(raw_shifts.values())
    offsets = {name: shift - min_shift for name, shift in raw_shifts.items()}

    moment_locals: dict[str, float] = {}
    for name, offset in offsets.items():
        moment_locals[name] = offset

    rankings: dict[str, int] = {}
    if "rankings" in result and isinstance(result["rankings"], dict):
        for name, rank in result["rankings"].items():
            if isinstance(rank, (int, float)):
                rankings[name] = int(rank)

    return AlignResult(
        offsets=offsets,
        moment_locals=moment_locals,
        rankings=rankings,
        recognizers_used=recognizers_used,
        warnings=warnings,
    )
