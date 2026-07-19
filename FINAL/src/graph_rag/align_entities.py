"""Align duplicate historical entities across extracted chunks."""

from __future__ import annotations

import argparse
import json
import os
import re
import threading
import time
import unicodedata
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from src.common.io import load_json, load_yaml, project_path, save_json, save_text
from src.common.normalize import normalize_text

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

STOP_TOKENS = {
    "của",
    "cho",
    "các",
    "những",
    "một",
    "nước",
    "quốc",
    "gia",
    "dân",
    "nhân",
    "thế",
    "giới",
    "chiến",
    "tranh",
    "phong",
    "trào",
    "cách",
    "mạng",
    "thời",
    "kỳ",
    "kì",
    "năm",
    "lần",
}

TYPE_PRIORITY = {
    "Person": 60,
    "Organization": 55,
    "Event": 50,
    "Place": 45,
    "Time": 35,
    "Concept": 20,
}

COMPATIBLE_CROSS_TYPES = {
    frozenset({"Place", "Organization"}),
}


def normalize_key(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "").lower()
    text = re.sub(r"[\W_]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def fold_key(text: str) -> str:
    text = normalize_key(text).replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    text = re.sub(r"\by\b", "i", text)
    text = text.replace("y", "i")
    return re.sub(r"\s+", " ", text).strip()


def tokens(text: str) -> set[str]:
    return {token for token in normalize_key(text).split() if len(token) >= 3 and token not in STOP_TOKENS}


def stable_entity_id(index: int) -> str:
    return f"u{index:06d}"


def stable_aligned_id(index: int) -> str:
    return f"ent_{index:06d}"


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


def confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def unique_sorted(values: list[Any]) -> list[Any]:
    output = []
    seen = set()
    for value in values:
        key = json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def coerce_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def collect_raw_entities(rows: list[dict]) -> list[dict]:
    raw_entities = []
    seen_ids: Counter[str] = Counter()
    mention_index = 0
    for row in rows:
        chunk_id = normalize_text(str(row.get("chunk_id", "")))
        for entity in coerce_list(row.get("entities")):
            if not isinstance(entity, dict):
                continue
            local_id = normalize_text(str(entity.get("local_id", ""))) or f"e{mention_index}"
            base_id = f"{chunk_id}:{local_id}" if chunk_id else f"mention:{mention_index}"
            seen_ids[base_id] += 1
            mention_id = base_id if seen_ids[base_id] == 1 else f"{base_id}:{seen_ids[base_id]}"
            name = normalize_text(str(entity.get("name", "")))
            entity_type = normalize_text(str(entity.get("type", "")))
            if not name or not entity_type:
                continue
            raw_entities.append(
                {
                    "mention_id": mention_id,
                    "chunk_id": chunk_id,
                    "book": row.get("book"),
                    "chapter": row.get("chapter"),
                    "section": row.get("section"),
                    "pages": row.get("pages", []),
                    "source_pages": row.get("source_pages", []),
                    "source_files": row.get("source_files", []),
                    "local_id": local_id,
                    "type": entity_type,
                    "name": name,
                    "normalized_name": normalize_key(name),
                    "folded_name": fold_key(name),
                    "aliases": [normalize_text(str(item)) for item in coerce_list(entity.get("aliases")) if normalize_text(str(item))],
                    "description": normalize_text(str(entity.get("description", ""))),
                    "years": sorted({int(year) for year in coerce_list(entity.get("years")) if isinstance(year, int)}),
                    "evidence_text": normalize_text(str(entity.get("evidence_text", ""))),
                    "confidence": confidence(entity.get("confidence")),
                    "mention_index": mention_index,
                }
            )
            mention_index += 1
    return raw_entities


def best_surface_name(names: list[str]) -> str:
    counts = Counter(names)
    return sorted(counts, key=lambda item: (-counts[item], len(item), item.lower()))[0]


def sample_contexts(mentions: list[dict], max_contexts: int) -> list[dict]:
    sorted_mentions = sorted(
        mentions,
        key=lambda item: (
            -confidence(item.get("confidence")),
            item.get("chunk_id", ""),
            item.get("mention_id", ""),
        ),
    )
    contexts = []
    for mention in sorted_mentions:
        context = {
            "chunk_id": mention.get("chunk_id"),
            "book": mention.get("book"),
            "section": mention.get("section"),
            "pages": mention.get("pages", []),
            "description": mention.get("description", ""),
            "evidence_text": mention.get("evidence_text", ""),
            "years": mention.get("years", []),
        }
        if context not in contexts:
            contexts.append(context)
        if len(contexts) >= max_contexts:
            break
    return contexts


def build_representatives(raw_entities: list[dict], config: dict) -> list[dict]:
    alignment_config = config.get("entity_alignment", {})
    max_contexts = int(alignment_config.get("max_contexts_per_entity", 4))
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for entity in raw_entities:
        grouped[(entity["type"], entity["normalized_name"])].append(entity)

    representatives = []
    for index, ((entity_type, normalized_name), mentions) in enumerate(sorted(grouped.items()), start=1):
        aliases = []
        for mention in mentions:
            aliases.append(mention["name"])
            aliases.extend(mention.get("aliases", []))
        years = sorted({year for mention in mentions for year in mention.get("years", [])})
        representatives.append(
            {
                "entity_id": stable_entity_id(index),
                "type": entity_type,
                "name": best_surface_name([mention["name"] for mention in mentions]),
                "normalized_name": normalized_name,
                "folded_name": fold_key(normalized_name),
                "aliases": sorted(set(alias for alias in aliases if alias), key=lambda item: (normalize_key(item), item)),
                "years": years,
                "source_chunks": sorted({mention.get("chunk_id") for mention in mentions if mention.get("chunk_id")}),
                "mention_ids": [mention["mention_id"] for mention in mentions],
                "mention_count": len(mentions),
                "contexts": sample_contexts(mentions, max_contexts),
                "description_samples": unique_sorted([mention.get("description", "") for mention in mentions if mention.get("description")])[:max_contexts],
                "evidence_samples": unique_sorted([mention.get("evidence_text", "") for mention in mentions if mention.get("evidence_text")])[:max_contexts],
                "confidence": round(sum(mention.get("confidence", 0.0) for mention in mentions) / max(1, len(mentions)), 4),
            }
        )
    return representatives


def type_compatible(left_type: str, right_type: str) -> bool:
    return left_type == right_type or frozenset({left_type, right_type}) in COMPATIBLE_CROSS_TYPES


def name_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def should_pair(left: dict, right: dict) -> bool:
    if not type_compatible(left["type"], right["type"]):
        return False
    left_name = left["normalized_name"]
    right_name = right["normalized_name"]
    left_fold = left["folded_name"]
    right_fold = right["folded_name"]
    if left_name == right_name or left_fold == right_fold:
        return True
    left_tokens = tokens(left_name)
    right_tokens = tokens(right_name)
    if left_tokens and right_tokens:
        overlap = len(left_tokens & right_tokens)
        smaller = min(len(left_tokens), len(right_tokens))
        if smaller and overlap / smaller >= 0.75:
            return True
    if name_similarity(left_fold, right_fold) >= 0.78:
        return True
    joined_left = normalize_key(" ".join(left.get("description_samples", []) + left.get("evidence_samples", [])))
    joined_right = normalize_key(" ".join(right.get("description_samples", []) + right.get("evidence_samples", [])))
    if left_name and left_name in joined_right:
        return True
    if right_name and right_name in joined_left:
        return True
    return False


def connected_components(nodes: set[str], edges: list[tuple[str, str]]) -> list[set[str]]:
    parent = {node: node for node in nodes}

    def find(node: str) -> str:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left, right in edges:
        union(left, right)

    components: dict[str, set[str]] = defaultdict(set)
    for node in nodes:
        components[find(node)].add(node)
    return list(components.values())


def chunk_group(entity_ids: list[str], max_group_entities: int, prefix: str) -> list[dict]:
    groups = []
    for index in range(0, len(entity_ids), max_group_entities):
        members = entity_ids[index : index + max_group_entities]
        if len(members) >= 2:
            groups.append({"group_id": f"{prefix}_{index // max_group_entities + 1:04d}", "entity_ids": members})
    return groups


def add_group(group_sets: dict[str, set[str]], prefix: str, members: set[str]) -> None:
    if len(members) < 2:
        return
    key = ",".join(sorted(members))
    group_sets[f"{prefix}_{key}"] = members


def country_state_candidate(rep: dict) -> bool:
    if rep["type"] not in {"Place", "Organization"}:
        return False
    name = rep.get("normalized_name", "")
    if len(name) > 35:
        return False
    text = normalize_key(" ".join([name] + rep.get("description_samples", []) + rep.get("evidence_samples", [])))
    cues = [
        "quốc gia",
        "tên nước",
        "quốc hiệu",
        "nước ",
        "chính phủ",
        "thực dân",
        "đế quốc",
        "liên bang",
        "dân chủ cộng hòa",
    ]
    return any(cue in text for cue in cues)


def build_candidate_groups(representatives: list[dict], config: dict) -> list[dict]:
    alignment_config = config.get("entity_alignment", {})
    max_group_entities = int(alignment_config.get("max_group_entities", 18))
    raw_max_candidate_groups = alignment_config.get("max_candidate_groups", 150)
    max_candidate_groups = int(raw_max_candidate_groups) if raw_max_candidate_groups is not None else None
    enable_similarity_blocks = bool(alignment_config.get("enable_similarity_blocks", True))
    enable_country_state_windows = bool(alignment_config.get("enable_country_state_windows", False))
    similarity_threshold = float(alignment_config.get("similarity_threshold", 0.9))
    reps_by_id = {rep["entity_id"]: rep for rep in representatives}
    group_sets: dict[str, set[str]] = {}

    folded_blocks: dict[str, list[dict]] = defaultdict(list)
    for rep in representatives:
        folded_blocks[rep["folded_name"]].append(rep)

    for block_key, block_reps in folded_blocks.items():
        if not block_key or len(block_reps) < 2:
            continue
        nodes = {rep["entity_id"] for rep in block_reps}
        edges = []
        for left_index, left in enumerate(block_reps):
            for right in block_reps[left_index + 1 :]:
                if type_compatible(left["type"], right["type"]):
                    edges.append((left["entity_id"], right["entity_id"]))
        for component in connected_components(nodes, edges):
            add_group(group_sets, f"fold_{block_key}", component)

    seed_groups = alignment_config.get("seed_alias_groups", [])
    for seed_index, seed_names in enumerate(seed_groups, start=1):
        if not isinstance(seed_names, list):
            continue
        seed_keys = {fold_key(str(name)) for name in seed_names if normalize_text(str(name))}
        members = {rep["entity_id"] for rep in representatives if rep["folded_name"] in seed_keys}
        add_group(group_sets, f"seed_{seed_index:03d}", members)

    if enable_similarity_blocks:
        token_blocks: dict[str, list[dict]] = defaultdict(list)
        for rep in representatives:
            useful_tokens = sorted(tokens(rep["normalized_name"]), key=lambda token: (-len(token), token))[:2]
            for token in useful_tokens:
                token_blocks[token].append(rep)
        for block_key, block_reps in token_blocks.items():
            if len(block_reps) < 2 or len(block_reps) > 25:
                continue
            nodes = {rep["entity_id"] for rep in block_reps}
            edges = []
            for left_index, left in enumerate(block_reps):
                for right in block_reps[left_index + 1 :]:
                    if not type_compatible(left["type"], right["type"]):
                        continue
                    if name_similarity(left["folded_name"], right["folded_name"]) >= similarity_threshold:
                        edges.append((left["entity_id"], right["entity_id"]))
            for component in connected_components(nodes, edges):
                add_group(group_sets, f"sim_{block_key}", component)

    if enable_country_state_windows:
        country_candidates = [rep for rep in representatives if country_state_candidate(rep)]
        country_candidates = sorted(country_candidates, key=lambda rep: (rep["folded_name"], rep["type"], rep["entity_id"]))
        for index, rep in enumerate(country_candidates):
            window = country_candidates[max(0, index - 2) : index + 3]
            members = {item["entity_id"] for item in window if type_compatible(rep["type"], item["type"])}
            add_group(group_sets, f"country_state_{rep['entity_id']}", members)

    groups = []
    for raw_index, (group_key, members) in enumerate(group_sets.items(), start=1):
        ordered = sorted(
            members,
            key=lambda entity_id: (
                reps_by_id[entity_id]["folded_name"],
                reps_by_id[entity_id]["type"],
                reps_by_id[entity_id]["entity_id"],
            ),
        )
        safe_prefix = re.sub(r"[^A-Za-z0-9_]+", "_", group_key)[:80]
        for group in chunk_group(ordered, max_group_entities, f"{safe_prefix}_{raw_index:04d}"):
            groups.append(group)
    def group_priority(group: dict) -> tuple[int, int, str]:
        group_id = group["group_id"]
        if group_id.startswith("seed_"):
            prefix_priority = 0
        elif group_id.startswith("fold_"):
            prefix_priority = 1
        elif group_id.startswith("sim_"):
            prefix_priority = 2
        elif group_id.startswith("country_state_"):
            prefix_priority = 3
        else:
            prefix_priority = 4
        return (prefix_priority, -len(group["entity_ids"]), group_id)

    sorted_groups = sorted(groups, key=group_priority)
    deduped_groups = []
    seen_member_sets = set()
    for group in sorted_groups:
        member_key = tuple(group["entity_ids"])
        if member_key in seen_member_sets:
            continue
        seen_member_sets.add(member_key)
        deduped_groups.append(group)
    if max_candidate_groups is not None and max_candidate_groups > 0:
        return deduped_groups[:max_candidate_groups]
    return deduped_groups


def prompt_entity(rep: dict) -> dict:
    return {
        "entity_id": rep["entity_id"],
        "type": rep["type"],
        "name": rep["name"],
        "normalized_name": rep["normalized_name"],
        "aliases": rep.get("aliases", [])[:8],
        "years": rep.get("years", [])[:12],
        "mention_count": rep.get("mention_count", 0),
        "source_chunks": rep.get("source_chunks", [])[:8],
        "description_samples": rep.get("description_samples", [])[:4],
        "evidence_samples": rep.get("evidence_samples", [])[:4],
        "contexts": rep.get("contexts", [])[:3],
    }


def build_prompt(group: dict, reps_by_id: dict[str, dict]) -> str:
    candidate_group = {
        "group_id": group["group_id"],
        "entities": [prompt_entity(reps_by_id[entity_id]) for entity_id in group["entity_ids"]],
    }
    return f"""Bạn là hệ thống căn chỉnh thực thể lịch sử Việt Nam cho GraphRAG.

Nhiệm vụ: xem một nhóm thực thể được trích xuất từ sách giáo khoa lịch sử và quyết định thực thể nào thật sự chỉ cùng một thực thể lịch sử.

Chỉ dùng thông tin trong input. Không bịa thêm sự kiện, ngày tháng, hoặc quan hệ.

Mục tiêu:
- Gộp các tên/biến thể/alias cùng chỉ một thực thể lịch sử.
- Không gộp các thực thể chỉ vì chúng có liên quan.
- Không gộp tổ chức, quốc gia, phong trào, sự kiện, địa danh nếu chúng là các thực thể lịch sử khác nhau.
- Với tên lịch sử mơ hồ như "An Nam", "Đại Việt", "Việt Nam", chỉ gộp nếu context trong mô tả/source cho thấy chúng đang chỉ cùng một thực thể trong ngữ cảnh này.
- Với tên người như "Nguyễn Ái Quốc" và "Hồ Chí Minh", có thể gộp nếu chúng cùng chỉ một cá nhân, nhưng phải giữ cả hai alias.
- Với tên quốc gia/chính quyền như "Mĩ", "Mỹ", "Hoa Kỳ", "Pháp", "thực dân Pháp", hãy phân biệt giữa quốc gia, chính phủ, lực lượng thực dân, và tổ chức nếu context yêu cầu.

Quy tắc quyết định:
1. Chỉ gộp nếu confidence >= 0.80.
2. Nếu không chắc, không gộp; đánh dấu review_required=true.
3. Không gộp khác loại entity trừ khi đó là lỗi type extraction rõ ràng, ví dụ cùng một quốc gia bị trích xuất lúc là Place, lúc là Organization.
4. Không gộp Event với Organization/Place/Person.
5. Không gộp Concept với Event nếu concept chỉ là chủ đề rộng.
6. Luôn giữ original names trong aliases.
7. canonical_name nên là tên phổ biến, rõ ràng nhất trong sách giáo khoa.
8. canonical_type nên là type phù hợp nhất sau khi xem toàn bộ context.
9. observed_types phải giữ tất cả type đã thấy trong input.
10. member_entity_ids phải chỉ dùng ID có trong input.

Input candidate group:
{json.dumps(candidate_group, ensure_ascii=False, indent=2)}

Trả về JSON hợp lệ duy nhất, không markdown, không giải thích ngoài JSON.

JSON schema cần trả về:
{{
  "aligned_entities": [
    {{
      "canonical_name": "Tên chuẩn",
      "canonical_type": "Person|Organization|Event|Place|Time|Concept",
      "observed_types": ["Place", "Organization"],
      "aliases": ["tên alias 1", "tên alias 2"],
      "member_entity_ids": ["entity_id_1", "entity_id_2"],
      "confidence": 0.92,
      "review_required": false,
      "reason": "Lý do ngắn, dựa trên input."
    }}
  ],
  "unmerged_entities": [
    {{
      "entity_id": "entity_id_3",
      "reason": "Không đủ bằng chứng để gộp hoặc là thực thể khác."
    }}
  ]
}}
"""


def build_response_schema() -> dict:
    entity_type_enum = ["Person", "Organization", "Event", "Place", "Time", "Concept"]
    return {
        "type": "OBJECT",
        "properties": {
            "aligned_entities": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "canonical_name": {"type": "STRING"},
                        "canonical_type": {"type": "STRING", "enum": entity_type_enum},
                        "observed_types": {"type": "ARRAY", "items": {"type": "STRING", "enum": entity_type_enum}},
                        "aliases": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "member_entity_ids": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "confidence": {"type": "NUMBER"},
                        "review_required": {"type": "BOOLEAN"},
                        "reason": {"type": "STRING"},
                    },
                    "required": [
                        "canonical_name",
                        "canonical_type",
                        "observed_types",
                        "aliases",
                        "member_entity_ids",
                        "confidence",
                        "review_required",
                        "reason",
                    ],
                },
            },
            "unmerged_entities": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "entity_id": {"type": "STRING"},
                        "reason": {"type": "STRING"},
                    },
                    "required": ["entity_id", "reason"],
                },
            },
        },
        "required": ["aligned_entities", "unmerged_entities"],
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

    alignment_config = config.get("entity_alignment", {})
    client = get_gemini_client(project, location)
    thinking_budget = alignment_config.get("thinking_budget")
    thinking_config = None
    if thinking_budget is not None:
        thinking_config = types.ThinkingConfig(thinking_budget=int(thinking_budget))
    response = client.models.generate_content(
        model=alignment_config.get("model", "gemini-2.5-flash"),
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=float(alignment_config.get("temperature", 0.0)),
            max_output_tokens=int(alignment_config.get("max_output_tokens", 8192)),
            response_mime_type="application/json",
            response_schema=build_response_schema(),
            thinking_config=thinking_config,
        ),
    )
    text = getattr(response, "text", None)
    if not text:
        raise ValueError("Gemini returned an empty response")
    return text


