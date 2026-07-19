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
from src.common.normalize import extract_years, tokenize
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


def get_thread_clients() -> dict[str, Any]:
    if not getattr(_thread_local, "clients", None):
        _thread_local.clients = {}
    return _thread_local.clients


def get_openai_client(api_key: str | None):
    clients = get_thread_clients()
    if "openai" not in clients:
        from openai import OpenAI

        clients["openai"] = OpenAI(api_key=api_key, max_retries=0)
    return clients["openai"]


def get_gemini_client(api_key: str | None):
    clients = get_thread_clients()
    client_key = "gemini_api" if api_key else "gemini_vertex"
    if client_key in clients:
        return clients[client_key]

    from google import genai

    if api_key:
        clients[client_key] = genai.Client(api_key=api_key)
        return clients[client_key]

    project = (
        os.getenv("GOOGLE_CLOUD_PROJECT")
        or os.getenv("VERTEX_PROJECT_ID")
        or os.getenv("GEMINI_PROJECT_ID")
        or os.getenv("PROJECT_ID")
    )
    location = (
        os.getenv("GOOGLE_CLOUD_LOCATION")
        or os.getenv("VERTEX_LOCATION")
        or os.getenv("PROJECT_LOCATION")
        or "us-central1"
    )
    if not project:
        raise RuntimeError(
            "Gemini needs GEMINI_API_KEY/GOOGLE_API_KEY or a Vertex project via "
            "GOOGLE_CLOUD_PROJECT, VERTEX_PROJECT_ID, GEMINI_PROJECT_ID, or PROJECT_ID."
        )
    clients[client_key] = genai.Client(vertexai=True, project=project, location=location)
    return clients[client_key]


def resolve_provider(config: dict, provider: str | None) -> str:
    selected = (provider or config.get("verifier", {}).get("provider", "openai")).lower().strip()
    if selected not in {"openai", "gemini"}:
        raise ValueError(f"Unsupported verifier provider: {selected}")
    return selected


def resolve_model(config: dict, provider: str, model: str | None) -> str:
    if model:
        return model
    verifier = config.get("verifier", {})
    if provider == "gemini":
        return os.getenv(
            verifier.get("gemini_model_env", "GEMINI_MODEL"),
            verifier.get("gemini_default_model", "gemini-2.5-flash"),
        )
    return os.getenv(verifier.get("model_env", "OPENAI_MODEL"), verifier.get("default_model", "gpt-4o-mini"))


def resolve_api_key(provider: str) -> str | None:
    if provider == "gemini":
        return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    return os.getenv("OPENAI_API_KEY")


def model_slug(provider: str, model: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "-", model.strip()).strip("-").lower()
    if provider == "openai" and cleaned.startswith("gpt"):
        return cleaned
    if provider == "gemini" and cleaned.startswith("gemini"):
        return cleaned
    return f"{provider}-{cleaned}"


def resolve_output_path(
    config: dict,
    provider: str,
    model: str,
    output_path: str | None = None,
    output_dir: str | None = None,
) -> str:
    if output_path:
        return output_path
    if output_dir:
        return str(project_path(output_dir) / "facet_verified.json")
    verify_root = config.get("paths", {}).get("verify_output_root")
    if verify_root:
        return str(project_path(verify_root) / model_slug(provider, model) / "facet_verified.json")
    return config["paths"]["facet_verified"]


def strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def salvage_verification_fields(text: str) -> dict | None:
    """Last-resort recovery for malformed single-item verifier JSON
    (unescaped quotes/newlines in reasoning, output truncated at max_tokens)."""
    label_match = re.search(r'"label"\s*:\s*"(real|fake)"', text)
    if not label_match:
        return None
    confidence_match = re.search(r'"confidence"\s*:\s*([0-9.]+)', text)
    evidence_ids = re.findall(r'"(E\d+)"', text)
    facets_match = re.search(r'"wrong_facets"\s*:\s*\[([^\]]*)\]', text)
    wrong_facets = re.findall(r'"([a-z_]+)"', facets_match.group(1)) if facets_match else []
    return {
        "label": label_match.group(1),
        "confidence": float(confidence_match.group(1)) if confidence_match else 0.0,
        "evidence_ids": list(dict.fromkeys(evidence_ids)),
        "wrong_facets": wrong_facets,
        "reasoning": "[salvaged from malformed JSON]",
    }


def parse_json_object(text: str) -> dict:
    cleaned = strip_code_fence(text)
    attempts = [cleaned]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        attempts.append(cleaned[start : end + 1])
    if start >= 0:
        # truncated-output repair: close a dangling string/object
        tail = cleaned[start:]
        attempts.extend([tail + '"}', tail + "}", tail + '"]}', tail + "]}"])
    last_error: Exception | None = None
    for attempt in attempts:
        try:
            parsed = json.loads(attempt, strict=False)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        if isinstance(parsed, dict):
            return parsed
        last_error = ValueError("Verifier response must be a JSON object")
    salvaged = salvage_verification_fields(cleaned)
    if salvaged is not None:
        return salvaged
    raise last_error if last_error else ValueError("Unparseable verifier response")


