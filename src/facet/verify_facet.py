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
from src.facet.extract_claim_facets import load_dotenv


VALID_LABELS = {"real", "fake"}
_thread_local = threading.local()


try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover
    def tqdm(iterable, **_: Any):
        return iterable


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
        raise ValueError("Verifier response must be a JSON object")
    return parsed


def select_balanced(rows: list[dict], limit: int | None) -> list[dict]:
    if limit is None:
        return rows
    per_label = max(1, limit // 2)
    real = [row for row in rows if row.get("label") == "real"][:per_label]
    fake = [row for row in rows if row.get("label") == "fake"][: limit - len(real)]
    selected = sorted(real + fake, key=lambda row: int(row.get("row_index", 0) or 0))
    return selected[:limit]


def build_evidence_context(
    item: dict,
    config: dict,
    top_k_override: int | None = None,
    max_chars_override: int | None = None,
) -> str:
    verifier = config.get("verifier", {})
    top_k = top_k_override if top_k_override is not None else int(verifier.get("top_k_evidence", 6))
    max_chars = max_chars_override if max_chars_override is not None else int(verifier.get("max_chars_per_evidence", 900))
    chunks = []
    for idx, evidence in enumerate(item.get("top_evidence", [])[:top_k], start=1):
        scores = evidence.get("scores", {})
        facet_hits = evidence.get("facet_hits", [])
        relation_hits = evidence.get("relation_hits", [])
        chunks.append(
            "\n".join(
                [
                    f"[E{idx}] chunk_id={evidence.get('chunk_id')} book={evidence.get('book')} pages={evidence.get('pages')}",
                    f"section={evidence.get('section')}",
                    f"scores={json.dumps(scores, ensure_ascii=False)}",
                    f"facet_hits={json.dumps(facet_hits[:8], ensure_ascii=False)}",
                    f"relation_hits={json.dumps(relation_hits[:6], ensure_ascii=False)}",
                    str(evidence.get("text", ""))[:max_chars],
                ]
            )
        )
    return "\n\n".join(chunks)


def build_prompt(item: dict, config: dict) -> str:
    evidence_context = build_evidence_context(item, config)
    facets = item.get("facets", {})
    facet_summary = item.get("facet_summary_for_verifier", {})
    return f"""Bạn là hệ thống kiểm chứng nhận định lịch sử Việt Nam.

Nhiệm vụ: dựa CHỈ trên evidence được cung cấp để quyết định claim là `real` hay `fake`.

Quy tắc:
- Chọn `real` nếu evidence ủng hộ các phần chính của claim.
- Chọn `fake` nếu evidence mâu thuẫn rõ về thời gian, địa điểm, nhân vật, tổ chức, sự kiện, số lượng, nguyên nhân hoặc kết quả.
- Nếu evidence thiếu hoặc không đủ ủng hộ claim, vẫn phải chọn `fake` và thêm `insufficient_evidence` vào wrong_facets.
- Không dùng kiến thức ngoài evidence.

Claim facets:
{json.dumps(facets, ensure_ascii=False, indent=2)}

Facet retrieval summary:
{json.dumps(facet_summary, ensure_ascii=False, indent=2)}

Evidence:
{evidence_context}

Chủ đề/key:
{item.get('key', '')}

Claim:
{item.get('claim', '')}

Trả về JSON hợp lệ duy nhất:
{{
  "label": "real|fake",
  "confidence": 0.0,
  "evidence_ids": ["E1"],
  "wrong_facets": ["time", "place"],
  "reasoning": "lý do ngắn gọn"
}}

wrong_facets chỉ được dùng các giá trị riêng lẻ trong danh sách này:
["time", "place", "person", "organization", "event", "quantity", "action", "result", "concept", "insufficient_evidence"]
"""


def build_batch_prompt(items: list[dict], config: dict) -> str:
    verifier = config.get("verifier", {})
    top_k = int(verifier.get("batch_top_k_evidence", 4))
    max_chars = int(verifier.get("batch_max_chars_per_evidence", 650))
    request_items = []
    for item in items:
        request_items.append(
            {
                "ID": row_key(item),
                "claim": item.get("claim", ""),
                "key": item.get("key", ""),
                "facets": item.get("facets", {}),
                "facet_summary": item.get("facet_summary_for_verifier", {}),
                "evidence": build_evidence_context(
                    item,
                    config,
                    top_k_override=top_k,
                    max_chars_override=max_chars,
                ),
            }
        )
    return f"""Bạn là hệ thống kiểm chứng nhận định lịch sử Việt Nam.

Nhiệm vụ: với MỖI item, dựa CHỈ trên evidence của item đó để quyết định claim là `real` hay `fake`.

Quy tắc:
- Chọn `real` nếu evidence ủng hộ các phần chính của claim.
- Chọn `fake` nếu evidence mâu thuẫn rõ hoặc evidence thiếu/không đủ ủng hộ claim.
- Nếu evidence thiếu, vẫn phải chọn `fake` và thêm `insufficient_evidence` vào wrong_facets.
- Không dùng kiến thức ngoài evidence.
- Không trộn evidence giữa các item.

Trả về JSON hợp lệ duy nhất:
{{
  "items": [
    {{
      "ID": "...",
      "label": "real|fake",
      "confidence": 0.0,
      "evidence_ids": ["E1"],
      "wrong_facets": ["time", "place"],
      "reasoning": "lý do ngắn gọn"
    }}
  ]
}}

wrong_facets chỉ được dùng các giá trị riêng lẻ trong danh sách này:
["time", "place", "person", "organization", "event", "quantity", "action", "result", "concept", "insufficient_evidence"]

Items:
{json.dumps(request_items, ensure_ascii=False, indent=2)}
"""


def call_openai_verify(item: dict, config: dict, api_key: str | None) -> dict:
    verifier = config.get("verifier", {})
    model = os.getenv(verifier.get("model_env", "OPENAI_MODEL"), verifier.get("default_model", "gpt-4o-mini"))
    client = get_openai_client(api_key)
    timeout = float(verifier.get("request_timeout_seconds", 90))
    retry_attempts = int(verifier.get("retry_attempts", 2))
    retry_sleep = float(verifier.get("retry_sleep_seconds", 2))
    last_error = None
    for attempt in range(retry_attempts + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=float(verifier.get("temperature", 0.0)),
                max_tokens=int(verifier.get("max_tokens", 450)),
                timeout=timeout,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "Bạn là hệ thống fact-checking, chỉ trả JSON hợp lệ."},
                    {"role": "user", "content": build_prompt(item, config)},
                ],
            )
            raw = response.choices[0].message.content or ""
            parsed = parse_json_object(raw)
            label = normalize_label(parsed.get("label"))
            wrong_facets = normalize_wrong_facets(parsed.get("wrong_facets", []))
            return {
                "label_rag": label,
                "confidence": safe_float(parsed.get("confidence")),
                "evidence_ids": parsed.get("evidence_ids", []),
                "wrong_facets": wrong_facets,
                "reasoning": str(parsed.get("reasoning", "")),
                "raw_response": raw,
                "verifier_model": model,
            }
        except Exception as exc:
            last_error = exc
            if attempt < retry_attempts:
                time.sleep(retry_sleep * (attempt + 1))
    raise RuntimeError(str(last_error)) from last_error


