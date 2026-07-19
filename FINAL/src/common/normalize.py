import re
import unicodedata


WHITESPACE_RE = re.compile(r"\s+")
YEAR_RE = re.compile(r"(?<!\d)(1[0-9]{3}|20[0-9]{2})(?!\d)")


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "")
    return WHITESPACE_RE.sub(" ", text).strip()


def tokenize(text: str) -> list[str]:
    text = normalize_text(text).lower()
    return text.split()


def extract_years(text: str) -> set[int]:
    return {int(match) for match in YEAR_RE.findall(text or "")}
