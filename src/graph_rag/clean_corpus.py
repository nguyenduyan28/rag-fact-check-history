import argparse
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from src.common.io import load_yaml, project_path, save_json, save_text
from src.common.normalize import extract_years


PAGE_RE = re.compile(r"\.pdf_(\d+)\.jpg\.txt$")
WHITESPACE_RE = re.compile(r"\s+")
LESSON_RE = re.compile(r"^(?:Bài|BÀI|BAI)\s*(\d{1,2})(?:\s*[:.\-]\s*(.*))?$", re.IGNORECASE)
LESSON_MARKER_RE = re.compile(r"^(?:Bài|BÀI|BAI)$", re.IGNORECASE)
MAJOR_SECTION_RE = re.compile(r"^(I|II|III|IV|V|VI|VII|VIII|IX|X)\s*[.\-]?\s+(.+)$", re.IGNORECASE)
NUMBERED_SECTION_RE = re.compile(r"^(\d{1,2})\s*[.)\-]\s+(.+)$")
EXERCISE_RE = re.compile(r"\b(Câu hỏi|Câu hỏi và bài tập|Bài tập|Hãy nêu|Dựa vào)\b", re.IGNORECASE)
PUBLICATION_NOISE_RE = re.compile(
    r"(Chịu trách nhiệm xuất bản|Biên tập lần đầu|Biên tập tái bản|Biên vẽ|Biên vê|"
    r"Trình bày bìa|Sửa bản in|Chế bản|CHẾ BẢN|Mã số|In xong|Bản quyền thuộc)",
    re.IGNORECASE,
)


def clean_line(line: str, unicode_form: str, normalize_whitespace: bool) -> str:
    line = unicodedata.normalize(unicode_form, line or "")
    if normalize_whitespace:
        line = WHITESPACE_RE.sub(" ", line)
    return line.strip()


def clean_text(text: str, unicode_form: str, normalize_whitespace: bool) -> str:
    text = unicodedata.normalize(unicode_form, text or "")
    if normalize_whitespace:
        text = WHITESPACE_RE.sub(" ", text)
    return text.strip()


def relative_source(path: Path) -> str:
    return str(path.relative_to(project_path(".")))


def parse_page_file(path: Path) -> dict[str, Any] | None:
    match = PAGE_RE.search(path.name)
    if not match:
        return None
    book = path.parent.name
    page = int(match.group(1))
    return {
        "page_id": f"{book}_p{page}",
        "book": book,
        "page": page,
        "source": relative_source(path),
    }


def uppercase_ratio(text: str) -> float:
    letters = [char for char in text if char.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for char in letters if char.isupper()) / len(letters)


def is_uppercase_heading(line: str) -> bool:
    words = line.split()
    if len(words) < 3 or len(line) > 120:
        return False
    if line.endswith((".", ",", ";", ":", "?", "!")):
        return False
    if any(char.isdigit() for char in line) and uppercase_ratio(line) < 0.85:
        return False
    return uppercase_ratio(line) >= 0.75


def detect_heading(line: str) -> dict[str, Any] | None:
    lesson_match = LESSON_RE.match(line)
    if lesson_match:
        lesson_number = int(lesson_match.group(1))
        title = lesson_match.group(2).strip() if lesson_match.group(2) else ""
        return {
            "kind": "lesson",
            "level": 1,
            "number": lesson_number,
            "title": f"Bài {lesson_number}" + (f": {title}" if title else ""),
        }

    if LESSON_MARKER_RE.match(line):
        return {
            "kind": "lesson_marker",
            "level": 1,
            "number": None,
            "title": "Bài",
        }

    major_match = MAJOR_SECTION_RE.match(line)
    if major_match and len(line) <= 140:
        return {
            "kind": "major_section",
            "level": 2,
            "number": major_match.group(1).upper(),
            "title": line,
        }

    numbered_match = NUMBERED_SECTION_RE.match(line)
    if numbered_match and len(line) <= 140:
        number = int(numbered_match.group(1))
        # Avoid treating page numbers or noisy OCR fragments as section headings.
        if 1 <= number <= 20 and not numbered_match.group(2).strip().startswith(("?", ".")):
            return {
                "kind": "numbered_section",
                "level": 3,
                "number": number,
                "title": line,
            }

    if is_uppercase_heading(line):
        return {
            "kind": "uppercase_heading",
            "level": 2,
            "number": None,
            "title": line,
        }

    return None