def validate_decision(parsed: dict, group: dict) -> dict:
    group_ids = set(group["entity_ids"])
    aligned_entities = []
    for item in coerce_list(parsed.get("aligned_entities")):
        if not isinstance(item, dict):
            continue
        member_ids = [str(entity_id) for entity_id in coerce_list(item.get("member_entity_ids")) if str(entity_id) in group_ids]
        member_ids = sorted(set(member_ids))
        if len(member_ids) < 2:
            continue
        canonical_name = normalize_text(str(item.get("canonical_name", "")))
        canonical_type = normalize_text(str(item.get("canonical_type", "")))
        if not canonical_name or canonical_type not in TYPE_PRIORITY:
            continue
        aligned_entities.append(
            {
                "canonical_name": canonical_name,
                "canonical_type": canonical_type,
                "observed_types": sorted(
                    {normalize_text(str(value)) for value in coerce_list(item.get("observed_types")) if normalize_text(str(value)) in TYPE_PRIORITY}
                ),
                "aliases": sorted({normalize_text(str(value)) for value in coerce_list(item.get("aliases")) if normalize_text(str(value))}),
                "member_entity_ids": member_ids,
                "confidence": confidence(item.get("confidence")),
                "review_required": bool(item.get("review_required", False)),
                "reason": normalize_text(str(item.get("reason", ""))),
            }
        )
    unmerged_entities = []
    for item in coerce_list(parsed.get("unmerged_entities")):
        if not isinstance(item, dict):
            continue
        entity_id = str(item.get("entity_id", ""))
        if entity_id in group_ids:
            unmerged_entities.append({"entity_id": entity_id, "reason": normalize_text(str(item.get("reason", "")))})
    return {"group_id": group["group_id"], "aligned_entities": aligned_entities, "unmerged_entities": unmerged_entities}


