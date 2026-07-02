from __future__ import annotations

import argparse
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from src.common.io import load_json, load_yaml, project_path, save_json
from src.common.normalize import extract_years, normalize_text
from src.facet.graph_index import GraphIndex
from src.facet.normalize import extract_quantities, normalize_facet_value, unique_preserve_order
from src.facet.schema import FACET_TYPES, GRAPH_TYPE_TO_FACET, empty_facets


_thread_local = threading.local()


try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover
    def tqdm(iterable, **_: Any):
        return iterable


def load_env_file() -> None:
    env_path = project_path(".env")
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - keeps deterministic mode dependency-light.
    def load_dotenv() -> bool:
        load_env_file()
        return True


def row_key(item: dict, index: int | None = None) -> str:
    if item.get("ID") is not None:
        return str(item["ID"])
    if index is None:
        raise ValueError("Cannot build row key without ID or index")
    return f"__idx_{index}"


def get_openai_client(api_key: str | None):
    if not getattr(_thread_local, "client", None):
        from openai import OpenAI

        _thread_local.client = OpenAI(api_key=api_key, max_retries=0)
    return _thread_local.client


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
        raise ValueError("Facet extractor response must be a JSON object")
    return parsed


def deterministic_facets(item: dict, graph_index: GraphIndex, config: dict) -> dict[str, list[str]]:
    facets = empty_facets()
    query = build_query(item, config.get("run", {}).get("query_fields", ["claim"]))
    max_alias_matches = int(config.get("matching", {}).get("max_alias_matches_per_text", 10))
    alias_matches = graph_index.match_aliases(query, graph_types=None, max_matches=max_alias_matches * 4)
    for match in alias_matches:
        facet_type = GRAPH_TYPE_TO_FACET.get(match.get("node_type", ""))
        if facet_type and facet_type in facets:
            facets[facet_type].append(match.get("matched_alias") or match.get("node_name", ""))
    for year in sorted(extract_years(query)):
        facets["time"].append(str(year))
    for quantity in extract_quantities(query):
        facets["quantity"].append(quantity)
    max_per_type = int(config.get("extractor", {}).get("max_facets_per_type", 8))
    return {facet_type: unique_preserve_order(values)[:max_per_type] for facet_type, values in facets.items()}


def facet_instruction(max_per_type: int) -> str:
    return f"""Bạn là bộ tách facet cho hệ thống kiểm chứng lịch sử Việt Nam.

Nhiệm vụ: chỉ dựa trên claim, tách các phần cần kiểm chứng. Không kết luận real/fake. Không thêm kiến thức ngoài claim.

Facet types:
- person: nhân vật
- organization: tổ chức, quốc gia, đảng phái, lực lượng
- event: sự kiện lịch sử cụ thể
- place: địa điểm
- time: năm, ngày tháng, giai đoạn
- concept: khái niệm/chủ đề lịch sử
- quantity: số lượng, tỉ lệ, con số
- action: hành động chính
- result: kết quả/tác động/hệ quả

Giới hạn tối đa {max_per_type} giá trị mỗi facet. Giữ cụm từ đúng như trong claim khi có thể."""


def build_prompt(item: dict, deterministic: dict[str, list[str]], config: dict) -> str:
    max_per_type = int(config.get("extractor", {}).get("max_facets_per_type", 8))
    return f"""{facet_instruction(max_per_type)}

Trả về JSON hợp lệ duy nhất theo dạng:
{{
  "facets": {{
    "person": [],
    "organization": [],
    "event": [],
    "place": [],
    "time": [],
    "concept": [],
    "quantity": [],
    "action": [],
    "result": []
  }},
  "claim_focus": ["time|place|actor|event|cause|result|number|sequence|concept"],
  "notes": "ghi chú ngắn"
}}

Giới hạn tối đa {max_per_type} giá trị mỗi facet. Giữ cụm từ đúng như trong claim khi có thể.

Facet rule-based đã tìm được, dùng như gợi ý:
{json.dumps(deterministic, ensure_ascii=False, indent=2)}

ID: {item.get("ID")}
Claim:
{item.get("claim", "")}
"""


