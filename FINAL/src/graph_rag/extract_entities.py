"""Extract historical entities and relations from cleaned corpus chunks."""

from __future__ import annotations

import argparse
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from src.common.io import load_json, load_yaml, project_path, save_json
from src.common.normalize import extract_years, normalize_text

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover - dependency is listed, but keep CLI help usable.
    def tqdm(iterable, **_: Any):
        return iterable

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency is listed, but keep CLI help usable.
    def load_dotenv() -> bool:
        env_path = project_path(".env")
        if not env_path.exists():
            return False
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)
        return True


_thread_local = threading.local()

NON_EXTRACTED_NODE_TYPES = {"DocumentChunk"}
NON_EXTRACTED_EDGE_TYPES = {"MENTIONS", "SUPPORTED_BY"}


def row_key(item: dict, index: int | None = None) -> str:
    chunk_id = item.get("chunk_id")
    if chunk_id is not None:
        return str(chunk_id)
    if index is None:
        raise ValueError("Cannot build row key without chunk_id or index")
    return f"__idx_{index}"


def strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def parse_json_object(text: str) -> dict:
    cleaned = strip_code_fence(text)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise
        parsed = json.loads(cleaned[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Gemini response must be a JSON object")
    return parsed


def coerce_years(value: Any, fallback_text: str = "") -> list[int]:
    years: set[int] = set()
    if isinstance(value, list):
        for item in value:
            if isinstance(item, int):
                years.add(item)
            elif isinstance(item, str):
                years.update(extract_years(item))
    elif isinstance(value, int):
        years.add(value)
    elif isinstance(value, str):
        years.update(extract_years(value))
    years.update(extract_years(fallback_text))
    return sorted(year for year in years if 1000 <= year <= 2099)


def coerce_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = 0.0
    return max(0.0, min(1.0, confidence))


def coerce_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    output = []
    for item in value:
        text = normalize_text(str(item))
        if text:
            output.append(text)
    return output


def allowed_types(config: dict) -> tuple[set[str], set[str]]:
    schema = config.get("schema", {})
    entity_types = set(schema.get("node_types", [])) - NON_EXTRACTED_NODE_TYPES
    relation_types = set(schema.get("edge_types", [])) - NON_EXTRACTED_EDGE_TYPES
    if not entity_types:
        raise ValueError("No extractable entity types found in graph schema")
    if not relation_types:
        raise ValueError("No extractable relation types found in graph schema")
    return entity_types, relation_types


def validate_extraction(parsed: dict, chunk: dict, config: dict) -> dict:
    entity_types, relation_types = allowed_types(config)
    warnings = []
    entities = []
    local_ids = set()

    raw_entities = parsed.get("entities", [])
    if not isinstance(raw_entities, list):
        warnings.append("entities was not a list; replaced with empty list")
        raw_entities = []

    for index, entity in enumerate(raw_entities, start=1):
        if not isinstance(entity, dict):
            warnings.append(f"skipped non-object entity at index {index}")
            continue
        entity_type = normalize_text(str(entity.get("type", "")))
        name = normalize_text(str(entity.get("name", "")))
        if entity_type not in entity_types:
            warnings.append(f"skipped entity with invalid type: {entity_type or '<empty>'}")
            continue
        if not name:
            warnings.append("skipped entity with empty name")
            continue

        local_id = normalize_text(str(entity.get("local_id", ""))) or f"e{index}"
        if local_id in local_ids:
            local_id = f"e{index}"
        local_ids.add(local_id)

        evidence_text = normalize_text(str(entity.get("evidence_text", "")))
        description = normalize_text(str(entity.get("description", "")))
        entities.append(
            {
                "local_id": local_id,
                "type": entity_type,
                "name": name,
                "aliases": coerce_string_list(entity.get("aliases", [])),
                "description": description,
                "years": coerce_years(entity.get("years", []), f"{name} {description} {evidence_text}"),
                "evidence_text": evidence_text,
                "confidence": coerce_confidence(entity.get("confidence")),
            }
        )

    raw_relations = parsed.get("relations", [])
    if not isinstance(raw_relations, list):
        warnings.append("relations was not a list; replaced with empty list")
        raw_relations = []

    relations = []
    for index, relation in enumerate(raw_relations, start=1):
        if not isinstance(relation, dict):
            warnings.append(f"skipped non-object relation at index {index}")
            continue
        relation_type = normalize_text(str(relation.get("type", "")))
        source = normalize_text(str(relation.get("source", "")))
        target = normalize_text(str(relation.get("target", "")))
        if relation_type not in relation_types:
            warnings.append(f"skipped relation with invalid type: {relation_type or '<empty>'}")
            continue
        if source not in local_ids or target not in local_ids:
            warnings.append(f"skipped relation with unknown endpoint: {source}->{target}")
            continue
        evidence_text = normalize_text(str(relation.get("evidence_text", "")))
        description = normalize_text(str(relation.get("description", "")))
        relations.append(
            {
                "source": source,
                "target": target,
                "type": relation_type,
                "description": description,
                "evidence_text": evidence_text,
                "confidence": coerce_confidence(relation.get("confidence")),
            }
        )

    result = {
        "chunk_id": chunk.get("chunk_id"),
        "book": chunk.get("book"),
        "chapter": chunk.get("chapter"),
        "section": chunk.get("section"),
        "pages": chunk.get("pages", []),
        "source_pages": chunk.get("source_pages", []),
        "source_files": chunk.get("source_files", []),
        "chunk_year_mentions": chunk.get("year_mentions", []),
        "entities": entities,
        "relations": relations,
    }
    if warnings:
        result["validation_warnings"] = warnings
    return result


def build_prompt(chunk: dict, config: dict) -> str:
    entity_types, relation_types = allowed_types(config)
    extraction_config = config.get("extraction", {})
    max_input_chars = int(extraction_config.get("max_input_chars", 2200))
    max_entities = int(extraction_config.get("max_entities_per_chunk", 12))
    max_relations = int(extraction_config.get("max_relations_per_chunk", 20))
    text = normalize_text(chunk.get("text", ""))[:max_input_chars]
    metadata = {
        "chunk_id": chunk.get("chunk_id"),
        "book": chunk.get("book"),
        "chapter": chunk.get("chapter"),
        "section": chunk.get("section"),
        "pages": chunk.get("pages", []),
        "year_mentions": chunk.get("year_mentions", []),
    }
    return f"""Bạn là hệ thống trích xuất tri thức lịch sử Việt Nam từ sách giáo khoa.

Nhiệm vụ: đọc một đoạn textbook và trả về JSON hợp lệ duy nhất, không markdown, không giải thích ngoài JSON.

Chỉ trích xuất thông tin được hỗ trợ trực tiếp bởi đoạn văn. Không bịa thêm ngày, địa điểm, người tham gia, hoặc quan hệ.

Allowed entity types: {', '.join(sorted(entity_types))}
Allowed relation types: {', '.join(sorted(relation_types))}

Quy tắc:
- Entity phải có local_id duy nhất trong chunk: e1, e2, e3...
- Relation source/target phải dùng local_id của entities trong cùng JSON.
- Dùng RELATED_TO nếu quan hệ có thật nhưng không khớp loại cụ thể hơn.
- Bỏ qua câu hỏi bài tập, số trang, OCR rác, heading không có sự kiện.
- Nếu không có facts hữu ích, trả về entities=[] và relations=[].
- Chỉ giữ tối đa {max_entities} entities quan trọng nhất và tối đa {max_relations} relations quan trọng nhất.
- confidence là số từ 0.0 đến 1.0.
- years chỉ gồm năm dạng integer được hỗ trợ bởi đoạn văn.

JSON schema cần trả về:
{{
  "chunk_id": "{chunk.get('chunk_id')}",
  "entities": [
    {{
      "local_id": "e1",
      "type": "Person|Organization|Event|Place|Time|Concept",
      "name": "tên thực thể",
      "aliases": [],
      "description": "mô tả ngắn dựa trên đoạn văn",
      "years": [1945],
      "evidence_text": "cụm từ/câu ngắn trong đoạn văn hỗ trợ entity",
      "confidence": 0.95
    }}
  ],
  "relations": [
    {{
      "source": "e1",
      "target": "e2",
      "type": "PARTICIPATED_IN|OCCURRED_AT|LOCATED_IN|RELATED_TO|CAUSES|RESULTS_IN|BEFORE|AFTER",
      "description": "mô tả quan hệ ngắn dựa trên đoạn văn",
      "evidence_text": "cụm từ/câu ngắn trong đoạn văn hỗ trợ relation",
      "confidence": 0.95
    }}
  ]
}}

Metadata:
{json.dumps(metadata, ensure_ascii=False)}

Text:
{text}
"""


def build_response_schema(config: dict) -> dict:
    entity_types, relation_types = allowed_types(config)
    entity_schema = {
        "type": "OBJECT",
        "properties": {
            "local_id": {"type": "STRING"},
            "type": {"type": "STRING", "enum": sorted(entity_types)},
            "name": {"type": "STRING"},
            "aliases": {"type": "ARRAY", "items": {"type": "STRING"}},
            "description": {"type": "STRING"},
            "years": {"type": "ARRAY", "items": {"type": "INTEGER"}},
            "evidence_text": {"type": "STRING"},
            "confidence": {"type": "NUMBER"},
        },
        "required": [
            "local_id",
            "type",
            "name",
            "aliases",
            "description",
            "years",
            "evidence_text",
            "confidence",
        ],
    }
    relation_schema = {
        "type": "OBJECT",
        "properties": {
            "source": {"type": "STRING"},
            "target": {"type": "STRING"},
            "type": {"type": "STRING", "enum": sorted(relation_types)},
            "description": {"type": "STRING"},
            "evidence_text": {"type": "STRING"},
            "confidence": {"type": "NUMBER"},
        },
        "required": ["source", "target", "type", "description", "evidence_text", "confidence"],
    }
    return {
        "type": "OBJECT",
        "properties": {
            "chunk_id": {"type": "STRING"},
            "entities": {"type": "ARRAY", "items": entity_schema},
            "relations": {"type": "ARRAY", "items": relation_schema},
        },
        "required": ["chunk_id", "entities", "relations"],
    }


def get_gemini_client(project: str, location: str):
    client_key = f"{project}:{location}"
    if getattr(_thread_local, "client_key", None) != client_key:
        from google import genai

        _thread_local.client = genai.Client(vertexai=True, project=project, location=location)
        _thread_local.client_key = client_key
    return _thread_local.client


def call_gemini(prompt: str, config: dict, project: str, location: str) -> str:
    from google.genai import types

    extraction_config = config.get("extraction", {})
    client = get_gemini_client(project, location)
    thinking_budget = extraction_config.get("thinking_budget")
    thinking_config = None
    if thinking_budget is not None:
        thinking_config = types.ThinkingConfig(thinking_budget=int(thinking_budget))
    response = client.models.generate_content(
        model=extraction_config.get("model", "gemini-2.5-flash"),
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=float(extraction_config.get("temperature", 0.0)),
            max_output_tokens=int(extraction_config.get("max_output_tokens", 4096)),
            response_mime_type="application/json",
            response_schema=build_response_schema(config),
            thinking_config=thinking_config,
        ),
    )
    text = getattr(response, "text", None)
    if not text:
        raise ValueError("Gemini returned an empty response")
    return text


def extract_chunk(chunk: dict, config: dict, project: str, location: str) -> dict:
    extraction_config = config.get("extraction", {})
    retry_attempts = int(extraction_config.get("retry_attempts", 2))
    prompt = build_prompt(chunk, config)
    last_error = None
    for attempt in range(retry_attempts + 1):
        try:
            raw_response = call_gemini(prompt, config, project, location)
            parsed = parse_json_object(raw_response)
            result = validate_extraction(parsed, chunk, config)
            if extraction_config.get("save_raw_response", False):
                result["raw_response"] = raw_response
            return result
        except Exception as exc:
            last_error = exc
            if attempt < retry_attempts:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(str(last_error)) from last_error


def load_completed(path: str | Path) -> dict[str, dict]:
    output_path = project_path(path)
    if not output_path.exists():
        return {}
    rows = load_json(path)
    completed = {}
    for index, row in enumerate(rows):
        completed[row_key(row, index)] = row
    return completed


def load_errors(path: str | Path) -> dict[str, dict]:
    output_path = project_path(path)
    if not output_path.exists():
        return {}
    rows = load_json(path)
    errors = {}
    for index, row in enumerate(rows):
        errors[row_key(row, index)] = row
    return errors


def ordered_rows(chunks: list[dict], rows_by_key: dict[str, dict]) -> list[dict]:
    output = []
    for index, chunk in enumerate(chunks):
        key = row_key(chunk, index)
        if key in rows_by_key:
            output.append(rows_by_key[key])
    return output


def filter_chunks(chunks: list[dict], args: argparse.Namespace) -> list[dict]:
    output = chunks
    if args.book:
        allowed_books = set(args.book)
        output = [chunk for chunk in output if chunk.get("book") in allowed_books]
    if args.confidence:
        allowed_confidence = set(args.confidence)
        output = [chunk for chunk in output if chunk.get("section_confidence") in allowed_confidence]
    if args.require_years:
        output = [chunk for chunk in output if chunk.get("year_mentions")]
    if args.limit is not None:
        output = output[: args.limit]
    return output


def verify_environment(config: dict) -> tuple[str, str]:
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project:
        raise ValueError("GOOGLE_CLOUD_PROJECT is required for Gemini Vertex extraction")

    extraction_config = config.get("extraction", {})
    location_env = extraction_config.get("location_env", "GOOGLE_CLOUD_LOCATION")
    location = os.getenv(location_env, extraction_config.get("default_location", "us-central1"))
    return project, location


def run_extraction(config: dict, args: argparse.Namespace) -> tuple[list[dict], list[dict]]:
    project, location = verify_environment(config)
    paths = config["paths"]
    chunks = filter_chunks(load_json(paths["cleaned_chunks"]), args)
    if not chunks:
        raise ValueError("No chunks selected for extraction")

    completed = {} if args.no_resume else load_completed(paths["extracted_chunks"])
    errors = {} if args.no_resume else load_errors(paths["extraction_errors"])
    if args.retry_errors:
        errors = {}

    pending = []
    for index, chunk in enumerate(chunks):
        key = row_key(chunk, index)
        if key not in completed and key not in errors:
            pending.append((index, chunk))

    extraction_config = config.get("extraction", {})
    workers = args.workers if args.workers is not None else int(extraction_config.get("workers", 1))
    checkpoint_every = (
        args.checkpoint_every
        if args.checkpoint_every is not None
        else int(extraction_config.get("checkpoint_every", 25))
    )
    workers = max(1, workers)
    checkpoint_every = max(1, checkpoint_every)

    print(f"Loaded {len(chunks)} selected chunks")
    print(f"Loaded {len(completed)} completed extractions")
    print(f"Loaded {len(errors)} previous extraction errors")
    print(f"Extracting {len(pending)} pending chunks with {workers} worker(s)")
    print(f"Gemini Vertex project=<set> location={location} model={extraction_config.get('model')}")

    new_completed = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(extract_chunk, chunk, config, project, location): (index, chunk)
            for index, chunk in pending
        }
        for future in tqdm(as_completed(futures), total=len(futures), desc="Extracting"):
            index, chunk = futures[future]
            key = row_key(chunk, index)
            try:
                completed[key] = future.result()
                errors.pop(key, None)
            except Exception as exc:
                errors[key] = {
                    "chunk_id": chunk.get("chunk_id"),
                    "book": chunk.get("book"),
                    "chapter": chunk.get("chapter"),
                    "section": chunk.get("section"),
                    "pages": chunk.get("pages", []),
                    "error": str(exc),
                }
            new_completed += 1
            if new_completed % checkpoint_every == 0:
                save_json(ordered_rows(chunks, completed), paths["extracted_chunks"])
                save_json(ordered_rows(chunks, errors), paths["extraction_errors"])

    extracted_rows = ordered_rows(chunks, completed)
    error_rows = ordered_rows(chunks, errors)
    save_json(extracted_rows, paths["extracted_chunks"])
    save_json(error_rows, paths["extraction_errors"])
    return extracted_rows, error_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract graph entities and relations with Gemini.")
    parser.add_argument("--config", default="configs/graph.yaml")
    parser.add_argument("--limit", type=int, default=None, help="Optional smoke-test chunk limit.")
    parser.add_argument("--workers", type=int, default=None, help="Parallel Gemini requests.")
    parser.add_argument("--checkpoint-every", type=int, default=None, help="Save progress every N chunks.")
    parser.add_argument("--no-resume", action="store_true", help="Ignore existing extraction outputs.")
    parser.add_argument("--retry-errors", action="store_true", help="Retry chunks already listed in errors.")
    parser.add_argument("--book", action="append", help="Optional book filter, e.g. --book lichsu_12.")
    parser.add_argument(
        "--confidence",
        action="append",
        help="Optional section confidence filter, e.g. --confidence high.",
    )
    parser.add_argument("--require-years", action="store_true", help="Only extract chunks with year mentions.")
    args = parser.parse_args()

    load_dotenv()
    config = load_yaml(args.config)
    extracted_rows, error_rows = run_extraction(config, args)
    print(f"Saved {len(extracted_rows)} extracted chunks to {config['paths']['extracted_chunks']}")
    print(f"Saved {len(error_rows)} extraction errors to {config['paths']['extraction_errors']}")


if __name__ == "__main__":
    main()
