from __future__ import annotations

import random


def mock_score(recording_seconds: float, target_seconds: float) -> tuple[int, int, int]:
    if target_seconds <= 0:
        completeness = 85
    else:
        ratio = recording_seconds / target_seconds
        completeness = round(100 - abs(1 - ratio) * 35)
    completeness = max(0, min(100, completeness))
    return completeness, random.randint(70, 95), random.randint(70, 95)