def build_batch_prompt(items: list[dict], deterministic_by_id: dict[str, dict[str, list[str]]], config: dict) -> str:
    max_per_type = int(config.get("extractor", {}).get("max_facets_per_type", 8))
    request_items = []
    for item in items:
        key = row_key(item)
        request_items.append(
            {
                "ID": key,
                "claim": item.get("claim", ""),
                "rule_based_facets": deterministic_by_id.get(key, empty_facets()),
            }
        )
    return f"""{facet_instruction(max_per_type)}

Bạn sẽ nhận một mảng claims. Trả về JSON hợp lệ duy nhất theo dạng:
{{
  "items": [
    {{
      "ID": "...",
      "facets": {{
        "person": [],
        "organization": [],
        "event": [],
        "place": [],
        "time": [],
        "concept": [],
        "quantity": [],
        "action": [],
        "result": []
      }},
      "claim_focus": ["time|place|actor|event|cause|result|number|sequence|concept"],
      "notes": "ghi chú ngắn"
    }}
  ]
}}

Yêu cầu:
- Phải trả đúng một item cho mỗi ID đầu vào.
- Không đổi ID.
- Không markdown.
- rule_based_facets chỉ là gợi ý, không bắt buộc giữ nếu claim không thật sự nêu.

Claims:
{json.dumps(request_items, ensure_ascii=False, indent=2)}
"""


def call_openai_facets(item: dict, deterministic: dict[str, list[str]], config: dict, api_key: str | None) -> dict:
    extractor = config.get("extractor", {})
    model = os.getenv(extractor.get("model_env", "OPENAI_MODEL"), extractor.get("default_model", "gpt-4o-mini"))
    client = get_openai_client(api_key)
    timeout = float(extractor.get("request_timeout_seconds", 60))
    retry_attempts = int(extractor.get("retry_attempts", 2))
    retry_sleep = float(extractor.get("retry_sleep_seconds", 2))
    last_error = None
    for attempt in range(retry_attempts + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=float(extractor.get("temperature", 0.0)),
                max_tokens=int(extractor.get("max_tokens", 900)),
                timeout=timeout,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "Bạn tách facet cho claim lịch sử và chỉ trả JSON hợp lệ."},
                    {"role": "user", "content": build_prompt(item, deterministic, config)},
                ],
            )
            raw = response.choices[0].message.content or ""
            parsed = parse_json_object(raw)
            parsed["raw_response"] = raw
            parsed["model"] = model
            return parsed
        except Exception as exc:
            last_error = exc
            if attempt < retry_attempts:
                time.sleep(retry_sleep * (attempt + 1))
    raise RuntimeError(str(last_error)) from last_error


def call_openai_facets_batch(
    items: list[dict],
    deterministic_by_id: dict[str, dict[str, list[str]]],
    config: dict,
    api_key: str | None,
) -> dict[str, dict]:
    extractor = config.get("extractor", {})
    model = os.getenv(extractor.get("model_env", "OPENAI_MODEL"), extractor.get("default_model", "gpt-4o-mini"))
    client = get_openai_client(api_key)
    timeout = float(extractor.get("request_timeout_seconds", 60))
    retry_attempts = int(extractor.get("retry_attempts", 2))
    retry_sleep = float(extractor.get("retry_sleep_seconds", 2))
    batch_max_tokens = max(int(extractor.get("max_tokens", 500)), 220 * len(items))
    last_error = None
    for attempt in range(retry_attempts + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=float(extractor.get("temperature", 0.0)),
                max_tokens=batch_max_tokens,
                timeout=timeout,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "Bạn tách facet cho nhiều claim lịch sử và chỉ trả JSON hợp lệ."},
                    {"role": "user", "content": build_batch_prompt(items, deterministic_by_id, config)},
                ],
            )
            raw = response.choices[0].message.content or ""
            parsed = parse_json_object(raw)
            rows = parsed.get("items", [])
            if not isinstance(rows, list):
                raise ValueError("Batch response must contain an items array")
            by_id = {}
            expected_ids = {row_key(item) for item in items}
            for row in rows:
                if not isinstance(row, dict):
                    continue
                item_id = str(row.get("ID", ""))
                if item_id in expected_ids:
                    row["raw_response"] = raw
                    row["model"] = model
                    by_id[item_id] = row
            missing = expected_ids - set(by_id)
            if missing:
                raise ValueError(f"Batch response missing IDs: {sorted(missing)[:5]}")
            return by_id
        except Exception as exc:
            last_error = exc
            if attempt < retry_attempts:
                time.sleep(retry_sleep * (attempt + 1))
    raise RuntimeError(str(last_error)) from last_error