def call_openai_verify_batch(items: list[dict], config: dict, api_key: str | None) -> dict[str, dict]:
    verifier = config.get("verifier", {})
    model = os.getenv(verifier.get("model_env", "OPENAI_MODEL"), verifier.get("default_model", "gpt-4o-mini"))
    client = get_openai_client(api_key)
    timeout = float(verifier.get("request_timeout_seconds", 90))
    retry_attempts = int(verifier.get("retry_attempts", 2))
    retry_sleep = float(verifier.get("retry_sleep_seconds", 2))
    max_tokens = max(
        int(verifier.get("max_tokens", 450)),
        int(verifier.get("batch_max_tokens_per_item", 280)) * len(items),
    )
    last_error = None
    for attempt in range(retry_attempts + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=float(verifier.get("temperature", 0.0)),
                max_tokens=max_tokens,
                timeout=timeout,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "Bạn là hệ thống fact-checking nhiều item, chỉ trả JSON hợp lệ."},
                    {"role": "user", "content": build_batch_prompt(items, config)},
                ],
            )
            raw = response.choices[0].message.content or ""
            parsed = parse_json_object(raw)
            rows = parsed.get("items", [])
            if not isinstance(rows, list):
                raise ValueError("Batch verifier response must contain an items array")
            expected_ids = {row_key(item) for item in items}
            output = {}
            for row in rows:
                if not isinstance(row, dict):
                    continue
                item_id = str(row.get("ID", ""))
                if item_id not in expected_ids:
                    continue
                output[item_id] = {
                    "label_rag": normalize_label(row.get("label")),
                    "confidence": safe_float(row.get("confidence")),
                    "evidence_ids": row.get("evidence_ids", []),
                    "wrong_facets": normalize_wrong_facets(row.get("wrong_facets", [])),
                    "reasoning": str(row.get("reasoning", "")),
                    "raw_response": raw,
                    "verifier_model": model,
                }
            missing = expected_ids - set(output)
            if missing:
                raise ValueError(f"Batch verifier response missing IDs: {sorted(missing)[:5]}")
            return output
        except Exception as exc:
            last_error = exc
            if attempt < retry_attempts:
                time.sleep(retry_sleep * (attempt + 1))
    raise RuntimeError(str(last_error)) from last_error


