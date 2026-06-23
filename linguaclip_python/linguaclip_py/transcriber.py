from __future__ import annotations

from pathlib import Path
from typing import Callable

from .models import SubtitleItem


class TranscriptionUnavailable(RuntimeError):
    pass


ProgressCallback = Callable[[str, int | None], None]


def _report(progress: ProgressCallback | None, message: str, percent: int | None = None) -> None:
    if progress:
        progress(message, percent)


def generate_subtitles_from_video(
    video_path: str,
    model_size: str = "base",
    language: str = "en",
    progress: ProgressCallback | None = None,
) -> list[SubtitleItem]:
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:
        raise TranscriptionUnavailable(
            "未安装 faster-whisper。请先执行：pip install -r requirements.txt"
        ) from exc

    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError(f"视频文件不存在：{path}")

    _report(progress, f"正在加载 Whisper 模型：{model_size}", 3)

    model = WhisperModel(model_size, device="cpu", compute_type="int8")

    _report(progress, "正在识别视频音频，这可能需要几分钟。", 8)

    segments, info = model.transcribe(
        str(path),
        language=language or None,
        vad_filter=True,
        beam_size=5,
    )

    subtitles: list[SubtitleItem] = []
    for index, segment in enumerate(segments):
        text = segment.text.strip()
        if not text:
            continue
        subtitles.append(
            SubtitleItem(
                id=f"asr_{index}_{segment.start:.3f}",
                start=float(segment.start),
                end=float(segment.end),
                text=text,
                translation="",
            )
        )
        if progress:
            duration = max(float(getattr(info, "duration", 0) or 0), 1.0)
            percent = min(95, max(8, int(float(segment.end) / duration * 92)))
            progress(f"已生成 {len(subtitles)} 句字幕，当前到 {segment.end:.1f} 秒", percent)

    _report(progress, f"字幕生成完成，共 {len(subtitles)} 句。", 100)

    return subtitles
