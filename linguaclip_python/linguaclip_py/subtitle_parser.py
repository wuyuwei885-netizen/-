from __future__ import annotations

import re

from .models import SubtitleItem

CHINESE_RE = re.compile(r"[\u3400-\u9fff]")


def _parse_timestamp(value: str) -> float:
    value = value.strip().replace(",", ".")
    parts = value.split(":")
    seconds = float(parts.pop() if parts else "0")
    minutes = int(parts.pop() if parts else "0")
    hours = int(parts.pop() if parts else "0")
    return hours * 3600 + minutes * 60 + seconds


def _split_bilingual(lines: list[str]) -> tuple[str, str]:
    cleaned = [line.strip() for line in lines if line.strip()]
    chinese = [line for line in cleaned if CHINESE_RE.search(line)]
    english = [line for line in cleaned if not CHINESE_RE.search(line)]
    if chinese and english:
        return " ".join(english), " ".join(chinese)
    return " ".join(cleaned), ""


def parse_subtitles(content: str) -> list[SubtitleItem]:
    text = (
        content.replace("\ufeff", "")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )
    text = re.sub(r"^\s*WEBVTT.*?\n", "", text, flags=re.IGNORECASE).strip()
    if not text:
        return []

    items: list[SubtitleItem] = []
    for index, block in enumerate(re.split(r"\n{2,}", text)):
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        time_index = next((i for i, line in enumerate(lines) if "-->" in line), -1)
        if time_index < 0:
            continue

        start_raw, end_part = lines[time_index].split("-->", 1)
        end_raw = end_part.strip().split()[0]
        try:
            start = _parse_timestamp(start_raw)
            end = _parse_timestamp(end_raw)
        except ValueError:
            continue
        if end <= start:
            continue

        body = [re.sub(r"<[^>]+>", "", line) for line in lines[time_index + 1 :]]
        sentence, translation = _split_bilingual(body)
        if not sentence and not translation:
            continue
        items.append(
            SubtitleItem(
                id=f"sub_{index}_{start:.3f}",
                start=start,
                end=end,
                text=sentence or translation,
                translation=translation,
            )
        )
    return items