def align_group(group: dict, reps_by_id: dict[str, dict], config: dict, project: str, location: str) -> dict:
    alignment_config = config.get("entity_alignment", {})
    retry_attempts = int(alignment_config.get("retry_attempts", 2))
    prompt = build_prompt(group, reps_by_id)
    last_error = None
    for attempt in range(retry_attempts + 1):
        try:
            raw_response = call_gemini(prompt, config, project, location)
            return validate_decision(parse_json_object(raw_response), group)
        except Exception as exc:
            last_error = exc
            if attempt < retry_attempts:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(str(last_error)) from last_error


def load_rows_by_group(path: str | Path) -> dict[str, dict]:
    output_path = project_path(path)
    if not output_path.exists():
        return {}
    rows = load_json(path)
    return {str(row.get("group_id")): row for row in rows if isinstance(row, dict) and row.get("group_id")}


def ordered_group_rows(groups: list[dict], rows_by_group: dict[str, dict]) -> list[dict]:
    return [rows_by_group[group["group_id"]] for group in groups if group["group_id"] in rows_by_group]


def verify_environment(config: dict) -> tuple[str, str]:
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project:
        raise ValueError("GOOGLE_CLOUD_PROJECT is required for Gemini Vertex entity alignment")
    alignment_config = config.get("entity_alignment", {})
    location_env = alignment_config.get("location_env", "GOOGLE_CLOUD_LOCATION")
    location = os.getenv(location_env, alignment_config.get("default_location", "us-central1"))
    return project, location


