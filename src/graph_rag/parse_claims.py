"""Parse claims into graph retrieval signals."""

from __future__ import annotations

import argparse
import json
import os
import re
import threading
import time
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from src.common.io import load_json, load_yaml, project_path, save_json, save_text
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

ENTITY_TYPES = ["Person", "Organization", "Event", "Place", "Time", "Concept"]
RELATION_TYPES = ["PARTICIPATED_IN", "OCCURRED_AT", "LOCATED_IN", "RELATED_TO", "CAUSES", "RESULTS_IN", "BEFORE", "AFTER"]


def normalize_key(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "").lower()
    text = re.sub(r"[\W_]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def row_key(item: dict, index: int | None = None) -> str:
    item_id = item.get("ID")
    if item_id is not None:
        return str(item_id)
    if index is None:
        raise ValueError("Cannot build row key without ID or index")
    return f"__idx_{index}"


def build_query(item: dict, query_fields: list[str]) -> str:
    return normalize_text(" ".join(str(item.get(field, "")) for field in query_fields))


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


def as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def build_alias_candidates(alias_map: dict, config: dict) -> list[dict]:
    claim_config = config.get("claim_parsing", {})
    min_alias_chars = int(claim_config.get("min_alias_chars", 4))
    candidates_by_key = {}
    for row in as_list(alias_map.get("aliases")):
        if not isinstance(row, dict):
            continue
        alias = normalize_text(str(row.get("alias", "")))
        normalized_alias = normalize_key(str(row.get("normalized_alias") or alias))
        canonical_id = normalize_text(str(row.get("canonical_id", "")))
        if not alias or not normalized_alias or not canonical_id:
            continue
        if len(normalized_alias.replace(" ", "")) < min_alias_chars:
            continue
        key = (normalized_alias, canonical_id)
        current = candidates_by_key.get(key)
        candidate = {
            "alias": alias,
            "normalized_alias": normalized_alias,
            "entity_id": canonical_id,
            "canonical_name": row.get("canonical_name", ""),
            "canonical_type": row.get("canonical_type", ""),
            "mention_count": int(row.get("mention_count", 0) or 0),
        }
        if current is None or len(alias) > len(current["alias"]):
            candidates_by_key[key] = candidate
    return sorted(
        candidates_by_key.values(),
        key=lambda item: (-len(item["normalized_alias"].split()), -len(item["normalized_alias"]), -item["mention_count"], item["normalized_alias"]),
    )


def deterministic_alias_matches(query: str, alias_candidates: list[dict], config: dict) -> list[dict]:
    claim_config = config.get("claim_parsing", {})
    max_alias_matches = int(claim_config.get("max_alias_matches", 30))
    normalized_query = f" {normalize_key(query)} "
    matches = []
    matched_entities = set()
    occupied_spans: list[tuple[int, int]] = []
    for candidate in alias_candidates:
        needle = f" {candidate['normalized_alias']} "
        start = normalized_query.find(needle)
        if start < 0:
            continue
        end = start + len(needle)
        if any(not (end <= left or start >= right) for left, right in occupied_spans):
            continue
        key = (candidate["entity_id"], candidate["normalized_alias"])
        if key in matched_entities:
            continue
        matched_entities.add(key)
        occupied_spans.append((start, end))
        matches.append(
            {
                "entity_id": candidate["entity_id"],
                "canonical_name": candidate["canonical_name"],
                "canonical_type": candidate["canonical_type"],
                "matched_alias": candidate["alias"],
                "normalized_alias": candidate["normalized_alias"],
                "match_method": "alias_exact_phrase",
                "mention_count": candidate["mention_count"],
            }
        )
        if len(matches) >= max_alias_matches:
            break
    return matches


def build_response_schema() -> dict:
    mention_schema = {
        "type": "OBJECT",
        "properties": {
            "text": {"type": "STRING"},
            "type_hint": {"type": "STRING", "enum": ENTITY_TYPES},
            "role": {"type": "STRING"},
            "importance": {"type": "NUMBER"},
        },
        "required": ["text", "type_hint", "role", "importance"],
    }
    relation_schema = {
        "type": "OBJECT",
        "properties": {
            "source": {"type": "STRING"},
            "relation": {"type": "STRING", "enum": RELATION_TYPES},
            "target": {"type": "STRING"},
            "evidence_text": {"type": "STRING"},
            "confidence": {"type": "NUMBER"},
        },
        "required": ["source", "relation", "target", "evidence_text", "confidence"],
    }
    return {
        "type": "OBJECT",
        "properties": {
            "time_expressions": {"type": "ARRAY", "items": {"type": "STRING"}},
            "entity_mentions": {"type": "ARRAY", "items": mention_schema},
            "event_mentions": {"type": "ARRAY", "items": mention_schema},
            "relation_hints": {"type": "ARRAY", "items": relation_schema},
            "claim_focus": {"type": "ARRAY", "items": {"type": "STRING"}},
            "keywords": {"type": "ARRAY", "items": {"type": "STRING"}},
        },
        "required": ["time_expressions", "entity_mentions", "event_mentions", "relation_hints", "claim_focus", "keywords"],
    }


def build_prompt(item: dict, query: str, years: list[int], alias_matches: list[dict], config: dict) -> str:
    claim_config = config.get("claim_parsing", {})
    max_mentions = int(claim_config.get("max_llm_mentions", 20))
    max_relations = int(claim_config.get("max_llm_relations", 12))
    return f"""Bạn là hệ thống phân tích tín hiệu truy hồi GraphRAG cho kiểm chứng lịch sử Việt Nam.

Nhiệm vụ: phân tích `key + claim` để lấy tín hiệu truy hồi graph. Không phán đoán real/fake. Không truy xuất bằng chứng. Không bịa thêm sự kiện ngoài claim.

Trả về JSON hợp lệ duy nhất, không markdown.

Yêu cầu:
- Giữ entity/event mention đúng theo claim hoặc key.
- role ngắn gọn, ví dụ: actor, location, time, main_event, organization, cause, result, object.
- relation_hints là quan hệ được claim nêu hoặc hàm ý trực tiếp.
- claim_focus nêu loại sai/đúng trọng tâm có thể cần kiểm tra: time, place, actor, event, cause, result, number, sequence, concept.
- keywords là cụm từ quan trọng để truy hồi nếu alias matching không đủ.
- Tối đa {max_mentions} entity_mentions, {max_mentions} event_mentions, và {max_relations} relation_hints.

Years extracted by rules:
{json.dumps(years, ensure_ascii=False)}

Alias matches found by rules:
{json.dumps(alias_matches[:20], ensure_ascii=False, indent=2)}

ID: {item.get('ID')}
Label field, for metadata only, do not use for parsing: {item.get('label', '')}

Key:
{item.get('key', '')}

Claim:
{item.get('claim', '')}

Combined query:
{query}
"""


def get_gemini_client(project: str, location: str):
    client_key = f"{project}:{location}"
    if getattr(_thread_local, "client_key", None) != client_key:
        from google import genai

        _thread_local.client = genai.Client(vertexai=True, project=project, location=location)
        _thread_local.client_key = client_key
    return _thread_local.client


def call_gemini(prompt: str, config: dict, project: str, location: str) -> str:
    from google.genai import types

    claim_config = config.get("claim_parsing", {})
    client = get_gemini_client(project, location)
    thinking_budget = claim_config.get("thinking_budget")
    thinking_config = None
    if thinking_budget is not None:
        thinking_config = types.ThinkingConfig(thinking_budget=int(thinking_budget))
    response = client.models.generate_content(
        model=claim_config.get("model", "gemini-2.5-flash"),
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=float(claim_config.get("temperature", 0.0)),
            max_output_tokens=int(claim_config.get("max_output_tokens", 2048)),
            response_mime_type="application/json",
            response_schema=build_response_schema(),
            thinking_config=thinking_config,
        ),
    )
    text = getattr(response, "text", None)
    if not text:
        raise ValueError("Gemini returned an empty response")
    return text


