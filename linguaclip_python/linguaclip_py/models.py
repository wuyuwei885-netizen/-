from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SubtitleMode = Literal["original", "english", "chinese", "bilingual"]
FontSize = Literal["small", "medium", "large"]
VocabularyStatus = Literal["unknown", "reviewing", "mastered"]


@dataclass(slots=True)
class VideoProject:
    id: str
    name: str
    file_name: str
    file_path: str
    duration: float
    created_at: float
    updated_at: float


@dataclass(slots=True)
class SubtitleItem:
    id: str
    start: float
    end: float
    text: str
    translation: str = ""


@dataclass(slots=True)
class VocabularyItem:
    id: str
    word: str
    sentence: str
    translation: str
    video_id: str
    video_name: str
    subtitle_id: str
    timestamp: float
    note: str
    status: VocabularyStatus
    created_at: float
    review_count: int


@dataclass(slots=True)
class SentencePracticeItem:
    id: str
    sentence: str
    translation: str
    video_id: str
    video_name: str
    subtitle_id: str
    start: float
    end: float
    created_at: float
    practice_count: int
    completeness: int = 0
    fluency: int = 0
    clarity: int = 0


@dataclass(slots=True)
class AppSettings:
    default_subtitle_mode: SubtitleMode = "bilingual"
    font_size: FontSize = "medium"
    subtitle_x: float = 50.0
    subtitle_y: float = 78.0
    subtitle_background: bool = True
    auto_loop_sentence: bool = False
    asr_model_size: str = "base"
    asr_language: str = "en"
    generate_chinese_translation: bool = False
