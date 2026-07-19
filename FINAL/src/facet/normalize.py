from __future__ import annotations

import re
import unicodedata

from src.common.normalize import extract_years, normalize_text


NON_WORD_RE = re.compile(r"[\W_]+", flags=re.UNICODE)
NUMBER_RE = re.compile(
    r"(?<!\w)(?:\d+(?:[.,]\d+)?(?:\s*[-–—]\s*\d+(?:[.,]\d+)?)?\s*)"
    r"(?:%|phần trăm|triệu|tỉ|tỷ|nghìn|vạn|ha|km2|km²|năm|người|quân|lần|tháng)?",
    flags=re.IGNORECASE,
)


def normalize_key(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "").lower()
    text = NON_WORD_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_facet_value(text: str) -> str:
    return normalize_text(text).strip(" .,:;!?()[]{}\"'")


def extract_quantities(text: str) -> list[str]:
    values = []
    for match in NUMBER_RE.finditer(text or ""):
        value = normalize_facet_value(match.group(0))
        if not value:
            continue
        if value.isdigit() and int(value) in extract_years(value):
            continue
        if value not in values:
            values.append(value)
    return values


def unique_preserve_order(values: list[str]) -> list[str]:
    seen = set()
    output = []
    for value in values:
        cleaned = normalize_facet_value(value)
        key = normalize_key(cleaned)
        if not cleaned or key in seen:
            continue
        seen.add(key)
        output.append(cleaned)
    return output