def coerce_string_list(value: Any) -> list[str]:
    output = []
    for item in as_list(value):
        text = normalize_text(str(item))
        if text and text not in output:
            output.append(text)
    return output


def validate_llm_parse(parsed: dict, config: dict) -> dict:
    claim_config = config.get("claim_parsing", {})
    max_mentions = int(claim_config.get("max_llm_mentions", 20))
    max_relations = int(claim_config.get("max_llm_relations", 12))
    entity_mentions = []
    for item in as_list(parsed.get("entity_mentions"))[:max_mentions]:
        if not isinstance(item, dict):
            continue
        text = normalize_text(str(item.get("text", "")))
        type_hint = normalize_text(str(item.get("type_hint", "")))
        if not text or type_hint not in ENTITY_TYPES:
            continue
        entity_mentions.append({"text": text, "type_hint": type_hint, "role": normalize_text(str(item.get("role", ""))), "importance": confidence(item.get("importance"))})
    event_mentions = []
    for item in as_list(parsed.get("event_mentions"))[:max_mentions]:
        if not isinstance(item, dict):
            continue
        text = normalize_text(str(item.get("text", "")))
        type_hint = normalize_text(str(item.get("type_hint", "Event")))
        if not text or type_hint not in ENTITY_TYPES:
            continue
        event_mentions.append({"text": text, "type_hint": type_hint, "role": normalize_text(str(item.get("role", ""))), "importance": confidence(item.get("importance"))})
    relation_hints = []
    for item in as_list(parsed.get("relation_hints"))[:max_relations]:
        if not isinstance(item, dict):
            continue
        relation = normalize_text(str(item.get("relation", "")))
        source = normalize_text(str(item.get("source", "")))
        target = normalize_text(str(item.get("target", "")))
        if relation not in RELATION_TYPES or not source or not target:
            continue
        relation_hints.append({"source": source, "relation": relation, "target": target, "evidence_text": normalize_text(str(item.get("evidence_text", ""))), "confidence": confidence(item.get("confidence"))})
    return {
        "time_expressions": coerce_string_list(parsed.get("time_expressions")),
        "entity_mentions": entity_mentions,
        "event_mentions": event_mentions,
        "relation_hints": relation_hints,
        "claim_focus": coerce_string_list(parsed.get("claim_focus")),
        "keywords": coerce_string_list(parsed.get("keywords")),
    }