class UnionFind:
    def __init__(self, ids: list[str]):
        self.parent = {item: item for item in ids}

    def find(self, item: str) -> str:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def choose_component_type(reps: list[dict], preferred_type: str | None = None) -> str:
    if preferred_type in TYPE_PRIORITY:
        return preferred_type
    counts = Counter()
    for rep in reps:
        counts[rep["type"]] += rep.get("mention_count", 1)
    return sorted(counts, key=lambda item: (-counts[item], -TYPE_PRIORITY.get(item, 0), item))[0]


def choose_component_name(reps: list[dict], preferred_name: str | None = None) -> str:
    if preferred_name:
        return preferred_name
    counts = Counter()
    for rep in reps:
        counts[rep["name"]] += rep.get("mention_count", 1)
    return sorted(counts, key=lambda item: (-counts[item], len(item), item.lower()))[0]


def apply_alignment(
    representatives: list[dict],
    raw_entities: list[dict],
    decisions: list[dict],
    config: dict,
) -> tuple[list[dict], dict]:
    min_confidence = float(config.get("entity_alignment", {}).get("min_merge_confidence", 0.8))
    reps_by_id = {rep["entity_id"]: rep for rep in representatives}
    union_find = UnionFind([rep["entity_id"] for rep in representatives])
    accepted_merges = []
    rejected_merges = []

    for decision in decisions:
        for merge in decision.get("aligned_entities", []):
            member_ids = [entity_id for entity_id in merge.get("member_entity_ids", []) if entity_id in reps_by_id]
            if len(member_ids) < 2:
                continue
            if merge.get("confidence", 0.0) < min_confidence or merge.get("review_required"):
                rejected_merges.append({**merge, "group_id": decision.get("group_id")})
                continue
            first = member_ids[0]
            for member_id in member_ids[1:]:
                union_find.union(first, member_id)
            accepted_merges.append({**merge, "group_id": decision.get("group_id")})

    components: dict[str, list[dict]] = defaultdict(list)
    for rep in representatives:
        components[union_find.find(rep["entity_id"])].append(rep)

    preferred_by_root: dict[str, dict] = {}
    for merge in sorted(accepted_merges, key=lambda item: item.get("confidence", 0.0), reverse=True):
        root = union_find.find(merge["member_entity_ids"][0])
        preferred_by_root.setdefault(root, merge)

    mention_to_aligned = {}
    unique_to_aligned = {}
    aligned_entities = []
    for index, (_, reps) in enumerate(
        sorted(
            components.items(),
            key=lambda item: (
                min(rep["folded_name"] for rep in item[1]),
                min(rep["type"] for rep in item[1]),
                min(rep["entity_id"] for rep in item[1]),
            ),
        ),
        start=1,
    ):
        root = union_find.find(reps[0]["entity_id"])
        preferred = preferred_by_root.get(root, {})
        aligned_id = stable_aligned_id(index)
        aliases = []
        years = []
        source_chunks = []
        mention_ids = []
        descriptions = []
        evidence = []
        observed_types = []
        source_unique_ids = []
        for rep in reps:
            source_unique_ids.append(rep["entity_id"])
            observed_types.append(rep["type"])
            aliases.extend(rep.get("aliases", []))
            aliases.append(rep.get("name", ""))
            years.extend(rep.get("years", []))
            source_chunks.extend(rep.get("source_chunks", []))
            mention_ids.extend(rep.get("mention_ids", []))
            descriptions.extend(rep.get("description_samples", []))
            evidence.extend(rep.get("evidence_samples", []))
        canonical_name = choose_component_name(reps, preferred.get("canonical_name"))
        canonical_type = choose_component_type(reps, preferred.get("canonical_type"))
        aligned = {
            "id": aligned_id,
            "type": canonical_type,
            "name": canonical_name,
            "normalized_name": normalize_key(canonical_name),
            "aliases": sorted({alias for alias in aliases if alias}, key=lambda item: (normalize_key(item), item)),
            "observed_types": sorted(set(observed_types), key=lambda item: (-TYPE_PRIORITY.get(item, 0), item)),
            "description": descriptions[0] if descriptions else "",
            "description_samples": unique_sorted(descriptions)[:8],
            "evidence_samples": unique_sorted(evidence)[:8],
            "years": sorted(set(years)),
            "source_chunks": sorted(set(source_chunks)),
            "source_unique_entity_ids": sorted(source_unique_ids),
            "mention_ids": sorted(mention_ids),
            "mention_count": len(mention_ids),
            "alignment_confidence": preferred.get("confidence", 1.0 if len(reps) == 1 else 0.9),
            "alignment_method": "gemini" if preferred else "exact_normalized_name",
        }
        if preferred:
            aligned["alignment_reason"] = preferred.get("reason", "")
            aligned["alignment_group_id"] = preferred.get("group_id")
        aligned_entities.append(aligned)
        for rep in reps:
            unique_to_aligned[rep["entity_id"]] = aligned_id
            for mention_id in rep.get("mention_ids", []):
                mention_to_aligned[mention_id] = aligned_id

    aligned_by_id = {entity["id"]: entity for entity in aligned_entities}
    raw_by_mention = {entity["mention_id"]: entity for entity in raw_entities}
    alias_rows_by_key = {}
    for mention_id, aligned_id in mention_to_aligned.items():
        raw = raw_by_mention.get(mention_id)
        if not raw:
            continue
        aligned = aligned_by_id[aligned_id]
        key = (raw["normalized_name"], raw["type"], aligned_id)
        row = alias_rows_by_key.setdefault(
            key,
            {
                "alias": raw["name"],
                "normalized_alias": raw["normalized_name"],
                "observed_types": set(),
                "canonical_id": aligned_id,
                "canonical_name": aligned["name"],
                "canonical_type": aligned["type"],
                "mention_ids": [],
            },
        )
        row["observed_types"].add(raw["type"])
        row["mention_ids"].append(mention_id)

    alias_rows = []
    for row in alias_rows_by_key.values():
        row["observed_types"] = sorted(row["observed_types"], key=lambda item: (-TYPE_PRIORITY.get(item, 0), item))
        row["mention_ids"] = sorted(row["mention_ids"])
        row["mention_count"] = len(row["mention_ids"])
        alias_rows.append(row)

    alias_map = {
        "aliases": sorted(alias_rows, key=lambda row: (row["canonical_id"], row["normalized_alias"], row["alias"])),
        "mention_to_entity": mention_to_aligned,
        "unique_entity_to_entity": unique_to_aligned,
        "accepted_merges": accepted_merges,
        "rejected_merges": rejected_merges,
    }
    return aligned_entities, alias_map


