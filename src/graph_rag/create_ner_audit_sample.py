"""Create CSV samples for manual NER/graph audit.

Run:
    python3 src/graph_rag/create_ner_audit_sample.py
    python3 src/graph_rag/create_ner_audit_sample.py --rate 0.1 --seed 42

Input:
    data/outputs/graph/entities_raw.json
    data/outputs/graph/extracted_chunks_cleaned.json
    data/outputs/graph/entity_aliases.json
    data/outputs/corpus/chunks.json

Output:
    data/outputs/audit/ner_entity_audit.csv
    data/outputs/audit/ner_relation_audit.csv
    data/outputs/audit/ner_alias_audit.csv
    data/outputs/audit/ner_audit_report.json
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.common.io import load_json, project_path, save_json


DEFAULT_OUTPUT_DIR = "data/outputs/audit"
AUDIT_COLUMNS = [
    "is_valid",
    "type_correct",
    "evidence_support",
    "direction_correct",
    "notes",
]


def as_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else str(value or "")


def preview(text: str, max_chars: int = 500) -> str:
    text = " ".join(str(text or "").split())
    return text[:max_chars]


def stratified_sample(rows: list[dict], group_key: str, rate: float, seed: int) -> list[dict]:
    rng = random.Random(seed)
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[str(row.get(group_key, "unknown"))].append(row)

    sampled = []
    for group_name in sorted(groups):
        group = groups[group_name]
        n = max(1, math.ceil(len(group) * rate))
        sampled.extend(rng.sample(group, min(n, len(group))))
    return sampled


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def build_entity_rows(entities: list[dict], chunk_text_by_id: dict[str, str]) -> list[dict]:
    rows = []
    for entity in entities:
        rows.append(
            {
                "audit_kind": "entity",
                "item_id": entity.get("mention_id"),
                "entity_type": entity.get("type"),
                "name": entity.get("name"),
                "description": entity.get("description"),
                "evidence_text": entity.get("evidence_text"),
                "confidence": entity.get("confidence"),
                "years": as_json(entity.get("years", [])),
                "chunk_id": entity.get("chunk_id"),
                "book": entity.get("book"),
                "chapter": entity.get("chapter"),
                "section": entity.get("section"),
                "pages": as_json(entity.get("pages", [])),
                "source_files": as_json(entity.get("source_files", [])),
                "chunk_text_preview": preview(chunk_text_by_id.get(entity.get("chunk_id"), "")),
                **{column: "" for column in AUDIT_COLUMNS},
            }
        )
    return rows


def build_relation_rows(chunks: list[dict], chunk_text_by_id: dict[str, str]) -> list[dict]:
    rows = []
    for chunk in chunks:
        entities = {entity["local_id"]: entity for entity in chunk.get("entities", [])}
        for index, relation in enumerate(chunk.get("relations", []), start=1):
            source = entities.get(relation.get("source"), {})
            target = entities.get(relation.get("target"), {})
            rows.append(
                {
                    "audit_kind": "relation",
                    "item_id": (
                        f"{chunk.get('chunk_id')}:{index}:"
                        f"{relation.get('source')}-{relation.get('type')}-{relation.get('target')}"
                    ),
                    "relation_type": relation.get("type"),
                    "source_id": relation.get("source"),
                    "source_type": source.get("type"),
                    "source_name": source.get("name"),
                    "target_id": relation.get("target"),
                    "target_type": target.get("type"),
                    "target_name": target.get("name"),
                    "description": relation.get("description"),
                    "evidence_text": relation.get("evidence_text"),
                    "confidence": relation.get("confidence"),
                    "chunk_id": chunk.get("chunk_id"),
                    "book": chunk.get("book"),
                    "chapter": chunk.get("chapter"),
                    "section": chunk.get("section"),
                    "pages": as_json(chunk.get("pages", [])),
                    "source_files": as_json(chunk.get("source_files", [])),
                    "chunk_text_preview": preview(chunk_text_by_id.get(chunk.get("chunk_id"), "")),
                    **{column: "" for column in AUDIT_COLUMNS},
                }
            )
    return rows


def build_alias_rows(alias_data: dict) -> list[dict]:
    aliases = alias_data.get("aliases", [])
    rows = []
    for alias in aliases:
        rows.append(
            {
                "audit_kind": "alias",
                "item_id": f"{alias.get('canonical_id')}::{alias.get('alias')}",
                "canonical_id": alias.get("canonical_id"),
                "canonical_type": alias.get("canonical_type"),
                "canonical_name": alias.get("canonical_name"),
                "alias": alias.get("alias"),
                "normalized_alias": alias.get("normalized_alias"),
                "observed_types": as_json(alias.get("observed_types", [])),
                "mention_count": alias.get("mention_count"),
                "mention_ids": as_json(alias.get("mention_ids", [])),
                "is_valid": "",
                "type_correct": "",
                "evidence_support": "",
                "direction_correct": "",
                "notes": "",
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Create manual audit CSVs for NER/graph artifacts.")
    parser.add_argument("--rate", type=float, default=0.10, help="Sampling rate per type/group.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--entities", default="data/outputs/graph/entities_raw.json")
    parser.add_argument("--chunks", default="data/outputs/graph/extracted_chunks_cleaned.json")
    parser.add_argument("--corpus-chunks", default="data/outputs/corpus/chunks.json")
    parser.add_argument("--aliases", default="data/outputs/graph/entity_aliases.json")
    args = parser.parse_args()

    if not 0 < args.rate <= 1:
        raise ValueError("--rate must be in (0, 1].")

    entities = load_json(args.entities)
    chunks = load_json(args.chunks)
    corpus_chunks = load_json(args.corpus_chunks)
    aliases = load_json(args.aliases)
    chunk_text_by_id = {
        chunk.get("chunk_id"): chunk.get("text", "")
        for chunk in corpus_chunks
        if chunk.get("chunk_id")
    }

    entity_rows = stratified_sample(
        build_entity_rows(entities, chunk_text_by_id), "entity_type", args.rate, args.seed
    )
    relation_rows = stratified_sample(
        build_relation_rows(chunks, chunk_text_by_id), "relation_type", args.rate, args.seed
    )
    alias_rows = stratified_sample(build_alias_rows(aliases), "canonical_type", args.rate, args.seed)

    output_dir = project_path(args.output_dir)
    entity_path = output_dir / "ner_entity_audit.csv"
    relation_path = output_dir / "ner_relation_audit.csv"
    alias_path = output_dir / "ner_alias_audit.csv"
    report_path = output_dir / "ner_audit_report.json"

    entity_fields = [
        "audit_kind",
        "item_id",
        "entity_type",
        "name",
        "description",
        "evidence_text",
        "confidence",
        "years",
        "chunk_id",
        "book",
        "chapter",
        "section",
        "pages",
        "source_files",
        "chunk_text_preview",
        *AUDIT_COLUMNS,
    ]
    relation_fields = [
        "audit_kind",
        "item_id",
        "relation_type",
        "source_id",
        "source_type",
        "source_name",
        "target_id",
        "target_type",
        "target_name",
        "description",
        "evidence_text",
        "confidence",
        "chunk_id",
        "book",
        "chapter",
        "section",
        "pages",
        "source_files",
        "chunk_text_preview",
        *AUDIT_COLUMNS,
    ]
    alias_fields = [
        "audit_kind",
        "item_id",
        "canonical_id",
        "canonical_type",
        "canonical_name",
        "alias",
        "normalized_alias",
        "observed_types",
        "mention_count",
        "mention_ids",
        *AUDIT_COLUMNS,
    ]

    write_csv(entity_path, entity_rows, entity_fields)
    write_csv(relation_path, relation_rows, relation_fields)
    write_csv(alias_path, alias_rows, alias_fields)

    report = {
        "rate": args.rate,
        "seed": args.seed,
        "totals": {
            "entities": len(entities),
            "relations": sum(len(chunk.get("relations", [])) for chunk in chunks),
            "aliases": len(aliases.get("aliases", [])),
        },
        "sampled": {
            "entities": len(entity_rows),
            "relations": len(relation_rows),
            "aliases": len(alias_rows),
        },
        "sampled_by_type": {
            "entities": dict(Counter(row["entity_type"] for row in entity_rows)),
            "relations": dict(Counter(row["relation_type"] for row in relation_rows)),
            "aliases": dict(Counter(row["canonical_type"] for row in alias_rows)),
        },
        "outputs": {
            "entities": str(entity_path.relative_to(project_path("."))),
            "relations": str(relation_path.relative_to(project_path("."))),
            "aliases": str(alias_path.relative_to(project_path("."))),
        },
    }
    save_json(report, report_path)

    print(f"Entity audit rows: {len(entity_rows)} -> {entity_path.relative_to(project_path('.'))}")
    print(f"Relation audit rows: {len(relation_rows)} -> {relation_path.relative_to(project_path('.'))}")
    print(f"Alias audit rows: {len(alias_rows)} -> {alias_path.relative_to(project_path('.'))}")
    print(f"Report: {report_path.relative_to(project_path('.'))}")


if __name__ == "__main__":
    main()
