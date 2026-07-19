"""Clean raw LLM entity extraction output before graph construction."""

from __future__ import annotations

import argparse
import re
import unicodedata
from collections import Counter
from typing import Any

from src.common.io import load_json, load_yaml, save_json, save_text
from src.common.normalize import normalize_text


ENTITY_PRIORITY = {
    "Event": 60,
    "Person": 55,
    "Organization": 55,
    "Place": 45,
    "Time": 45,
    "Concept": 20,
}

RELATION_PRIORITY = {
    "CAUSES": 60,
    "RESULTS_IN": 60,
    "PARTICIPATED_IN": 55,
    "OCCURRED_AT": 50,
    "BEFORE": 45,
    "AFTER": 45,
    "LOCATED_IN": 35,
    "RELATED_TO": 20,
}


def normalize_key(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "").lower()
    text = re.sub(r"[\W_]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    output = []
    for item in value:
        text = normalize_text(str(item))
        if text and text not in output:
            output.append(text)
    return output


def int_years(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    years = []
    for item in value:
        if isinstance(item, int) and 1000 <= item <= 2099 and item not in years:
            years.append(item)
    return sorted(years)


def should_drop_entity(entity: dict, config: dict, stats: Counter) -> bool:
    cleanup_config = config.get("extraction_cleanup", {})
    entity_type = entity.get("type")
    name = normalize_text(entity.get("name", ""))
    if not entity_type or not name:
        stats["drop_entity_empty_required_field"] += 1
        return True

    min_confidence = float(cleanup_config.get("min_entity_confidence", 0.8))
    if confidence(entity.get("confidence")) < min_confidence:
        stats["drop_entity_low_confidence"] += 1
        return True

    if entity_type == "Concept":
        max_concept_chars = int(cleanup_config.get("drop_long_concept_names_over_chars", 80))
        if len(name) > max_concept_chars:
            stats["drop_entity_long_concept_name"] += 1
            return True
        generic = {normalize_key(item) for item in cleanup_config.get("drop_generic_concepts", [])}
        if normalize_key(name) in generic:
            stats["drop_entity_generic_concept"] += 1
            return True

    return False


def canonical_entity(entity: dict) -> dict:
    return {
        "local_id": normalize_text(str(entity.get("local_id", ""))),
        "type": normalize_text(str(entity.get("type", ""))),
        "name": normalize_text(str(entity.get("name", ""))),
        "aliases": string_list(entity.get("aliases", [])),
        "description": normalize_text(str(entity.get("description", ""))),
        "years": int_years(entity.get("years", [])),
        "evidence_text": normalize_text(str(entity.get("evidence_text", ""))),
        "confidence": confidence(entity.get("confidence")),
    }


def merge_entities(entities: list[dict], stats: Counter) -> tuple[list[dict], dict[str, str]]:
    by_key: dict[tuple[str, str], dict] = {}
    id_map: dict[str, str] = {}
    for entity in entities:
        key = (entity["type"], normalize_key(entity["name"]))
        if key not in by_key:
            by_key[key] = entity
            id_map[entity["local_id"]] = entity["local_id"]
            continue

        kept = by_key[key]
        stats["merge_duplicate_entity_in_chunk"] += 1
        id_map[entity["local_id"]] = kept["local_id"]
        kept["aliases"] = sorted(set(kept.get("aliases", [])) | set(entity.get("aliases", [])))
        kept["years"] = sorted(set(kept.get("years", [])) | set(entity.get("years", [])))
        if entity.get("confidence", 0) > kept.get("confidence", 0):
            kept["description"] = entity.get("description", kept.get("description", ""))
            kept["evidence_text"] = entity.get("evidence_text", kept.get("evidence_text", ""))
            kept["confidence"] = entity.get("confidence", kept.get("confidence", 0.0))

    return list(by_key.values()), id_map


def fix_relation_type_and_direction(relation: dict, entities_by_id: dict[str, dict], stats: Counter) -> dict | None:
    source = relation.get("source")
    target = relation.get("target")
    relation_type = relation.get("type")
    source_type = entities_by_id[source]["type"]
    target_type = entities_by_id[target]["type"]

    if relation_type == "OCCURRED_AT":
        if source_type in {"Place", "Time"} and target_type == "Event":
            relation["source"], relation["target"] = target, source
            stats["fix_swap_occurred_at"] += 1
        elif source_type != "Event":
            relation["type"] = "RELATED_TO"
            stats["fix_occurred_at_to_related_to"] += 1
        return relation

    if relation_type == "PARTICIPATED_IN":
        if source_type == "Event" and target_type in {"Person", "Organization"}:
            relation["source"], relation["target"] = target, source
            stats["fix_swap_participated_in"] += 1
        elif source_type not in {"Person", "Organization"} or target_type != "Event":
            relation["type"] = "RELATED_TO"
            stats["fix_participated_in_to_related_to"] += 1
        return relation

    if relation_type == "LOCATED_IN":
        if source_type == "Event" and target_type == "Place":
            relation["type"] = "OCCURRED_AT"
            stats["fix_located_in_to_occurred_at"] += 1
        elif source_type != "Place" or target_type != "Place":
            relation["type"] = "RELATED_TO"
            stats["fix_located_in_to_related_to"] += 1
        return relation

    if relation_type in {"BEFORE", "AFTER"}:
        if source_type not in {"Event", "Time"} or target_type not in {"Event", "Time"}:
            relation["type"] = "RELATED_TO"
            stats[f"fix_{relation_type.lower()}_to_related_to"] += 1
        return relation

    return relation


def canonical_relation(relation: dict, id_map: dict[str, str], entities_by_id: dict[str, dict], config: dict, stats: Counter) -> dict | None:
    cleanup_config = config.get("extraction_cleanup", {})
    relation_type = normalize_text(str(relation.get("type", "")))
    source = id_map.get(normalize_text(str(relation.get("source", ""))))
    target = id_map.get(normalize_text(str(relation.get("target", ""))))
    if not source or not target or source not in entities_by_id or target not in entities_by_id:
        stats["drop_relation_unknown_endpoint"] += 1
        return None
    if source == target:
        stats["drop_relation_self_loop"] += 1
        return None
    relation_confidence = confidence(relation.get("confidence"))
    if relation_confidence < float(cleanup_config.get("min_relation_confidence", 0.8)):
        stats["drop_relation_low_confidence"] += 1
        return None

    cleaned = {
        "source": source,
        "target": target,
        "type": relation_type,
        "description": normalize_text(str(relation.get("description", ""))),
        "evidence_text": normalize_text(str(relation.get("evidence_text", ""))),
        "confidence": relation_confidence,
    }
    if not cleaned["type"] or not cleaned["description"]:
        stats["drop_relation_empty_required_field"] += 1
        return None
    return fix_relation_type_and_direction(cleaned, entities_by_id, stats)


def relation_key(relation: dict) -> tuple[str, str, str, str]:
    return (
        relation.get("source", ""),
        relation.get("type", ""),
        relation.get("target", ""),
        normalize_key(relation.get("description", "")),
    )


def deduplicate_relations(relations: list[dict], stats: Counter) -> list[dict]:
    output = []
    seen = set()
    for relation in relations:
        key = relation_key(relation)
        if key in seen:
            stats["drop_duplicate_relation_in_chunk"] += 1
            continue
        seen.add(key)
        output.append(relation)
    return output


def entity_score(entity: dict, degree: Counter) -> float:
    name_length_penalty = max(0, len(entity.get("name", "")) - 60) * 0.2
    return (
        confidence(entity.get("confidence")) * 100
        + ENTITY_PRIORITY.get(entity.get("type"), 0)
        + degree.get(entity.get("local_id"), 0) * 6
        + len(entity.get("years", [])) * 4
        - name_length_penalty
    )


def relation_score(relation: dict, entities_by_id: dict[str, dict]) -> float:
    source = entities_by_id.get(relation.get("source"), {})
    target = entities_by_id.get(relation.get("target"), {})
    return (
        confidence(relation.get("confidence")) * 100
        + RELATION_PRIORITY.get(relation.get("type"), 0)
        + ENTITY_PRIORITY.get(source.get("type"), 0) * 0.1
        + ENTITY_PRIORITY.get(target.get("type"), 0) * 0.1
    )


def cap_entities_and_relations(entities: list[dict], relations: list[dict], config: dict, stats: Counter) -> tuple[list[dict], list[dict]]:
    cleanup_config = config.get("extraction_cleanup", {})
    max_entities = int(cleanup_config.get("max_entities_per_chunk", 12))
    max_relations = int(cleanup_config.get("max_relations_per_chunk", 20))

    degree = Counter()
    for relation in relations:
        degree[relation.get("source")] += 1
        degree[relation.get("target")] += 1

    if len(entities) > max_entities:
        keep_ids = {
            entity["local_id"]
            for entity in sorted(entities, key=lambda item: entity_score(item, degree), reverse=True)[:max_entities]
        }
        stats["drop_entity_over_chunk_cap"] += len(entities) - len(keep_ids)
        entities = [entity for entity in entities if entity["local_id"] in keep_ids]
        relations_before = len(relations)
        relations = [
            relation
            for relation in relations
            if relation.get("source") in keep_ids and relation.get("target") in keep_ids
        ]
        stats["drop_relation_endpoint_removed_by_cap"] += relations_before - len(relations)

    entities_by_id = {entity["local_id"]: entity for entity in entities}
    if len(relations) > max_relations:
        stats["drop_relation_over_chunk_cap"] += len(relations) - max_relations
        relations = sorted(
            relations,
            key=lambda relation: relation_score(relation, entities_by_id),
            reverse=True,
        )[:max_relations]

    return entities, relations


def clean_row(row: dict, config: dict, stats: Counter) -> dict:
    raw_entities = row.get("entities", []) if isinstance(row.get("entities", []), list) else []
    raw_relations = row.get("relations", []) if isinstance(row.get("relations", []), list) else []
    stats["raw_entities"] += len(raw_entities)
    stats["raw_relations"] += len(raw_relations)

    entities = []
    for entity in raw_entities:
        if not isinstance(entity, dict):
            stats["drop_entity_non_object"] += 1
            continue
        cleaned = canonical_entity(entity)
        if should_drop_entity(cleaned, config, stats):
            continue
        entities.append(cleaned)

    entities, id_map = merge_entities(entities, stats)
    entities_by_id = {entity["local_id"]: entity for entity in entities}

    relations = []
    for relation in raw_relations:
        if not isinstance(relation, dict):
            stats["drop_relation_non_object"] += 1
            continue
        cleaned = canonical_relation(relation, id_map, entities_by_id, config, stats)
        if cleaned:
            relations.append(cleaned)

    relations = deduplicate_relations(relations, stats)
    entities, relations = cap_entities_and_relations(entities, relations, config, stats)

    stats["clean_entities"] += len(entities)
    stats["clean_relations"] += len(relations)
    if not entities:
        stats["rows_empty_entities_after_cleanup"] += 1
    if not relations:
        stats["rows_empty_relations_after_cleanup"] += 1

    output = {
        "chunk_id": row.get("chunk_id"),
        "book": row.get("book"),
        "chapter": row.get("chapter"),
        "section": row.get("section"),
        "pages": row.get("pages", []),
        "source_pages": row.get("source_pages", []),
        "source_files": row.get("source_files", []),
        "chunk_year_mentions": row.get("chunk_year_mentions", []),
        "entities": entities,
        "relations": relations,
    }
    if row.get("validation_warnings"):
        output["validation_warnings"] = row["validation_warnings"]
    return output


def build_report(rows: list[dict], cleaned_rows: list[dict], stats: Counter) -> str:
    entity_types = Counter(entity.get("type") for row in cleaned_rows for entity in row.get("entities", []))
    relation_types = Counter(relation.get("type") for row in cleaned_rows for relation in row.get("relations", []))

    lines = [
        "# Extraction Cleanup Report",
        "",
        "## Summary",
        "",
        f"- Input chunks: {len(rows)}",
        f"- Output chunks: {len(cleaned_rows)}",
        f"- Raw entities: {stats['raw_entities']}",
        f"- Clean entities: {stats['clean_entities']}",
        f"- Raw relations: {stats['raw_relations']}",
        f"- Clean relations: {stats['clean_relations']}",
        f"- Rows with no entities after cleanup: {stats['rows_empty_entities_after_cleanup']}",
        f"- Rows with no relations after cleanup: {stats['rows_empty_relations_after_cleanup']}",
        "",
        "## Entity Types",
        "",
        "| Type | Count |",
        "|---|---:|",
    ]
    for entity_type, count in entity_types.most_common():
        lines.append(f"| {entity_type} | {count} |")

    lines.extend(["", "## Relation Types", "", "| Type | Count |", "|---|---:|"])
    for relation_type, count in relation_types.most_common():
        lines.append(f"| {relation_type} | {count} |")

    cleanup_events = [(key, value) for key, value in stats.items() if key not in {"raw_entities", "raw_relations", "clean_entities", "clean_relations"} and value]
    lines.extend(["", "## Cleanup Actions", "", "| Action | Count |", "|---|---:|"])
    for key, value in sorted(cleanup_events):
        lines.append(f"| `{key}` | {value} |")

    return "\n".join(lines) + "\n"


def run_cleanup(config: dict) -> tuple[list[dict], Counter]:
    paths = config["paths"]
    rows = load_json(paths["extracted_chunks"])
    stats: Counter = Counter()
    cleaned_rows = [clean_row(row, config, stats) for row in rows]
    save_json(cleaned_rows, paths["extracted_chunks_cleaned"])
    save_text(build_report(rows, cleaned_rows, stats), paths["extraction_cleanup_report"])
    return cleaned_rows, stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean raw graph extraction output.")
    parser.add_argument("--config", default="configs/graph.yaml")
    args = parser.parse_args()

    config = load_yaml(args.config)
    cleaned_rows, stats = run_cleanup(config)
    print(f"Saved {len(cleaned_rows)} cleaned chunks to {config['paths']['extracted_chunks_cleaned']}")
    print(f"Raw entities: {stats['raw_entities']} -> clean entities: {stats['clean_entities']}")
    print(f"Raw relations: {stats['raw_relations']} -> clean relations: {stats['clean_relations']}")
    print(f"Saved cleanup report to {config['paths']['extraction_cleanup_report']}")


if __name__ == "__main__":
    main()