def safe_float(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def normalize_label(value: Any) -> str:
    label = str(value or "").lower().strip()
    if label in VALID_LABELS:
        return label
    if label in {"insufficient_evidence", "insufficient evidence", "not_enough_evidence", "not enough evidence"}:
        return "fake"
    if "fake" in label and "real" not in label:
        return "fake"
    if "real" in label and "fake" not in label:
        return "real"
    return "unknown"


def normalize_wrong_facets(value: Any) -> list[str]:
    allowed = {
        "time",
        "place",
        "person",
        "organization",
        "event",
        "quantity",
        "action",
        "result",
        "concept",
        "insufficient_evidence",
    }
    if isinstance(value, str):
        raw_items = re.split(r"[|,;/\s]+", value)
    elif isinstance(value, list):
        raw_items = []
        for item in value:
            raw_items.extend(re.split(r"[|,;/\s]+", str(item)))
    else:
        raw_items = []
    output = []
    for item in raw_items:
        cleaned = item.strip().lower()
        if cleaned in allowed and cleaned not in output:
            output.append(cleaned)
    return output


def verify_row(item: dict, config: dict, api_key: str | None) -> dict:
    result = {
        "ID": item.get("ID"),
        "row_index": item.get("row_index"),
        "key": item.get("key", ""),
        "claim": item.get("claim", ""),
        "label": item.get("label", ""),
        "gold_relevant": item.get("gold_relevant", ""),
        "facets": item.get("facets", {}),
        "facet_match_summary": item.get("facet_match_summary", {}),
        "facet_summary_for_verifier": item.get("facet_summary_for_verifier", {}),
        "top_evidence": item.get("top_evidence", []),
    }
    try:
        result.update(call_openai_verify(item, config, api_key))
    except Exception as exc:
        result.update(
            {
                "label_rag": "error",
                "confidence": 0.0,
                "evidence_ids": [],
                "wrong_facets": [],
                "reasoning": "",
                "raw_response": "",
                "verifier_model": "",
                "error": str(exc),
            }
        )
    result["correct"] = result.get("label_rag") == result.get("label")
    return result


def base_result(item: dict) -> dict:
    return {
        "ID": item.get("ID"),
        "row_index": item.get("row_index"),
        "key": item.get("key", ""),
        "claim": item.get("claim", ""),
        "label": item.get("label", ""),
        "gold_relevant": item.get("gold_relevant", ""),
        "facets": item.get("facets", {}),
        "facet_match_summary": item.get("facet_match_summary", {}),
        "facet_summary_for_verifier": item.get("facet_summary_for_verifier", {}),
        "top_evidence": item.get("top_evidence", []),
    }


def verify_batch(batch: list[tuple[int, dict]], config: dict, api_key: str | None) -> list[dict]:
    items = [row for _, row in batch]
    try:
        verified_by_id = call_openai_verify_batch(items, config, api_key)
    except Exception:
        if len(batch) == 1:
            raise
        return [verify_row(row, config, api_key) for _, row in batch]
    output = []
    for _, item in batch:
        result = base_result(item)
        result.update(verified_by_id[row_key(item)])
        result["correct"] = result.get("label_rag") == result.get("label")
        output.append(result)
    return output


def chunk_pending(pending: list[tuple[int, dict]], batch_size: int) -> list[list[tuple[int, dict]]]:
    return [pending[index : index + batch_size] for index in range(0, len(pending), batch_size)]


def load_completed(path: str) -> dict[str, dict]:
    output_path = project_path(path)
    if not output_path.exists():
        return {}
    rows = load_json(path)
    return {
        row_key(row, index): row
        for index, row in enumerate(rows)
        if isinstance(row, dict) and row.get("label_rag") not in {None, "", "error"}
    }


def ordered_rows(rows: list[dict], completed: dict[str, dict]) -> list[dict]:
    return [completed[row_key(row, index)] for index, row in enumerate(rows) if row_key(row, index) in completed]


def run_verify(
    config: dict,
    limit: int | None = None,
    balanced: bool = False,
    workers: int | None = None,
    batch_size: int | None = None,
    no_resume: bool = False,
) -> list[dict]:
    rows = load_json(config["paths"]["facet_reranked"])
    if balanced:
        rows = select_balanced(rows, limit)
    elif limit is not None:
        rows = rows[:limit]

    output_path = config["paths"]["facet_verified"]
    completed = {} if no_resume else load_completed(output_path)
    pending = [(index, row) for index, row in enumerate(rows) if row_key(row, index) not in completed]

    verifier = config.get("verifier", {})
    worker_count = workers if workers is not None else int(verifier.get("workers", 1))
    batch_size = batch_size if batch_size is not None else int(verifier.get("batch_size", 1))
    checkpoint_every = max(1, int(verifier.get("checkpoint_every", 25)))
    worker_count = max(1, worker_count)
    batch_size = max(1, batch_size)
    api_key = os.getenv("OPENAI_API_KEY")
    verify_environment(api_key)
    pending_batches = chunk_pending(pending, batch_size)

    print(f"Loaded {len(rows)} rows for verification")
    print(f"Loaded completed verified rows: {len(completed)}")
    print(f"Verifying {len(pending)} pending rows with {worker_count} worker(s)")
    print(f"Batch size: {batch_size}; batches: {len(pending_batches)}")

    new_completed = 0
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(verify_batch, batch, config, api_key): batch
            for batch in pending_batches
        }
        for future in tqdm(as_completed(futures), total=len(futures), desc="Verifying facet batches"):
            batch = futures[future]
            results = future.result()
            for result in results:
                completed[row_key(result)] = result
            new_completed += len(results)
            if new_completed % checkpoint_every == 0:
                save_json(ordered_rows(rows, completed), output_path)

    verified = ordered_rows(rows, completed)
    save_json(verified, output_path)
    return verified


def verify_environment(api_key: str | None) -> None:
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing. Put it in .env or export it before running verifier.")
    try:
        import openai  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Python package 'openai' is not installed in this environment. "
            "Run: pip install -r requirements.txt"
        ) from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify FacetGraphRAG evidence with an OpenAI model.")
    parser.add_argument("--config", default="configs/facet/facet.yaml")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--balanced", action="store_true", help="Use a balanced real/fake prefix sample.")
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=None, help="Claims per OpenAI verifier request.")
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()

    load_dotenv()
    config = load_yaml(args.config)
    rows = run_verify(
        config,
        limit=args.limit,
        balanced=args.balanced,
        workers=args.workers,
        batch_size=args.batch_size,
        no_resume=args.no_resume,
    )
    print(f"Saved {len(rows)} verified rows to {config['paths']['facet_verified']}")


if __name__ == "__main__":
    main()