def verify_environment(config: dict) -> tuple[str, str]:
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project:
        raise ValueError("GOOGLE_CLOUD_PROJECT is required for Gemini Vertex claim parsing")
    claim_config = config.get("claim_parsing", {})
    location_env = claim_config.get("location_env", "GOOGLE_CLOUD_LOCATION")
    location = os.getenv(location_env, claim_config.get("default_location", "us-central1"))
    return project, location


def parse_claim_with_llm(item: dict, query: str, years: list[int], alias_matches: list[dict], config: dict, project: str, location: str) -> dict:
    claim_config = config.get("claim_parsing", {})
    retry_attempts = int(claim_config.get("retry_attempts", 2))
    prompt = build_prompt(item, query, years, alias_matches, config)
    last_error = None
    for attempt in range(retry_attempts + 1):
        try:
            raw_response = call_gemini(prompt, config, project, location)
            return validate_llm_parse(parse_json_object(raw_response), config)
        except Exception as exc:
            last_error = exc
            if attempt < retry_attempts:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(str(last_error)) from last_error


def parse_claim_row(item: dict, config: dict, alias_candidates: list[dict], project: str | None, location: str | None, no_llm: bool) -> dict:
    query_fields = config.get("claim_parsing", {}).get("query_fields", ["key", "claim"])
    query = build_query(item, query_fields)
    years = sorted(extract_years(query))
    alias_matches = deterministic_alias_matches(query, alias_candidates, config)
    llm_parse = {"time_expressions": [], "entity_mentions": [], "event_mentions": [], "relation_hints": [], "claim_focus": [], "keywords": []}
    if not no_llm:
        if project is None or location is None:
            raise ValueError("Gemini project/location is required when LLM parsing is enabled")
        llm_parse = parse_claim_with_llm(item, query, years, alias_matches, config, project, location)
    return {
        "ID": item.get("ID"),
        "key": item.get("key", ""),
        "claim": item.get("claim", ""),
        "label": item.get("label", ""),
        "gold_relevant": item.get("relevant", ""),
        "query": query,
        "years": years,
        "alias_matches": alias_matches,
        "llm_parse": llm_parse,
    }


def load_completed(path: str | Path) -> dict[str, dict]:
    output_path = project_path(path)
    if not output_path.exists():
        return {}
    rows = load_json(path)
    return {row_key(row, index): row for index, row in enumerate(rows) if isinstance(row, dict)}


def load_errors(path: str | Path) -> dict[str, dict]:
    output_path = project_path(path)
    if not output_path.exists():
        return {}
    rows = load_json(path)
    return {row_key(row, index): row for index, row in enumerate(rows) if isinstance(row, dict)}


def ordered_rows(claims: list[dict], rows_by_key: dict[str, dict]) -> list[dict]:
    return [rows_by_key[row_key(item, index)] for index, item in enumerate(claims) if row_key(item, index) in rows_by_key]