def is_exercise_line(line: str) -> bool:
    return bool(EXERCISE_RE.search(line))


def is_publication_or_index_page(text: str) -> bool:
    lesson_mentions = len(re.findall(r"\bBài\s+\d+", text, flags=re.IGNORECASE))
    if lesson_mentions >= 5:
        return True
    if PUBLICATION_NOISE_RE.search(text):
        return lesson_mentions == 0
    return False


def sorted_unique(values: list[Any]) -> list[Any]:
    return sorted(dict.fromkeys(values))


def make_page_record(path: Path, config: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    metadata = parse_page_file(path)
    if metadata is None:
        return None, "unparsed_filename"

    cleaning = config["corpus_cleaning"]
    raw_text = path.read_text(encoding="utf-8", errors="ignore")
    lines = [
        clean_line(line, cleaning.get("unicode_form", "NFC"), cleaning.get("normalize_whitespace", True))
        for line in raw_text.splitlines()
    ]
    lines = [line for line in lines if line]
    text = clean_text(" ".join(lines), cleaning.get("unicode_form", "NFC"), cleaning.get("normalize_whitespace", True))
    if len(text) < cleaning.get("min_chars", 80):
        return None, "too_short"
    if is_publication_or_index_page(text):
        return None, "publication_or_index_page"

    record = {
        **metadata,
        "text": text,
        "char_count": len(text),
        "year_mentions": sorted(extract_years(text)),
        "lines": lines,
    }
    return record, None


def add_line(section: dict[str, Any], page: dict[str, Any], line: str) -> None:
    section["lines"].append(line)
    section["pages"].append(page["page"])
    section["source_pages"].append(page["page_id"])
    section["source_files"].append(page["source"])


def finalize_section(section: dict[str, Any] | None, sections: list[dict[str, Any]], min_chars: int) -> None:
    if not section:
        return
    text = clean_text(" ".join(section.pop("lines")), "NFC", True)
    if len(text) < min_chars:
        return
    section["pages"] = sorted_unique(section["pages"])
    section["source_pages"] = sorted_unique(section["source_pages"])
    section["source_files"] = sorted_unique(section["source_files"])
    section["text"] = text
    section["char_count"] = len(text)
    section["year_mentions"] = sorted(extract_years(text))
    sections.append(section)


def make_section(
    book: str,
    chapter: str | None,
    lesson_number: int | None,
    section_title: str | None,
    section_number: int,
    global_number: int,
    heading_kind: str,
    confidence: str,
) -> dict[str, Any]:
    if lesson_number is not None:
        base_id = f"{book}_s{global_number}_bai{lesson_number}_sec{section_number}"
    else:
        base_id = f"{book}_s{global_number}"
    return {
        "base_id": base_id,
        "chunk_type": "section",
        "chunking_method": "section_aware_rule_based",
        "book": book,
        "chapter": chapter,
        "section": section_title,
        "heading_kind": heading_kind,
        "pages": [],
        "source_pages": [],
        "source_files": [],
        "lines": [],
        "section_confidence": confidence,
        "fallback_used": False,
    }


def make_fallback_chunk(page: dict[str, Any]) -> dict[str, Any]:
    return {
        "base_id": page["page_id"],
        "chunk_type": "page_fallback",
        "chunking_method": "page_fallback",
        "book": page["book"],
        "chapter": None,
        "section": None,
        "heading_kind": None,
        "pages": [page["page"]],
        "source_pages": [page["page_id"]],
        "source_files": [page["source"]],
        "text": page["text"],
        "char_count": page["char_count"],
        "year_mentions": page["year_mentions"],
        "section_confidence": "low",
        "fallback_used": True,
    }


def build_raw_sections(pages: list[dict[str, Any]], config: dict[str, Any], report: dict[str, Any]) -> list[dict[str, Any]]:
    chunking = config.get("chunking", {})
    min_chars = chunking.get("min_chars", 120)
    filter_exercises = chunking.get("filter_exercise_blocks", True)
    fallback_to_pages = chunking.get("fallback_to_page_chunks", True)
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    current_chapter: str | None = None
    current_lesson_number: int | None = None
    section_counter_by_book: Counter[str] = Counter()
    section_counter_by_lesson: defaultdict[tuple[str, int], int] = defaultdict(int)

    for book in sorted({page["book"] for page in pages}):
        book_pages = sorted((page for page in pages if page["book"] == book), key=lambda item: item["page"])
        skipping_exercise = False
        current = None
        current_chapter = None
        current_lesson_number = None

        for page in book_pages:
            fallback_lines: list[str] = []
            page_had_heading = False

            for line in page["lines"]:
                heading = detect_heading(line)

                if skipping_exercise:
                    if heading and heading["kind"] in {"lesson", "lesson_marker", "major_section", "uppercase_heading"}:
                        skipping_exercise = False
                    else:
                        continue

                if filter_exercises and is_exercise_line(line):
                    finalize_section(current, sections, min_chars)
                    current = None
                    skipping_exercise = True
                    report["exercise_blocks"] += 1
                    continue

                if heading:
                    page_had_heading = True
                    report["heading_counts"][heading["kind"]] += 1
                    finalize_section(current, sections, min_chars)

                    section_counter_by_book[book] += 1
                    global_section_number = section_counter_by_book[book]

                    if heading["kind"] == "lesson":
                        current_lesson_number = heading["number"]
                        current_chapter = heading["title"]
                        section_counter_by_lesson[(book, current_lesson_number)] = 1
                        section_number = 1
                    elif heading["kind"] == "lesson_marker":
                        current_lesson_number = None
                        current_chapter = "Bài"
                        section_number = global_section_number
                    elif current_lesson_number is not None:
                        section_counter_by_lesson[(book, current_lesson_number)] += 1
                        section_number = section_counter_by_lesson[(book, current_lesson_number)]
                    else:
                        section_number = global_section_number

                    current = make_section(
                        book=book,
                        chapter=current_chapter,
                        lesson_number=current_lesson_number,
                        section_title=heading["title"],
                        section_number=section_number,
                        global_number=global_section_number,
                        heading_kind=heading["kind"],
                        confidence="high" if heading["kind"] in {"lesson", "major_section", "numbered_section"} else "medium",
                    )
                    add_line(current, page, line)
                    continue

                if current is not None:
                    add_line(current, page, line)
                else:
                    fallback_lines.append(line)

            if fallback_to_pages and fallback_lines and not page_had_heading and current is None:
                fallback_page = {**page, "text": clean_text(" ".join(fallback_lines), "NFC", True)}
                fallback_page["char_count"] = len(fallback_page["text"])
                fallback_page["year_mentions"] = sorted(extract_years(fallback_page["text"]))
                if fallback_page["char_count"] >= min_chars:
                    sections.append(make_fallback_chunk(fallback_page))
                    report["fallback_reasons"]["no_section_boundary"] += 1

        finalize_section(current, sections, min_chars)

    return sections


def tail_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    tail = text[-max_chars:]
    first_space = tail.find(" ")
    return tail[first_space + 1 :].strip() if first_space != -1 else tail.strip()


def merge_trace(current: list[Any], extra: list[Any]) -> list[Any]:
    return sorted_unique([*extra, *current])


def add_previous_section_overlap(sections: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    chunking = config.get("chunking", {})
    overlap_count = chunking.get("overlap_prev_sections", 0)
    if overlap_count <= 0:
        return sections

    overlap_chars = chunking.get("split_overlap_chars", 300)
    output: list[dict[str, Any]] = []
    previous_by_book: dict[str, dict[str, Any]] = {}

    for section in sections:
        new_section = dict(section)
        previous = previous_by_book.get(section["book"])
        if previous and not section.get("fallback_used") and not previous.get("fallback_used"):
            prefix = tail_text(previous["text"], overlap_chars)
            if prefix:
                new_section["text"] = clean_text(f"{prefix} {section['text']}", "NFC", True)
                new_section["char_count"] = len(new_section["text"])
                new_section["year_mentions"] = sorted(extract_years(new_section["text"]))
                new_section["pages"] = merge_trace(new_section["pages"], previous["pages"])
                new_section["source_pages"] = merge_trace(new_section["source_pages"], previous["source_pages"])
                new_section["source_files"] = merge_trace(new_section["source_files"], previous["source_files"])
                new_section["overlap_source_chunk"] = previous["base_id"]
        output.append(new_section)
        previous_by_book[section["book"]] = section

    return output


def split_text(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            boundary = max(text.rfind(". ", start, end), text.rfind("? ", start, end), text.rfind("! ", start, end))
            if boundary > start + max_chars // 2:
                end = boundary + 1
        part = text[start:end].strip()
        if part:
            parts.append(part)
        if end >= len(text):
            break
        start = max(end - overlap_chars, start + 1)
    return parts


def materialize_chunks(sections: list[dict[str, Any]], config: dict[str, Any], report: dict[str, Any]) -> list[dict[str, Any]]:
    chunking = config.get("chunking", {})
    max_chars = chunking.get("max_chars", 3500)
    overlap_chars = chunking.get("split_overlap_chars", 300)
    chunks: list[dict[str, Any]] = []

    for section in sections:
        parts = split_text(section["text"], max_chars, overlap_chars)
        if len(parts) > 1:
            report["oversized_splits"] += 1
        for index, part in enumerate(parts, start=1):
            if section.get("fallback_used") and len(parts) == 1:
                chunk_id = section["base_id"]
            else:
                chunk_id = f"{section['base_id']}_{index:03d}"
            chunk = {
                "chunk_id": chunk_id,
                "chunk_type": section["chunk_type"],
                "chunking_method": section["chunking_method"],
                "book": section["book"],
                "chapter": section["chapter"],
                "section": section["section"],
                "heading_kind": section.get("heading_kind"),
                "pages": section["pages"],
                "source_pages": section["source_pages"],
                "source_files": section["source_files"],
                "text": part,
                "char_count": len(part),
                "year_mentions": sorted(extract_years(part)),
                "prev_chunk_id": None,
                "next_chunk_id": None,
                "section_confidence": section["section_confidence"],
                "fallback_used": section["fallback_used"],
            }
            if "overlap_source_chunk" in section:
                chunk["overlap_source_chunk"] = section["overlap_source_chunk"]
            chunks.append(chunk)

    for index, chunk in enumerate(chunks):
        previous_chunk = chunks[index - 1] if index > 0 and chunks[index - 1]["book"] == chunk["book"] else None
        next_chunk = chunks[index + 1] if index + 1 < len(chunks) and chunks[index + 1]["book"] == chunk["book"] else None
        chunk["prev_chunk_id"] = previous_chunk["chunk_id"] if previous_chunk else None
        chunk["next_chunk_id"] = next_chunk["chunk_id"] if next_chunk else None

    return chunks


def build_report_text(pages: list[dict[str, Any]], chunks: list[dict[str, Any]], report: dict[str, Any], config: dict[str, Any]) -> str:
    raw_by_book = Counter(page["book"] for page in pages)
    section_by_book = Counter(chunk["book"] for chunk in chunks if chunk["chunk_type"] == "section")
    fallback_by_book = Counter(chunk["book"] for chunk in chunks if chunk.get("fallback_used"))
    lines = [
        "# Corpus Cleaning And Chunking Report",
        "",
        "## Summary",
        "",
        f"- Total raw files: {report['total_raw_files']}",
        f"- Cleaned pages: {len(pages)}",
        f"- Output chunks: {len(chunks)}",
        f"- Section-aware chunks: {sum(1 for chunk in chunks if chunk['chunk_type'] == 'section')}",
        f"- Page fallback chunks: {sum(1 for chunk in chunks if chunk.get('fallback_used'))}",
        f"- Filtered pages: {sum(report['filter_reasons'].values())}",
        f"- Exercise blocks filtered: {report['exercise_blocks']}",
        f"- Oversized sections split: {report['oversized_splits']}",
        "",
        "## By Book",
        "",
        "| Book | Cleaned Pages | Section Chunks | Fallback Chunks |",
        "|---|---:|---:|---:|",
    ]
    for book in sorted(raw_by_book):
        lines.append(f"| {book} | {raw_by_book[book]} | {section_by_book[book]} | {fallback_by_book[book]} |")

    lines.extend([
        "",
        "## Config",
        "",
        f"- Unicode form: {config['corpus_cleaning'].get('unicode_form', 'NFC')}",
        f"- Normalize whitespace: {config['corpus_cleaning'].get('normalize_whitespace', True)}",
        f"- Page min chars: {config['corpus_cleaning'].get('min_chars', 80)}",
        f"- Chunking method: {config.get('chunking', {}).get('method', 'section_aware_rule_based')}",
        f"- Chunk min chars: {config.get('chunking', {}).get('min_chars', 120)}",
        f"- Chunk max chars: {config.get('chunking', {}).get('max_chars', 3500)}",
        f"- Previous-section overlap: {config.get('chunking', {}).get('overlap_prev_sections', 0)}",
        "",
        "## Heading Detection",
        "",
        "| Heading Type | Count |",
        "|---|---:|",
    ])
    for heading_type, count in sorted(report["heading_counts"].items()):
        lines.append(f"| {heading_type} | {count} |")

    lines.extend([
        "",
        "## Filter Reasons",
        "",
        "| Reason | Count |",
        "|---|---:|",
    ])
    for reason, count in sorted(report["filter_reasons"].items()):
        lines.append(f"| {reason} | {count} |")

    lines.extend([
        "",
        "## Fallback Reasons",
        "",
        "| Reason | Count |",
        "|---|---:|",
    ])
    for reason, count in sorted(report["fallback_reasons"].items()):
        lines.append(f"| {reason} | {count} |")

    lines.extend(["", "## Sample Chunks", ""])
    for book in sorted(raw_by_book):
        sample = next((chunk for chunk in chunks if chunk["book"] == book), None)
        if not sample:
            continue
        preview = sample["text"][:300].replace("\n", " ")
        lines.extend(
            [
                f"### {book}",
                "",
                f"- Chunk ID: `{sample['chunk_id']}`",
                f"- Type: `{sample['chunk_type']}`",
                f"- Pages: {sample['pages']}",
                f"- Years: {sample['year_mentions']}",
                f"- Preview: {preview}",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def clean_corpus(config: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    paths = config["paths"]
    corpus_dir = project_path(paths["corpus_dir"])
    report: dict[str, Any] = {
        "total_raw_files": 0,
        "filter_reasons": Counter(),
        "heading_counts": Counter(),
        "fallback_reasons": Counter(),
        "exercise_blocks": 0,
        "oversized_splits": 0,
    }

    pages: list[dict[str, Any]] = []
    txt_files = sorted(corpus_dir.rglob("*.txt"))
    report["total_raw_files"] = len(txt_files)
    for txt_file in txt_files:
        page, reason = make_page_record(txt_file, config)
        if page is None:
            report["filter_reasons"][reason or "unknown"] += 1
            continue
        pages.append(page)

    pages.sort(key=lambda item: (item["book"], item["page"]))
    raw_sections = build_raw_sections(pages, config, report)
    overlapped_sections = add_previous_section_overlap(raw_sections, config)
    chunks = materialize_chunks(overlapped_sections, config, report)

    # Internal line lists are useful while processing, but should not be stored in the artifact.
    public_pages = [{key: value for key, value in page.items() if key != "lines"} for page in pages]
    report_text = build_report_text(public_pages, chunks, report, config)
    return public_pages, chunks, report_text


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean OCR corpus and build section-aware chunks.")
    parser.add_argument("--config", default="configs/graph.yaml")
    args = parser.parse_args()

    config = load_yaml(args.config)
    pages, chunks, report_text = clean_corpus(config)

    paths = config["paths"]
    save_json(pages, paths["cleaned_pages"])
    save_json(chunks, paths["cleaned_chunks"])
    save_text(report_text, paths["corpus_report"])

    print(f"Saved cleaned pages to {paths['cleaned_pages']}")
    print(f"Saved section-aware chunks to {paths['cleaned_chunks']}")
    print(f"Saved cleaning report to {paths['corpus_report']}")
    print(f"Pages: {len(pages)}")
    print(f"Chunks: {len(chunks)}")


if __name__ == "__main__":
    main()