def run_gemini_alignment(groups: list[dict], representatives: list[dict], config: dict, args: argparse.Namespace) -> tuple[list[dict], list[dict]]:
    paths = config["paths"]
    reps_by_id = {rep["entity_id"]: rep for rep in representatives}
    decisions_by_group = {} if args.no_resume else load_rows_by_group(paths["entity_alignment_decisions"])
    errors_by_group = {} if args.no_resume else load_rows_by_group(paths["entity_alignment_errors"])
    if args.retry_errors:
        errors_by_group = {}

    selected_groups = groups[: args.limit_groups] if args.limit_groups is not None else groups
    pending = [group for group in selected_groups if group["group_id"] not in decisions_by_group and group["group_id"] not in errors_by_group]

    alignment_config = config.get("entity_alignment", {})
    workers = args.workers if args.workers is not None else int(alignment_config.get("workers", 1))
    checkpoint_every = args.checkpoint_every if args.checkpoint_every is not None else int(alignment_config.get("checkpoint_every", 25))
    workers = max(1, workers)
    checkpoint_every = max(1, checkpoint_every)
    project, location = verify_environment(config)

    print(f"Candidate groups: {len(groups)}")
    print(f"Selected groups: {len(selected_groups)}")
    print(f"Loaded completed decisions: {len(decisions_by_group)}")
    print(f"Loaded previous errors: {len(errors_by_group)}")
    print(f"Aligning {len(pending)} pending groups with {workers} worker(s)")
    print(f"Gemini Vertex project=<set> location={location} model={alignment_config.get('model')}")

    new_completed = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(align_group, group, reps_by_id, config, project, location): group
            for group in pending
        }
        for future in tqdm(as_completed(futures), total=len(futures), desc="Aligning"):
            group = futures[future]
            try:
                decisions_by_group[group["group_id"]] = future.result()
                errors_by_group.pop(group["group_id"], None)
            except Exception as exc:
                errors_by_group[group["group_id"]] = {
                    "group_id": group["group_id"],
                    "entity_ids": group["entity_ids"],
                    "error": str(exc),
                }
            new_completed += 1
            if new_completed % checkpoint_every == 0:
                save_json(ordered_group_rows(selected_groups, decisions_by_group), paths["entity_alignment_decisions"])
                save_json(ordered_group_rows(selected_groups, errors_by_group), paths["entity_alignment_errors"])

    decisions = ordered_group_rows(selected_groups, decisions_by_group)
    errors = ordered_group_rows(selected_groups, errors_by_group)
    save_json(decisions, paths["entity_alignment_decisions"])
    save_json(errors, paths["entity_alignment_errors"])
    return decisions, errors