def coerce_facets(value: Any, fallback: dict[str, list[str]], config: dict) -> dict[str, list[str]]:
    source = value if isinstance(value, dict) else {}
    max_per_type = int(config.get("extractor", {}).get("max_facets_per_type", 8))
    facets = empty_facets()
    for facet_type in FACET_TYPES:
        values = source.get(facet_type, fallback.get(facet_type, []))
        if not isinstance(values, list):
            values = []
        facets[facet_type] = unique_preserve_order([normalize_facet_value(str(item)) for item in values])[:max_per_type]
    return facets


def extract_row(item: dict, index: int, graph_index: GraphIndex, config: dict, use_llm: bool, api_key: str | None) -> dict:
    deterministic = deterministic_facets(item, graph_index, config)
    llm_data = {}
    error = ""
    if use_llm:
        try:
            llm_data = call_openai_facets(item, deterministic, config, api_key)
        except Exception as exc:
            error = str(exc)
            if not bool(config.get("extractor", {}).get("fallback_on_llm_error", False)):
                raise RuntimeError(f"OpenAI facet extraction failed for {item.get('ID')}: {error}") from exc
    facets = coerce_facets(llm_data.get("facets") if llm_data else {}, deterministic, config)
    return {
        "ID": item.get("ID"),
        "row_index": index,
        "key": item.get("key", ""),
        "claim": item.get("claim", ""),
        "label": item.get("label", ""),
        "gold_relevant": item.get("relevant", ""),
        "facets": facets,
        "claim_focus": unique_preserve_order([str(x) for x in llm_data.get("claim_focus", [])]) if llm_data else [],
        "extractor": "openai" if use_llm and not error else "deterministic",
        "llm_error": error,
    }


def extract_batch(
    batch: list[tuple[int, dict]],
    graph_index: GraphIndex,
    config: dict,
    use_llm: bool,
    api_key: str | None,
) -> list[dict]:
    deterministic_by_id = {
        row_key(item): deterministic_facets(item, graph_index, config)
        for _, item in batch
    }
    llm_by_id = {}
    if use_llm:
        try:
            llm_by_id = call_openai_facets_batch([item for _, item in batch], deterministic_by_id, config, api_key)
        except Exception:
            if len(batch) == 1:
                raise
            # Fall back to single-item calls so one malformed batch does not block progress.
            rows = []
            for index, item in batch:
                rows.append(extract_row(item, index, graph_index, config, use_llm, api_key))
            return rows
    rows = []
    for index, item in batch:
        item_id = row_key(item)
        llm_data = llm_by_id.get(item_id, {})
        deterministic = deterministic_by_id[item_id]
        facets = coerce_facets(llm_data.get("facets") if llm_data else {}, deterministic, config)
        rows.append(
            {
                "ID": item.get("ID"),
                "row_index": index,
                "key": item.get("key", ""),
                "claim": item.get("claim", ""),
                "label": item.get("label", ""),
                "gold_relevant": item.get("relevant", ""),
                "facets": facets,
                "claim_focus": unique_preserve_order([str(x) for x in llm_data.get("claim_focus", [])]) if llm_data else [],
                "extractor": "openai_batch" if use_llm else "deterministic",
                "llm_error": "",
            }
        )
    return rows


