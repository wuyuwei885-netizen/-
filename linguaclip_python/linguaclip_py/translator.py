from __future__ import annotations

from typing import Callable

from .models import SubtitleItem

ProgressCallback = Callable[[str, int | None], None]


class TranslationUnavailable(RuntimeError):
    pass


def translate_subtitles_to_chinese(
    subtitles: list[SubtitleItem],
    progress: ProgressCallback | None = None,
) -> list[SubtitleItem]:
    try:
        from deep_translator import GoogleTranslator
    except Exception as exc:
        raise TranslationUnavailable(
            "未安装 deep-translator。请先执行：pip install -r requirements.txt"
        ) from exc

    if not subtitles:
        return subtitles

    translator = GoogleTranslator(source="en", target="zh-CN")
    total = len(subtitles)
    translated: list[SubtitleItem] = []

    for index, item in enumerate(subtitles, start=1):
        try:
            chinese = translator.translate(item.text) or ""
        except Exception as exc:
            raise TranslationUnavailable(f"中文字幕生成失败：{exc}") from exc

        translated.append(
            SubtitleItem(
                id=item.id,
                start=item.start,
                end=item.end,
                text=item.text,
                translation=chinese,
            )
        )

        if progress:
            percent = int(index / total * 100)
            progress(f"正在生成中文字幕：{index}/{total}", percent)

    return translated
