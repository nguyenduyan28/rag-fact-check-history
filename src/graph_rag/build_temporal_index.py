"""Build temporal lookup indexes for graph retrieval."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from typing import Any

from src.common.io import load_json, load_yaml, save_json, save_text
from src.common.normalize import extract_years, normalize_text


def as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def valid_years(values: list[Any]) -> set[int]:
    years = set()
    for value in values:
        if isinstance(value, int) and 1000 <= value <= 2099:
            years.add(value)
        elif isinstance(value, str):
            years.update(extract_years(value))
    return years


def node_years(node: dict) -> list[int]:
    text_fields = [
        node.get("name", ""),
        node.get("description", ""),
        node.get("text", ""),
        " ".join(as_list(node.get("aliases"))),
        " ".join(as_list(node.get("description_samples"))),
        " ".join(as_list(node.get("evidence_samples"))),
    ]
    years = valid_years(as_list(node.get("years")))
    years.update(extract_years(" ".join(normalize_text(str(item)) for item in text_fields)))
    return sorted(years)


def edge_years(edge: dict) -> list[int]:
    text = " ".join(
        normalize_text(str(item))
        for item in [
            edge.get("description", ""),
            edge.get("evidence_text", ""),
            edge.get("source_chunk", ""),
        ]
    )
    return sorted(extract_years(text))


def chunk_years(chunk: dict) -> list[int]:
    text = " ".join(
        normalize_text(str(item))
        for item in [
            chunk.get("text", ""),
            chunk.get("contextual_text", ""),
            chunk.get("section", ""),
            chunk.get("chapter", ""),
        ]
    )
    years = valid_years(as_list(chunk.get("year_mentions")))
    years.update(extract_years(text))
    return sorted(years)


def add_reverse(mapping: dict[str, list[int]], target: dict[str, list[str]]) -> None:
    for item_id, years in mapping.items():
        for year in years:
            target[str(year)].append(item_id)


def sorted_reverse(target: dict[str, list[str]]) -> dict[str, list[str]]:
    return {year: sorted(set(ids)) for year, ids in sorted(target.items(), key=lambda item: int(item[0]))}


def build_report(index: dict) -> str:
    metadata = index["metadata"]
    node_year_counts = Counter(len(years) for years in index["node_to_years"].values())
    edge_year_counts = Counter(len(years) for years in index["edge_to_years"].values())
    chunk_year_counts = Counter(len(years) for years in index["chunk_to_years"].values())
    top_years = sorted(index["year_to_chunks"].items(), key=lambda item: (-len(item[1]), int(item[0])))[:20]

    lines = [
        "# Temporal Index Report",
        "",
        "## Summary",
        "",
        f"- Nodes indexed: {metadata['node_count']}",
        f"- Edges indexed: {metadata['edge_count']}",
        f"- Chunks indexed: {metadata['chunk_count']}",
        f"- Nodes with years: {metadata['nodes_with_years']}",
        f"- Edges with years: {metadata['edges_with_years']}",
        f"- Chunks with years: {metadata['chunks_with_years']}",
        f"- Unique years: {metadata['unique_year_count']}",
        f"- Min year: {metadata.get('min_year')}",
        f"- Max year: {metadata.get('max_year')}",
        "",
        "## Year Count Per Item",
        "",
        "| Years per item | Nodes | Edges | Chunks |",
        "|---:|---:|---:|---:|",
    ]
    for count in sorted(set(node_year_counts) | set(edge_year_counts) | set(chunk_year_counts)):
        lines.append(
            f"| {count} | {node_year_counts.get(count, 0)} | {edge_year_counts.get(count, 0)} | {chunk_year_counts.get(count, 0)} |"
        )
    lines.extend(["", "## Top Years By Chunk Coverage", "", "| Year | Chunks |", "|---:|---:|"])
    for year, chunks in top_years:
        lines.append(f"| {year} | {len(chunks)} |")
    return "\n".join(lines) + "\n"


def run_build(config: dict) -> dict:
    paths = config["paths"]
    nodes = load_json(paths["graph_nodes"])
    edges = load_json(paths["graph_edges"])
    chunks = load_json(paths["cleaned_chunks"])

    node_to_years = {node["id"]: node_years(node) for node in nodes if node.get("id")}
    edge_to_years = {edge["id"]: edge_years(edge) for edge in edges if edge.get("id")}
    chunk_to_years = {chunk["chunk_id"]: chunk_years(chunk) for chunk in chunks if chunk.get("chunk_id")}

    year_to_nodes: dict[str, list[str]] = defaultdict(list)
    year_to_edges: dict[str, list[str]] = defaultdict(list)
    year_to_chunks: dict[str, list[str]] = defaultdict(list)
    add_reverse(node_to_years, year_to_nodes)
    add_reverse(edge_to_years, year_to_edges)
    add_reverse(chunk_to_years, year_to_chunks)

    all_years = sorted({year for years in node_to_years.values() for year in years} | {year for years in edge_to_years.values() for year in years} | {year for years in chunk_to_years.values() for year in years})
    index = {
        "metadata": {
            "build_method": "deterministic_temporal_index_from_graph_and_chunks",
            "node_count": len(nodes),
            "edge_count": len(edges),
            "chunk_count": len(chunks),
            "nodes_with_years": sum(1 for years in node_to_years.values() if years),
            "edges_with_years": sum(1 for years in edge_to_years.values() if years),
            "chunks_with_years": sum(1 for years in chunk_to_years.values() if years),
            "unique_year_count": len(all_years),
            "min_year": min(all_years) if all_years else None,
            "max_year": max(all_years) if all_years else None,
        },
        "node_to_years": node_to_years,
        "edge_to_years": edge_to_years,
        "chunk_to_years": chunk_to_years,
        "year_to_nodes": sorted_reverse(year_to_nodes),
        "year_to_edges": sorted_reverse(year_to_edges),
        "year_to_chunks": sorted_reverse(year_to_chunks),
    }
    save_json(index, paths["temporal_index"])
    if paths.get("temporal_index_report"):
        save_text(build_report(index), paths["temporal_index_report"])
    return index


def main() -> None:
    parser = argparse.ArgumentParser(description="Build temporal index from graph and cleaned chunks.")
    parser.add_argument("--config", default="configs/graph.yaml")
    args = parser.parse_args()

    config = load_yaml(args.config)
    index = run_build(config)
    metadata = index["metadata"]
    print(f"Saved temporal index to {config['paths']['temporal_index']}")
    print(f"Nodes with years: {metadata['nodes_with_years']}/{metadata['node_count']}")
    print(f"Edges with years: {metadata['edges_with_years']}/{metadata['edge_count']}")
    print(f"Chunks with years: {metadata['chunks_with_years']}/{metadata['chunk_count']}")


if __name__ == "__main__":
    main()
