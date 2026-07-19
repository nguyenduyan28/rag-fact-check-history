from __future__ import annotations

import argparse

from src.common.io import load_json, load_yaml, save_json
from src.common.normalize import extract_years
from src.facet.graph_index import GraphIndex
from src.facet.normalize import normalize_key


try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover
    def tqdm(iterable, **_):
        return iterable


def add_chunk(
    evidence_by_chunk: dict[str, dict],
    graph_index: GraphIndex,
    chunk_id: str,
    facet_type: str,
    facet_value: str,
    reason: str,
    node_id: str | None = None,
    edge: dict | None = None,
) -> None:
    chunk = graph_index.get_chunk(chunk_id)
    if not chunk:
        return
    item = evidence_by_chunk.setdefault(
        chunk_id,
        {
            "chunk_id": chunk_id,
            "book": chunk.get("book"),
            "chapter": chunk.get("chapter"),
            "section": chunk.get("section"),
            "pages": chunk.get("pages", []),
            "years": chunk.get("years", []),
            "text": chunk.get("text", ""),
            "facet_hits": [],
            "relation_hits": [],
            "node_ids": [],
        },
    )
    hit = {"facet_type": facet_type, "facet_value": facet_value, "reason": reason}
    if hit not in item["facet_hits"]:
        item["facet_hits"].append(hit)
    if node_id and node_id not in item["node_ids"]:
        item["node_ids"].append(node_id)
    if edge:
        relation_hit = {
            "edge_id": edge.get("id"),
            "type": edge.get("type"),
            "source": edge.get("source"),
            "target": edge.get("target"),
            "evidence_text": edge.get("evidence_text", ""),
        }
        if relation_hit not in item["relation_hits"]:
            item["relation_hits"].append(relation_hit)


def retrieve_row(row: dict, graph_index: GraphIndex, config: dict) -> dict:
    evidence_config = config.get("evidence", {})
    max_chunks_per_facet = int(evidence_config.get("max_chunks_per_facet", 5))
    max_chunks_per_claim = int(evidence_config.get("max_chunks_per_claim", 12))
    allowed_relations = set(evidence_config.get("include_neighbor_relations", []))
    evidence_by_chunk: dict[str, dict] = {}

    for facet_match in row.get("facet_matches", []):
        facet_type = facet_match.get("facet_type", "")
        facet_value = facet_match.get("facet_value", "")
        chunks_for_facet = 0
        for match in facet_match.get("matches", []):
            node_id = match.get("node_id")
            if not node_id:
                continue
            for chunk_id in sorted(graph_index.source_chunks_for_node(node_id)):
                add_chunk(evidence_by_chunk, graph_index, chunk_id, facet_type, facet_value, "node_mention", node_id=node_id)
                chunks_for_facet += 1
                if chunks_for_facet >= max_chunks_per_facet:
                    break
            for edge in graph_index.relation_edges_for_node(node_id, allowed_relations):
                source_chunk = edge.get("source_chunk")
                if source_chunk:
                    add_chunk(
                        evidence_by_chunk,
                        graph_index,
                        source_chunk,
                        facet_type,
                        facet_value,
                        "relation_1hop",
                        node_id=node_id,
                        edge=edge,
                    )
                    chunks_for_facet += 1
                if chunks_for_facet >= max_chunks_per_facet:
                    break
            if chunks_for_facet >= max_chunks_per_facet:
                break

        if facet_type == "time":
            for year in extract_years(facet_value):
                for chunk_id in sorted(graph_index.year_to_chunks.get(year, set()))[:max_chunks_per_facet]:
                    add_chunk(evidence_by_chunk, graph_index, chunk_id, facet_type, facet_value, "temporal_index")

    evidence = list(evidence_by_chunk.values())
    evidence.sort(
        key=lambda item: (
            -len({(hit["facet_type"], normalize_key(hit["facet_value"])) for hit in item["facet_hits"]}),
            -len(item["relation_hits"]),
            item["chunk_id"],
        )
    )
    return {
        **row,
        "evidence": evidence[:max_chunks_per_claim],
        "evidence_summary": {
            "candidate_chunks": len(evidence),
            "selected_chunks": min(len(evidence), max_chunks_per_claim),
        },
    }


def run_retrieve(config: dict) -> list[dict]:
    rows = load_json(config["paths"]["facet_matches"])
    graph_index = GraphIndex(config)
    output = [retrieve_row(row, graph_index, config) for row in tqdm(rows, desc="Retrieving evidence")]
    save_json(output, config["paths"]["facet_evidence"])
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Retrieve 1-hop graph evidence for matched facets.")
    parser.add_argument("--config", default="configs/facet/facet.yaml")
    args = parser.parse_args()
    config = load_yaml(args.config)
    rows = run_retrieve(config)
    print(f"Saved {len(rows)} rows to {config['paths']['facet_evidence']}")


if __name__ == "__main__":
    main()
