import argparse
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from tqdm import tqdm

from src.common.io import load_json, load_yaml, project_path, save_json


VALID_LABELS = {"real", "fake"}
_thread_local = threading.local()


def get_client(api_key: str | None) -> OpenAI:
    if not getattr(_thread_local, "client", None):
        _thread_local.client = OpenAI(api_key=api_key)
    return _thread_local.client


def row_key(item: dict, index: int | None = None) -> str:
    item_id = item.get("ID")
    if item_id is not None:
        return str(item_id)
    if index is None:
        raise ValueError("Cannot build row key without ID or index")
    return f"__idx_{index}"


def load_completed(path: str | Path) -> dict[str, dict]:
    output_path = project_path(path)
    if not output_path.exists():
        return {}
    rows = load_json(path)
    completed = {}
    for index, row in enumerate(rows):
        label_rag = row.get("label_rag")
        if label_rag and label_rag != "error":
            completed[row_key(row, index)] = row
    return completed


def ordered_results(rows: list[dict], completed: dict[str, dict]) -> list[dict]:
    output = []
    for index, item in enumerate(rows):
        key = row_key(item, index)
        if key in completed:
            output.append(completed[key])
    return output


def build_context(retrieved_context: list[dict], top_k: int, max_chars_per_doc: int) -> str:
    chunks = []
    for idx, doc in enumerate(retrieved_context[:top_k], start=1):
        text = doc.get("text", "")[:max_chars_per_doc]
        chunks.append(
            f"[E{idx}] book={doc.get('book')} page={doc.get('page')} source={doc.get('source')}\n{text}"
        )
    return "\n\n".join(chunks)


def strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def parse_response(text: str) -> dict:
    cleaned = strip_code_fence(text)
    try:
        parsed = json.loads(cleaned)
        label = str(parsed.get("label", "")).lower().strip()
        if label not in VALID_LABELS:
            label = "unknown"
        return {
            "label": label,
            "evidence_ids": parsed.get("evidence_ids", []),
            "reasoning": parsed.get("reasoning", ""),
        }
    except Exception:
        lowered = cleaned.lower()
        if "real" in lowered and "fake" not in lowered:
            label = "real"
        elif "fake" in lowered and "real" not in lowered:
            label = "fake"
        else:
            label = "unknown"
        return {"label": label, "evidence_ids": [], "reasoning": cleaned}


def verify_item(client: OpenAI, model: str, config: dict, item: dict) -> dict:
    verify_config = config["verification"]
    context = build_context(
        item.get("retrieved_context", []),
        verify_config["top_k_context"],
        verify_config["max_chars_per_doc"],
    )
    prompt = f"""Bạn là hệ thống kiểm chứng nhận định lịch sử Việt Nam.

Nhiệm vụ: dựa CHỈ trên các đoạn bằng chứng được truy xuất, hãy xác định nhận định là `real` hay `fake`.

Nếu bằng chứng ủng hộ nhận định, chọn `real`.
Nếu bằng chứng mâu thuẫn nhận định, chọn `fake`.
Nếu bằng chứng không đủ rõ, chọn nhãn hợp lý nhất nhưng nêu lý do ngắn gọn.

Bằng chứng:
{context}

Chủ đề: {item.get('key', '')}
Nhận định: {item.get('claim', '')}

Chỉ trả về JSON hợp lệ theo dạng:
{{
  "label": "real|fake",
  "evidence_ids": ["E1"],
  "reasoning": "lý do ngắn gọn"
}}
"""
    response = client.chat.completions.create(
        model=model,
        temperature=config["openai"].get("temperature", 0.0),
        max_tokens=config["openai"].get("max_tokens", 350),
        messages=[
            {"role": "system", "content": "Bạn là hệ thống kiểm chứng sự thật, trả về JSON hợp lệ."},
            {"role": "user", "content": prompt},
        ],
    )
    raw_response = response.choices[0].message.content or ""
    parsed = parse_response(raw_response)
    return {
        "label_rag": parsed["label"],
        "evidence_ids": parsed["evidence_ids"],
        "reasoning": parsed["reasoning"],
        "raw_response": raw_response,
    }


def verify_row(item: dict, model: str, config: dict, api_key: str | None) -> dict:
    result = {
        "ID": item.get("ID"),
        "key": item.get("key", ""),
        "claim": item.get("claim", ""),
        "label": item.get("label", ""),
        "gold_relevant": item.get("gold_relevant", ""),
        "retrieved_context": item.get("retrieved_context", []),
    }
    try:
        verification = verify_item(get_client(api_key), model, config, item)
        result.update(verification)
    except Exception as exc:
        result.update(
            {
                "label_rag": "error",
                "evidence_ids": [],
                "reasoning": "",
                "raw_response": "",
                "error": str(exc),
            }
        )
    result["correct"] = result.get("label_rag") == result.get("label")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify claims with retrieved top-k evidence.")
    parser.add_argument("--config", default="configs/verify.yaml")
    parser.add_argument("--limit", type=int, default=None, help="Optional smoke-test limit.")
    parser.add_argument("--workers", type=int, default=None, help="Parallel OpenAI requests.")
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=None,
        help="Save progress after this many completed new rows.",
    )
    parser.add_argument("--no-resume", action="store_true", help="Ignore existing verification output.")
    args = parser.parse_args()

    load_dotenv()
    config = load_yaml(args.config)
    model = os.getenv(config["openai"].get("model_env", "OPENAI_MODEL"), config["openai"]["default_model"])
    api_key = os.getenv("OPENAI_API_KEY")

    rows = load_json(config["paths"]["input_retrieved"])
    if args.limit is not None:
        rows = rows[: args.limit]

    verify_config = config.get("verification", {})
    workers = args.workers if args.workers is not None else int(verify_config.get("workers", 1))
    checkpoint_every = (
        args.checkpoint_every
        if args.checkpoint_every is not None
        else int(verify_config.get("checkpoint_every", 25))
    )
    workers = max(1, workers)
    checkpoint_every = max(1, checkpoint_every)

    completed = {} if args.no_resume else load_completed(config["paths"]["output_verified"])
    pending = [(index, item) for index, item in enumerate(rows) if row_key(item, index) not in completed]

    print(f"Loaded {len(completed)} completed rows")
    print(f"Verifying {len(pending)} pending rows with {workers} worker(s)")

    new_completed = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(verify_row, item, model, config, api_key): (index, item)
            for index, item in pending
        }
        for future in tqdm(as_completed(futures), total=len(futures), desc="Verifying"):
            index, item = futures[future]
            completed[row_key(item, index)] = future.result()
            new_completed += 1
            if new_completed % checkpoint_every == 0:
                save_json(ordered_results(rows, completed), config["paths"]["output_verified"])

    save_json(ordered_results(rows, completed), config["paths"]["output_verified"])
    print(f"Saved verification output to {config['paths']['output_verified']}")


if __name__ == "__main__":
    main()