def chunk_pending(pending: list[tuple[int, dict]], batch_size: int) -> list[list[tuple[int, dict]]]:
    return [pending[index : index + batch_size] for index in range(0, len(pending), batch_size)]


def load_completed(path: str) -> dict[str, dict]:
    output_path = project_path(path)
    if not output_path.exists():
        return {}
    rows = load_json(path)
    return {row_key(row, index): row for index, row in enumerate(rows) if isinstance(row, dict)}


def ordered_rows(claims: list[dict], rows_by_key: dict[str, dict]) -> list[dict]:
    return [rows_by_key[row_key(item, index)] for index, item in enumerate(claims) if row_key(item, index) in rows_by_key]


def run_extract(
    config: dict,
    limit: int | None = None,
    use_llm: bool | None = None,
    no_resume: bool = False,
    workers: int | None = None,
    batch_size: int | None = None,
) -> list[dict]:
    all_claims = load_json(config["paths"]["claims"])
    claims = all_claims
    if limit is None:
        limit = config.get("run", {}).get("limit")
    if limit is not None:
        claims = all_claims[: int(limit)]
    if use_llm is None:
        use_llm = bool(config.get("extractor", {}).get("use_llm", False))
    graph_index = GraphIndex(config)
    output_path = config["paths"]["claim_facets"]
    completed = {} if no_resume else load_completed(output_path)
    pending = [(index, item) for index, item in enumerate(claims) if row_key(item, index) not in completed]
    extractor = config.get("extractor", {})
    worker_count = workers if workers is not None else int(extractor.get("workers", 1))
    batch_size = batch_size if batch_size is not None else int(extractor.get("batch_size", 1))
    checkpoint_every = int(extractor.get("checkpoint_every", 25))
    worker_count = max(1, worker_count)
    batch_size = max(1, batch_size if use_llm else 1)
    checkpoint_every = max(1, checkpoint_every)
    api_key = os.getenv("OPENAI_API_KEY")
    pending_batches = chunk_pending(pending, batch_size)

    print(f"Loaded {len(claims)} claims")
    print(f"Loaded completed facet rows: {len(completed)}")
    print(f"Extracting {len(pending)} pending rows; llm={'yes' if use_llm else 'no'}")
    print(f"Batch size: {batch_size}; batches: {len(pending_batches)}; workers: {worker_count}")
    new_completed = 0
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(extract_batch, batch, graph_index, config, use_llm, api_key): batch
            for batch in pending_batches
        }
        for future in tqdm(as_completed(futures), total=len(futures), desc="Extracting facet batches"):
            batch = futures[future]
            rows = future.result()
            for row in rows:
                completed[row_key(row)] = row
            new_completed += len(rows)
            if new_completed % checkpoint_every == 0:
                save_base = claims if no_resume else all_claims
                save_json(ordered_rows(save_base, completed), output_path)
    save_base = claims if no_resume else all_claims
    rows = ordered_rows(save_base, completed)
    save_json(rows, output_path)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract claim facets for FacetGraphRAG.")
    parser.add_argument("--config", default="configs/facet/facet.yaml")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=None, help="Claims per OpenAI request when --use-llm is enabled.")
    parser.add_argument("--use-llm", action="store_true", help="Use OpenAI facet extraction with OPENAI_API_KEY from .env.")
    parser.add_argument("--no-llm", action="store_true", help="Force deterministic extraction.")
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()

    load_dotenv()
    config = load_yaml(args.config)
    use_llm = True if args.use_llm else False if args.no_llm else None
    rows = run_extract(
        config,
        limit=args.limit,
        use_llm=use_llm,
        no_resume=args.no_resume,
        workers=args.workers,
        batch_size=args.batch_size,
    )
    print(f"Saved {len(rows)} rows to {config['paths']['claim_facets']}")


if __name__ == "__main__":
    main()
