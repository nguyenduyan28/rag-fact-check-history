"""Build a source-grounded history graph from aligned extraction outputs."""

from __future__ import annotations

import argparse
import re
import unicodedata
from collections import Counter, defaultdict
from typing import Any

from src.common.io import load_json, load_yaml, save_json, save_text
from src.common.normalize import extract_years, normalize_text


def normalize_key(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "").lower()
    text = re.sub(r"[\W_]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def chunk_node_id(chunk_id: str) -> str:
    return f"chunk_{chunk_id}"


def stable_edge_id(index: int) -> str:
    return f"edge_{index:08d}"


def mention_id(chunk_id: str, local_id: str) -> str:
    return f"{chunk_id}:{local_id}"


def as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def build_chunk_nodes(chunks: list[dict]) -> list[dict]:
    nodes = []
    for chunk in chunks:
        chunk_id = normalize_text(str(chunk.get("chunk_id", "")))
        if not chunk_id:
            continue
        text = normalize_text(chunk.get("text", ""))
        nodes.append(
            {
                "id": chunk_node_id(chunk_id),
                "type": "DocumentChunk",
                "name": chunk_id,
                "chunk_id": chunk_id,
                "chunk_type": chunk.get("chunk_type"),
                "book": chunk.get("book"),
                "chapter": chunk.get("chapter"),
                "section": chunk.get("section"),
                "pages": chunk.get("pages", []),
                "source_pages": chunk.get("source_pages", []),
                "source_files": chunk.get("source_files", []),
                "years": sorted(set(as_list(chunk.get("year_mentions")) + list(extract_years(text)))),
                "char_count": chunk.get("char_count", len(text)),
                "text": text,
            }
        )
    return nodes


def build_entity_nodes(aligned_entities: list[dict]) -> list[dict]:
    nodes = []
    for entity in aligned_entities:
        entity_id = normalize_text(str(entity.get("id", "")))
        if not entity_id:
            continue
        years = set(as_list(entity.get("years")))
        years.update(extract_years(entity.get("description", "")))
        years.update(extract_years(" ".join(as_list(entity.get("description_samples")))))
        nodes.append(
            {
                "id": entity_id,
                "type": entity.get("type"),
                "name": entity.get("name"),
                "normalized_name": entity.get("normalized_name"),
                "aliases": entity.get("aliases", []),
                "observed_types": entity.get("observed_types", []),
                "description": entity.get("description", ""),
                "description_samples": entity.get("description_samples", []),
                "evidence_samples": entity.get("evidence_samples", []),
                "years": sorted(year for year in years if isinstance(year, int)),
                "source_chunks": entity.get("source_chunks", []),
                "mention_ids": entity.get("mention_ids", []),
                "mention_count": entity.get("mention_count", 0),
                "alignment_confidence": entity.get("alignment_confidence", 1.0),
                "alignment_method": entity.get("alignment_method", "exact_normalized_name"),
            }
        )
    return nodes


def edge_key(edge: dict) -> tuple:
    return (
        edge.get("source"),
        edge.get("target"),
        edge.get("type"),
        edge.get("source_chunk"),
        normalize_key(edge.get("evidence_text", "")),
        normalize_key(edge.get("description", "")),
    )


def add_edge(edges: list[dict], seen: set[tuple], edge: dict, stats: Counter) -> None:
    key = edge_key(edge)
    if key in seen:
        stats["duplicate_edges_skipped"] += 1
        return
    seen.add(key)
    edge["id"] = stable_edge_id(len(edges) + 1)
    edges.append(edge)


def build_mention_edges(rows: list[dict], mention_to_entity: dict[str, str], stats: Counter) -> list[dict]:
    edges = []
    seen = set()
    mentions_by_chunk_entity: dict[tuple[str, str], list[str]] = defaultdict(list)
    entity_names: dict[tuple[str, str], set[str]] = defaultdict(set)

    for row in rows:
        chunk_id = normalize_text(str(row.get("chunk_id", "")))
        if not chunk_id:
            continue
        for entity in as_list(row.get("entities")):
            if not isinstance(entity, dict):
                continue
            local_id = normalize_text(str(entity.get("local_id", "")))
            mid = mention_id(chunk_id, local_id)
            aligned_id = mention_to_entity.get(mid)
            if not aligned_id:
                stats["mentions_without_aligned_entity"] += 1
                continue
            key = (chunk_id, aligned_id)
            mentions_by_chunk_entity[key].append(mid)
            if entity.get("name"):
                entity_names[key].add(normalize_text(str(entity.get("name"))))

    for (chunk_id, aligned_id), mention_ids in sorted(mentions_by_chunk_entity.items()):
        add_edge(
            edges,
            seen,
            {
                "source": chunk_node_id(chunk_id),
                "target": aligned_id,
                "type": "MENTIONS",
                "description": "Document chunk mentions aligned entity.",
                "evidence_text": "; ".join(sorted(entity_names[(chunk_id, aligned_id)])),
                "source_chunk": chunk_id,
                "confidence": 1.0,
                "mention_ids": sorted(mention_ids),
            },
            stats,
        )
    return edges


def build_relation_edges(rows: list[dict], mention_to_entity: dict[str, str], stats: Counter) -> list[dict]:
    edges = []
    seen = set()
    for row in rows:
        chunk_id = normalize_text(str(row.get("chunk_id", "")))
        if not chunk_id:
            continue
        for index, relation in enumerate(as_list(row.get("relations")), start=1):
            if not isinstance(relation, dict):
                continue
            source_local = normalize_text(str(relation.get("source", "")))
            target_local = normalize_text(str(relation.get("target", "")))
            source_mention = mention_id(chunk_id, source_local)
            target_mention = mention_id(chunk_id, target_local)
            source_id = mention_to_entity.get(source_mention)
            target_id = mention_to_entity.get(target_mention)
            if not source_id or not target_id:
                stats["relations_without_aligned_endpoint"] += 1
                continue
            if source_id == target_id:
                stats["relations_self_loop_after_alignment"] += 1
                continue
            add_edge(
                edges,
                seen,
                {
                    "source": source_id,
                    "target": target_id,
                    "type": normalize_text(str(relation.get("type", "RELATED_TO"))),
                    "description": normalize_text(str(relation.get("description", ""))),
                    "evidence_text": normalize_text(str(relation.get("evidence_text", ""))),
                    "source_chunk": chunk_id,
                    "confidence": float(relation.get("confidence", 0.0) or 0.0),
                    "source_mention_id": source_mention,
                    "target_mention_id": target_mention,
                    "relation_index": index,
                },
                stats,
            )
    return edges


def validate_graph(nodes: list[dict], edges: list[dict]) -> dict:
    node_ids = [node.get("id") for node in nodes]
    edge_ids = [edge.get("id") for edge in edges]
    node_id_set = set(node_ids)
    duplicate_node_ids = len(node_ids) - len(node_id_set)
    duplicate_edge_ids = len(edge_ids) - len(set(edge_ids))
    broken_edges = [edge for edge in edges if edge.get("source") not in node_id_set or edge.get("target") not in node_id_set]
    missing_source_chunk = [edge for edge in edges if not edge.get("source_chunk")]
    missing_evidence = [edge for edge in edges if edge.get("type") != "MENTIONS" and not edge.get("evidence_text")]
    return {
        "duplicate_node_ids": duplicate_node_ids,
        "duplicate_edge_ids": duplicate_edge_ids,
        "broken_edge_count": len(broken_edges),
        "missing_source_chunk_edges": len(missing_source_chunk),
        "relation_edges_missing_evidence": len(missing_evidence),
    }


def build_report(nodes: list[dict], edges: list[dict], stats: Counter, validation: dict) -> str:
    node_types = Counter(node.get("type") for node in nodes)
    edge_types = Counter(edge.get("type") for edge in edges)
    lines = [
        "# Graph Build Report",
        "",
        "## Summary",
        "",
        f"- Nodes: {len(nodes)}",
        f"- Edges: {len(edges)}",
        f"- Duplicate node IDs: {validation['duplicate_node_ids']}",
        f"- Duplicate edge IDs: {validation['duplicate_edge_ids']}",
        f"- Broken edges: {validation['broken_edge_count']}",
        f"- Edges missing `source_chunk`: {validation['missing_source_chunk_edges']}",
        f"- Relation edges missing evidence: {validation['relation_edges_missing_evidence']}",
        "",
        "## Node Types",
        "",
        "| Type | Count |",
        "|---|---:|",
    ]
    for node_type, count in node_types.most_common():
        lines.append(f"| {node_type} | {count} |")
    lines.extend(["", "## Edge Types", "", "| Type | Count |", "|---|---:|"])
    for edge_type, count in edge_types.most_common():
        lines.append(f"| {edge_type} | {count} |")
    lines.extend(["", "## Build Actions", "", "| Action | Count |", "|---|---:|"])
    if stats:
        for key, count in sorted(stats.items()):
            lines.append(f"| `{key}` | {count} |")
    else:
        lines.append("| none | 0 |")
    return "\n".join(lines) + "\n"


def run_build(config: dict) -> tuple[list[dict], list[dict], dict]:
    paths = config["paths"]
    chunks = load_json(paths["cleaned_chunks"])
    rows = load_json(paths["extracted_chunks_cleaned"])
    aligned_entities = load_json(paths["entities_aligned"])
    alias_map = load_json(paths["entity_aliases"])
    mention_to_entity = alias_map.get("mention_to_entity", {})
    stats: Counter = Counter()

    chunk_nodes = build_chunk_nodes(chunks)
    entity_nodes = build_entity_nodes(aligned_entities)
    nodes = chunk_nodes + entity_nodes

    mention_edges = build_mention_edges(rows, mention_to_entity, stats)
    relation_edges = build_relation_edges(rows, mention_to_entity, stats)
    edges = mention_edges + relation_edges
    for index, edge in enumerate(edges, start=1):
        edge["id"] = stable_edge_id(index)

    validation = validate_graph(nodes, edges)
    metadata = {
        "build_method": "deterministic_source_grounded_graph_construction_from_aligned_extractions",
        "inputs": {
            "cleaned_chunks": paths["cleaned_chunks"],
            "extracted_chunks_cleaned": paths["extracted_chunks_cleaned"],
            "entities_aligned": paths["entities_aligned"],
            "entity_aliases": paths["entity_aliases"],
        },
        "node_count": len(nodes),
        "edge_count": len(edges),
        "node_type_counts": dict(Counter(node.get("type") for node in nodes)),
        "edge_type_counts": dict(Counter(edge.get("type") for edge in edges)),
        "validation": validation,
    }

    save_json(nodes, paths["graph_nodes"])
    save_json(edges, paths["graph_edges"])
    save_json({"metadata": metadata, "nodes": nodes, "edges": edges}, paths["history_graph"])
    if paths.get("graph_build_report"):
        save_text(build_report(nodes, edges, stats, validation), paths["graph_build_report"])
    return nodes, edges, validation


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a JSON history graph from aligned extraction outputs.")
    parser.add_argument("--config", default="configs/graph.yaml")
    args = parser.parse_args()

    config = load_yaml(args.config)
    nodes, edges, validation = run_build(config)
    print(f"Saved {len(nodes)} graph nodes to {config['paths']['graph_nodes']}")
    print(f"Saved {len(edges)} graph edges to {config['paths']['graph_edges']}")
    print(f"Saved combined graph to {config['paths']['history_graph']}")
    print(f"Validation: {validation}")


if __name__ == "__main__":
    main()