def build_report(rows: list[dict], errors: list[dict], no_llm: bool) -> str:
    years_count = sum(1 for row in rows if row.get("years"))
    alias_count = sum(1 for row in rows if row.get("alias_matches"))
    llm_entity_count = sum(1 for row in rows if row.get("llm_parse", {}).get("entity_mentions"))
    llm_event_count = sum(1 for row in rows if row.get("llm_parse", {}).get("event_mentions"))
    focus_counts = Counter(focus for row in rows for focus in row.get("llm_parse", {}).get("claim_focus", []))
    type_counts = Counter(match.get("canonical_type") for row in rows for match in row.get("alias_matches", []))
    lines = [
        "# Claim Parser Report",
        "",
        "## Summary",
        "",
        f"- Parsed claims: {len(rows)}",
        f"- Parse errors: {len(errors)}",
        f"- LLM parsing used: {'no' if no_llm else 'yes'}",
        f"- Claims with years: {years_count}",
        f"- Claims with alias matches: {alias_count}",
        f"- Claims with LLM entity mentions: {llm_entity_count}",
        f"- Claims with LLM event mentions: {llm_event_count}",
        "",
        "## Alias Match Types",
        "",
        "| Type | Matches |",
        "|---|---:|",
    ]
    for item, count in type_counts.most_common():
        lines.append(f"| {item} | {count} |")
    lines.extend(["", "## Claim Focus", "", "| Focus | Count |", "|---|---:|"])
    for focus, count in focus_counts.most_common():
        lines.append(f"| {focus} | {count} |")
    return "\n".join(lines) + "\n"


def run_parse(config: dict, args: argparse.Namespace) -> tuple[list[dict], list[dict]]:
    paths = config["paths"]
    claims = load_json(paths["input_claims"])
    if args.limit is not None:
        claims = claims[: args.limit]
    alias_candidates = build_alias_candidates(load_json(paths["entity_aliases"]), config)
    completed = {} if args.no_resume else load_completed(paths["parsed_claims"])
    errors = {} if args.no_resume else load_errors(paths["claim_parse_errors"])
    if args.retry_errors:
        errors = {}
    pending = [(index, item) for index, item in enumerate(claims) if row_key(item, index) not in completed and row_key(item, index) not in errors]

    project = location = None
    if not args.no_llm:
        project, location = verify_environment(config)

    claim_config = config.get("claim_parsing", {})
    workers = args.workers if args.workers is not None else int(claim_config.get("workers", 1))
    checkpoint_every = args.checkpoint_every if args.checkpoint_every is not None else int(claim_config.get("checkpoint_every", 50))
    workers = max(1, workers)
    checkpoint_every = max(1, checkpoint_every)

    print(f"Loaded {len(claims)} selected claims")
    print(f"Alias candidates: {len(alias_candidates)}")
    print(f"Loaded completed parses: {len(completed)}")
    print(f"Loaded previous errors: {len(errors)}")
    print(f"Parsing {len(pending)} pending claims with {workers} worker(s); llm={'no' if args.no_llm else 'yes'}")

    new_completed = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(parse_claim_row, item, config, alias_candidates, project, location, args.no_llm): (index, item)
            for index, item in pending
        }
        for future in tqdm(as_completed(futures), total=len(futures), desc="Parsing claims"):
            index, item = futures[future]
            key = row_key(item, index)
            try:
                completed[key] = future.result()
                errors.pop(key, None)
            except Exception as exc:
                errors[key] = {"ID": item.get("ID"), "key": item.get("key", ""), "claim": item.get("claim", ""), "label": item.get("label", ""), "error": str(exc)}
            new_completed += 1
            if new_completed % checkpoint_every == 0:
                save_json(ordered_rows(claims, completed), paths["parsed_claims"])
                save_json(ordered_rows(claims, errors), paths["claim_parse_errors"])

    parsed_rows = ordered_rows(claims, completed)
    error_rows = ordered_rows(claims, errors)
    save_json(parsed_rows, paths["parsed_claims"])
    save_json(error_rows, paths["claim_parse_errors"])
    if paths.get("claim_parser_report"):
        save_text(build_report(parsed_rows, error_rows, args.no_llm), paths["claim_parser_report"])
    return parsed_rows, error_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse claims into graph retrieval signals.")
    parser.add_argument("--config", default="configs/graph.yaml")
    parser.add_argument("--limit", type=int, default=None, help="Optional smoke-test claim limit.")
    parser.add_argument("--workers", type=int, default=None, help="Parallel Gemini requests.")
    parser.add_argument("--checkpoint-every", type=int, default=None, help="Save progress every N claims.")
    parser.add_argument("--no-resume", action="store_true", help="Ignore existing parsed claim outputs.")
    parser.add_argument("--retry-errors", action="store_true", help="Retry rows already listed in errors.")
    parser.add_argument("--no-llm", action="store_true", help="Run deterministic year and alias parsing only.")
    args = parser.parse_args()

    load_dotenv()
    config = load_yaml(args.config)
    rows, errors = run_parse(config, args)
    print(f"Saved {len(rows)} parsed claims to {config['paths']['parsed_claims']}")
    print(f"Saved {len(errors)} claim parse errors to {config['paths']['claim_parse_errors']}")
    print(f"Saved claim parser report to {config['paths']['claim_parser_report']}")


if __name__ == "__main__":
    main()
