from __future__ import annotations

import re

WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
TOKEN_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?|[^A-Za-z]+")


def clean_word(value: str) -> str:
    match = WORD_RE.search(value)
    return match.group(0).lower() if match else ""


def tokenize_sentence(sentence: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    for part in TOKEN_RE.findall(sentence):
        tokens.append((part, clean_word(part)))
    return tokens