def deterministic_decisions(groups: list[dict]) -> list[dict]:
    return []


def build_report(
    raw_entities: list[dict],
    representatives: list[dict],
    groups: list[dict],
    decisions: list[dict],
    errors: list[dict],
    aligned_entities: list[dict],
    alias_map: dict,
    used_gemini: bool,
) -> str:
    raw_types = Counter(entity["type"] for entity in raw_entities)
    aligned_types = Counter(entity["type"] for entity in aligned_entities)
    exact_collapsed = len(raw_entities) - len(representatives)
    total_merged_reps = len(representatives) - len(aligned_entities)
    accepted_merges = alias_map.get("accepted_merges", [])
    rejected_merges = alias_map.get("rejected_merges", [])
    multi_alias = [entity for entity in aligned_entities if len(entity.get("aliases", [])) > 1]

    lines = [
        "# Entity Alignment Report",
        "",
        "## Summary",
        "",
        f"- Raw entity mentions: {len(raw_entities)}",
        f"- Unique normalized type/name entities: {len(representatives)}",
        f"- Exact normalized mentions collapsed: {exact_collapsed}",
        f"- Candidate groups generated: {len(groups)}",
        f"- Gemini used: {'yes' if used_gemini else 'no'}",
        f"- Gemini decisions: {len(decisions)}",
        f"- Gemini errors: {len(errors)}",
        f"- Accepted Gemini merge decisions: {len(accepted_merges)}",
        f"- Rejected/low-confidence merge decisions: {len(rejected_merges)}",
        f"- Final aligned entities: {len(aligned_entities)}",
        f"- Unique representatives merged beyond exact normalization: {total_merged_reps}",
        f"- Alias rows: {len(alias_map.get('aliases', []))}",
        f"- Aligned entities with multiple aliases: {len(multi_alias)}",
        "",
        "## Raw Entity Types",
        "",
        "| Type | Count |",
        "|---|---:|",
    ]
    for entity_type, count in raw_types.most_common():
        lines.append(f"| {entity_type} | {count} |")
    lines.extend(["", "## Aligned Entity Types", "", "| Type | Count |", "|---|---:|"])
    for entity_type, count in aligned_types.most_common():
        lines.append(f"| {entity_type} | {count} |")
    lines.extend(["", "## Accepted Merge Examples", ""])
    for merge in accepted_merges[:20]:
        lines.append(
            f"- `{merge.get('canonical_name')}` ({merge.get('canonical_type')}), confidence={merge.get('confidence')}: "
            f"{', '.join(merge.get('member_entity_ids', []))}"
        )
    if not accepted_merges:
        lines.append("- None")
    lines.extend(["", "## Output Artifacts", "", "- `data/outputs/graph/entities_raw.json`", "- `data/outputs/graph/entities_aligned.json`", "- `data/outputs/graph/entity_aliases.json`", "- `data/outputs/graph/entity_alignment_decisions.json`", "- `data/outputs/graph/entity_alignment_errors.json`"])
    return "\n".join(lines) + "\n"