def select_balanced(rows: list[dict], limit: int | None) -> list[dict]:
    if limit is None:
        return rows
    per_label = max(1, limit // 2)
    real = [row for row in rows if row.get("label") == "real"][:per_label]
    fake = [row for row in rows if row.get("label") == "fake"][: limit - len(real)]
    selected = sorted(real + fake, key=lambda row: int(row.get("row_index", 0) or 0))
    return selected[:limit]


def crop_text_to_claim(text: str, claim: str, max_chars: int) -> str:
    """Pick the max_chars window of `text` with the highest claim-token overlap,
    instead of blindly keeping the head of the chunk."""
    if len(text) <= max_chars:
        return text
    claim_tokens = {token for token in tokenize(claim) if len(token) >= 3}
    if not claim_tokens:
        return text[:max_chars]
    step = max(1, max_chars // 2)
    best_start, best_score = 0, -1
    for start in range(0, len(text) - max_chars + step, step):
        window = text[start : start + max_chars]
        score = len(claim_tokens & {token for token in tokenize(window) if len(token) >= 3})
        if score > best_score:
            best_start, best_score = start, score
    return text[best_start : best_start + max_chars]


def build_evidence_context(
    item: dict,
    config: dict,
    top_k_override: int | None = None,
    max_chars_override: int | None = None,
) -> str:
    verifier = config.get("verifier", {})
    top_k = top_k_override if top_k_override is not None else int(verifier.get("top_k_evidence", 6))
    max_chars = max_chars_override if max_chars_override is not None else int(verifier.get("max_chars_per_evidence", 900))
    show_years = bool(verifier.get("show_years", False))
    chunks = []
    for idx, evidence in enumerate(item.get("top_evidence", [])[:top_k], start=1):
        scores = evidence.get("scores", {})
        facet_hits = evidence.get("facet_hits", [])
        relation_hits = evidence.get("relation_hits", [])
        lines = [
            f"[E{idx}] chunk_id={evidence.get('chunk_id')} book={evidence.get('book')} pages={evidence.get('pages')}",
            f"section={evidence.get('section')}",
            f"scores={json.dumps(scores, ensure_ascii=False)}",
            f"facet_hits={json.dumps(facet_hits[:8], ensure_ascii=False)}",
            f"relation_hits={json.dumps(relation_hits[:6], ensure_ascii=False)}",
        ]
        if show_years:
            evidence_years = sorted(
                set(evidence.get("years", []) or []) | extract_years(str(evidence.get("text", "")))
            )[:12]
            lines.append(f"years={evidence_years}")
        evidence_text = str(evidence.get("text", ""))
        if bool(verifier.get("smart_crop", False)):
            lines.append(crop_text_to_claim(evidence_text, str(item.get("claim", "")), max_chars))
        else:
            lines.append(evidence_text[:max_chars])
        chunks.append("\n".join(lines))
    return "\n\n".join(chunks)


def build_prompt(item: dict, config: dict) -> str:
    evidence_context = build_evidence_context(item, config)
    facets = item.get("facets", {})
    facet_summary = item.get("facet_summary_for_verifier", {})
    temporal_rule = ""
    if bool(config.get("verifier", {}).get("show_years", False)):
        temporal_rule = (
            "\n- Đối chiếu từng năm/mốc thời gian trong claim với các năm trong evidence:"
            " nếu evidence nói về cùng sự kiện nhưng ghi năm khác với claim, đó là dấu hiệu mạnh của `fake`."
        )
    return f"""Bạn là hệ thống kiểm chứng nhận định lịch sử Việt Nam.

Nhiệm vụ: dựa CHỈ trên evidence được cung cấp để quyết định claim là `real` hay `fake`.

Quy tắc:
- Chọn `real` nếu evidence ủng hộ các phần chính của claim.
- Chọn `fake` nếu evidence mâu thuẫn rõ về thời gian, địa điểm, nhân vật, tổ chức, sự kiện, số lượng, nguyên nhân hoặc kết quả.{temporal_rule}
- Nếu evidence không đủ rõ, chọn nhãn hợp lý nhất dựa trên evidence hiện có và nêu lý do ngắn gọn.
- Chỉ thêm `insufficient_evidence` vào wrong_facets khi evidence thật sự thiếu phần quan trọng làm bạn không thể ủng hộ claim.
- Không dùng kiến thức ngoài evidence.

Claim facets:
{json.dumps(facets, ensure_ascii=False, indent=2)}

Facet retrieval summary:
{json.dumps(facet_summary, ensure_ascii=False, indent=2)}

Evidence:
{evidence_context}

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
- Chọn `fake` nếu evidence mâu thuẫn rõ về phần quan trọng của claim.
- Nếu evidence không đủ rõ, chọn nhãn hợp lý nhất dựa trên evidence hiện có và nêu lý do ngắn gọn.
- Chỉ thêm `insufficient_evidence` vào wrong_facets khi evidence thật sự thiếu phần quan trọng làm bạn không thể ủng hộ claim.
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


def call_openai_verify(item: dict, config: dict, api_key: str | None, model: str) -> dict:
    verifier = config.get("verifier", {})
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
                "verifier_provider": "openai",
                "verifier_model": model,
            }
        except Exception as exc:
            last_error = exc
            if attempt < retry_attempts:
                time.sleep(retry_sleep * (attempt + 1))
    raise RuntimeError(str(last_error)) from last_error


def call_openai_verify_batch(items: list[dict], config: dict, api_key: str | None, model: str) -> dict[str, dict]:
    verifier = config.get("verifier", {})
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
                    "verifier_provider": "openai",
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


def build_gemini_config(config: dict, max_output_tokens: int):
    from google.genai import types

    verifier = config.get("verifier", {})
    kwargs = {
        "temperature": float(verifier.get("temperature", 0.0)),
        "max_output_tokens": max_output_tokens,
        "response_mime_type": "application/json",
    }
    thinking_budget = verifier.get("gemini_thinking_budget")
    if thinking_budget is not None:
        try:
            kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=int(thinking_budget))
        except Exception:
            pass
    return types.GenerateContentConfig(**kwargs)


def call_gemini_verify(item: dict, config: dict, api_key: str | None, model: str) -> dict:
    verifier = config.get("verifier", {})
    client = get_gemini_client(api_key)
    retry_attempts = int(verifier.get("retry_attempts", 2))
    retry_sleep = float(verifier.get("retry_sleep_seconds", 2))
    last_error = None
    prompt = "Bạn là hệ thống fact-checking, chỉ trả JSON hợp lệ.\n\n" + build_prompt(item, config)
    for attempt in range(retry_attempts + 1):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=build_gemini_config(config, int(verifier.get("max_tokens", 450))),
            )
            raw = response.text or ""
            parsed = parse_json_object(raw)
            return {
                "label_rag": normalize_label(parsed.get("label")),
                "confidence": safe_float(parsed.get("confidence")),
                "evidence_ids": parsed.get("evidence_ids", []),
                "wrong_facets": normalize_wrong_facets(parsed.get("wrong_facets", [])),
                "reasoning": str(parsed.get("reasoning", "")),
                "raw_response": raw,
                "verifier_provider": "gemini",
                "verifier_model": model,
            }
        except Exception as exc:
            last_error = exc
            if attempt < retry_attempts:
                time.sleep(retry_sleep * (attempt + 1))
    raise RuntimeError(str(last_error)) from last_error


def call_gemini_verify_batch(items: list[dict], config: dict, api_key: str | None, model: str) -> dict[str, dict]:
    verifier = config.get("verifier", {})
    client = get_gemini_client(api_key)
    retry_attempts = int(verifier.get("retry_attempts", 2))
    retry_sleep = float(verifier.get("retry_sleep_seconds", 2))
    max_tokens = max(
        int(verifier.get("max_tokens", 450)),
        int(verifier.get("batch_max_tokens_per_item", 280)) * len(items),
    )
    last_error = None
    prompt = "Bạn là hệ thống fact-checking nhiều item, chỉ trả JSON hợp lệ.\n\n" + build_batch_prompt(items, config)
    for attempt in range(retry_attempts + 1):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=build_gemini_config(config, max_tokens),
            )
            raw = response.text or ""
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
                    "verifier_provider": "gemini",
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


def call_model_verify(item: dict, config: dict, provider: str, api_key: str | None, model: str) -> dict:
    if provider == "gemini":
        return call_gemini_verify(item, config, api_key, model)
    return call_openai_verify(item, config, api_key, model)


def call_model_verify_batch(
    items: list[dict],
    config: dict,
    provider: str,
    api_key: str | None,
    model: str,
) -> dict[str, dict]:
    if provider == "gemini":
        return call_gemini_verify_batch(items, config, api_key, model)
    return call_openai_verify_batch(items, config, api_key, model)


def verify_row(item: dict, config: dict, provider: str, api_key: str | None, model: str) -> dict:
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
        result.update(call_model_verify(item, config, provider, api_key, model))
    except Exception as exc:
        result.update(
            {
                "label_rag": "error",
                "confidence": 0.0,
                "evidence_ids": [],
                "wrong_facets": [],
                "reasoning": "",
                "raw_response": "",
                "verifier_provider": provider,
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


def verify_batch(
    batch: list[tuple[int, dict]],
    config: dict,
    provider: str,
    api_key: str | None,
    model: str,
) -> list[dict]:
    items = [row for _, row in batch]
    if len(batch) == 1 and bool(config.get("verifier", {}).get("route_single_full_prompt", False)):
        return [verify_row(row, config, provider, api_key, model) for _, row in batch]
    try:
        verified_by_id = call_model_verify_batch(items, config, provider, api_key, model)
    except Exception:
        if len(batch) == 1:
            raise
        return [verify_row(row, config, provider, api_key, model) for _, row in batch]
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
    input_path: str | None = None,
    output_path: str | None = None,
    output_dir: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> list[dict]:
    provider_name = resolve_provider(config, provider)
    model_name = resolve_model(config, provider_name, model)
    rows = load_json(input_path or config["paths"]["facet_reranked"])
    if balanced:
        rows = select_balanced(rows, limit)
    elif limit is not None:
        rows = rows[:limit]

    verified_path = resolve_output_path(config, provider_name, model_name, output_path, output_dir)
    completed = {} if no_resume else load_completed(verified_path)
    pending = [(index, row) for index, row in enumerate(rows) if row_key(row, index) not in completed]

    verifier = config.get("verifier", {})
    worker_count = workers if workers is not None else int(verifier.get("workers", 1))
    batch_size = batch_size if batch_size is not None else int(verifier.get("batch_size", 1))
    checkpoint_every = max(1, int(verifier.get("checkpoint_every", 25)))
    worker_count = max(1, worker_count)
    batch_size = max(1, batch_size)
    api_key = resolve_api_key(provider_name)
    verify_environment(provider_name, api_key)
    pending_batches = chunk_pending(pending, batch_size)

    print(f"Loaded {len(rows)} rows for verification")
    print(f"Loaded completed verified rows: {len(completed)}")
    print(f"Verifier: provider={provider_name} model={model_name}")
    print(f"Verifying {len(pending)} pending rows with {worker_count} worker(s)")
    print(f"Batch size: {batch_size}; batches: {len(pending_batches)}")
    print(f"Output: {verified_path}")

    new_completed = 0
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(verify_batch, batch, config, provider_name, api_key, model_name): batch
            for batch in pending_batches
        }
        for future in tqdm(as_completed(futures), total=len(futures), desc="Verifying facet batches"):
            batch = futures[future]
            results = future.result()
            for result in results:
                completed[row_key(result)] = result
            new_completed += len(results)
            if new_completed % checkpoint_every == 0:
                save_json(ordered_rows(rows, completed), verified_path)

    verified = ordered_rows(rows, completed)
    save_json(verified, verified_path)
    return verified


def verify_environment(provider: str, api_key: str | None) -> None:
    if provider == "openai":
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is missing. Put it in .env or export it before running verifier.")
        try:
            import openai  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "Python package 'openai' is not installed in this environment. "
                "Run: pip install -r requirements.txt"
            ) from exc
        return

    try:
        from google import genai  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Python package 'google-genai' is not installed in this environment. "
            "Run: pip install -r requirements.txt"
        ) from exc
    if not api_key and not (
        os.getenv("GOOGLE_CLOUD_PROJECT")
        or os.getenv("VERTEX_PROJECT_ID")
        or os.getenv("GEMINI_PROJECT_ID")
        or os.getenv("PROJECT_ID")
    ):
        raise RuntimeError(
            "Gemini verifier needs GEMINI_API_KEY/GOOGLE_API_KEY, or Vertex env "
            "GOOGLE_CLOUD_PROJECT/VERTEX_PROJECT_ID/GEMINI_PROJECT_ID/PROJECT_ID."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify FacetGraphRAG evidence with OpenAI or Gemini.")
    parser.add_argument("--config", default="configs/facet/facet.yaml")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--balanced", action="store_true", help="Use a balanced real/fake prefix sample.")
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=None, help="Claims per verifier request.")
    parser.add_argument("--provider", choices=["openai", "gemini"], default=None)
    parser.add_argument("--model", default=None, help="Override verifier model name.")
    parser.add_argument("--input-path", default=None, help="Override verifier input JSON.")
    parser.add_argument("--output-path", default=None, help="Override verifier output JSON.")
    parser.add_argument("--output-dir", default=None, help="Directory for facet_verified.json.")
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
        input_path=args.input_path,
        output_path=args.output_path,
        output_dir=args.output_dir,
        provider=args.provider,
        model=args.model,
    )
    provider_name = resolve_provider(config, args.provider)
    model_name = resolve_model(config, provider_name, args.model)
    saved_path = resolve_output_path(config, provider_name, model_name, args.output_path, args.output_dir)
    print(f"Saved {len(rows)} verified rows to {saved_path}")


if __name__ == "__main__":
    main()