def run_alignment(config: dict, args: argparse.Namespace) -> tuple[list[dict], list[dict], list[dict]]:
    paths = config["paths"]
    rows = load_json(paths["extracted_chunks_cleaned"])
    raw_entities = collect_raw_entities(rows)
    representatives = build_representatives(raw_entities, config)
    groups = build_candidate_groups(representatives, config)
    if args.limit_groups is not None:
        groups_for_decisions = groups[: args.limit_groups]
    else:
        groups_for_decisions = groups

    save_json(raw_entities, paths["entities_raw"])
    if args.no_gemini:
        decisions = deterministic_decisions(groups_for_decisions)
        errors = []
        save_json(decisions, paths["entity_alignment_decisions"])
        save_json(errors, paths["entity_alignment_errors"])
    else:
        decisions, errors = run_gemini_alignment(groups, representatives, config, args)

    aligned_entities, alias_map = apply_alignment(representatives, raw_entities, decisions, config)
    save_json(aligned_entities, paths["entities_aligned"])
    save_json(alias_map, paths["entity_aliases"])
    save_text(
        build_report(raw_entities, representatives, groups, decisions, errors, aligned_entities, alias_map, not args.no_gemini),
        paths["entity_alignment_report"],
    )
    return raw_entities, aligned_entities, errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Align extracted graph entities with Gemini-assisted review.")
    parser.add_argument("--config", default="configs/graph.yaml")
    parser.add_argument("--workers", type=int, default=None, help="Parallel Gemini requests.")
    parser.add_argument("--checkpoint-every", type=int, default=None, help="Save progress every N candidate groups.")
    parser.add_argument("--limit-groups", type=int, default=None, help="Optional smoke-test candidate group limit.")
    parser.add_argument("--no-gemini", action="store_true", help="Run only deterministic exact normalized-name alignment.")
    parser.add_argument("--no-resume", action="store_true", help="Ignore existing Gemini decision outputs.")
    parser.add_argument("--retry-errors", action="store_true", help="Retry candidate groups already listed in errors.")
    args = parser.parse_args()

    load_dotenv()
    config = load_yaml(args.config)
    raw_entities, aligned_entities, errors = run_alignment(config, args)
    print(f"Saved {len(raw_entities)} raw entity mentions to {config['paths']['entities_raw']}")
    print(f"Saved {len(aligned_entities)} aligned entities to {config['paths']['entities_aligned']}")
    print(f"Saved {len(errors)} alignment errors to {config['paths']['entity_alignment_errors']}")
    print(f"Saved alignment report to {config['paths']['entity_alignment_report']}")


if __name__ == "__main__":
    main()
