from __future__ import annotations

import argparse
from collections import Counter

from src.common.io import load_json, load_yaml, save_json, save_text


def normalize_text_evidence(doc: dict) -> dict:
    doc_id = doc.get("doc_id") or doc.get("source") or f"text_rank_{doc.get('rank')}"
    return {
        "chunk_id": doc_id,
        "source_branch": "text",
        "book": doc.get("book"),
        "chapter": doc.get("chapter"),
        "section": doc.get("section"),
        "pages": doc.get("pages") or ([doc.get("page")] if doc.get("page") is not None else []),
        "years": doc.get("year_mentions", []),
        "text": doc.get("text", ""),
        "facet_hits": [],
        "relation_hits": [],
        "node_ids": [],
        "scores": {
            "final": float(doc.get("score", 0.0) or 0.0),
            "text_rank": int(doc.get("rank", 0) or 0),
            "bm25": float(doc.get("bm25_score", 0.0) or 0.0),
            "dense": float(doc.get("dense_score", 0.0) or 0.0),
        },
    }


def normalize_graph_evidence(evidence: dict) -> dict:
    item = dict(evidence)
    item["source_branch"] = "graph"
    item.setdefault("scores", {})
    item.setdefault("facet_hits", [])
    item.setdefault("relation_hits", [])
    item.setdefault("node_ids", [])
    return item


def evidence_key(evidence: dict) -> str:
    return str(evidence.get("chunk_id") or evidence.get("source") or evidence.get("text", "")[:80])


def fuse_row(text_row: dict | None, graph_row: dict, config: dict) -> dict:
    fusion = config.get("fusion", {})
    text_top_k = int(fusion.get("text_top_k", 3))
    graph_top_k = int(fusion.get("graph_top_k", 3))
    max_total = int(fusion.get("max_total_evidence", 6))
    max_chars = int(fusion.get("max_chars_per_evidence", 1400))

    candidates = []
    for doc in (text_row or {}).get("retrieved_context", [])[:text_top_k]:
        candidates.append(normalize_text_evidence(doc))
    for evidence in graph_row.get("top_evidence", [])[:graph_top_k]:
        candidates.append(normalize_graph_evidence(evidence))

    deduped = []
    seen = set()
    for evidence in candidates:
        key = evidence_key(evidence)
        if key in seen:
            continue
        seen.add(key)
        evidence["text"] = str(evidence.get("text", ""))[:max_chars]
        deduped.append(evidence)
        if len(deduped) >= max_total:
            break

    text_ids = [item["chunk_id"] for item in deduped if item.get("source_branch") == "text"]
    graph_ids = [item["chunk_id"] for item in deduped if item.get("source_branch") == "graph"]
    return {
        "ID": graph_row.get("ID"),
        "row_index": graph_row.get("row_index"),
        "key": graph_row.get("key", ""),
        "claim": graph_row.get("claim", ""),
        "label": graph_row.get("label", ""),
        "gold_relevant": graph_row.get("gold_relevant", ""),
        "facets": graph_row.get("facets", {}),
        "facet_matches": graph_row.get("facet_matches", []),
        "facet_match_summary": graph_row.get("facet_match_summary", {}),
        "evidence_summary": {
            "text_candidates": len((text_row or {}).get("retrieved_context", [])),
            "graph_candidates": len(graph_row.get("top_evidence", [])),
            "selected_text": len(text_ids),
            "selected_graph": len(graph_ids),
            "selected_total": len(deduped),
        },
        "top_evidence": deduped,
        "facet_summary_for_verifier": {
            **graph_row.get("facet_summary_for_verifier", {}),
            "text_chunk_ids": text_ids,
            "graph_chunk_ids": graph_ids,
            "fusion": "text_top_k+graph_top_k",
        },
    }


def build_report(rows: list[dict], missing_text: int) -> str:
    total = len(rows)
    with_evidence = sum(1 for row in rows if row.get("top_evidence"))
    branch_counts = Counter(
        evidence.get("source_branch", "unknown")
        for row in rows
        for evidence in row.get("top_evidence", [])
    )
    lines = [
        "# Hybrid FacetGraphRAG Fusion Report",
        "",
        f"- Rows: {total}",
        f"- Rows with evidence: {with_evidence}",
        f"- Missing text retrieval rows: {missing_text}",
        "",
        "| Evidence branch | Count |",
        "|---|---:|",
    ]
    for branch, count in branch_counts.most_common():
        lines.append(f"| {branch} | {count} |")
    return "\n".join(lines) + "\n"


def run_fuse(config: dict) -> list[dict]:
    text_rows = load_json(config["paths"]["text_retrieved"])
    graph_rows = load_json(config["paths"]["facet_reranked"])
    text_by_id = {str(row.get("ID")): row for row in text_rows}
    output = []
    missing_text = 0
    for graph_row in graph_rows:
        text_row = text_by_id.get(str(graph_row.get("ID")))
        if text_row is None:
            missing_text += 1
        output.append(fuse_row(text_row, graph_row, config))
    save_json(output, config["paths"]["hybrid_facet_reranked"])
    report_path = config["paths"].get("hybrid_fusion_report", "data/outputs/facet/hybrid_facet_fusion_report.md")
    save_text(build_report(output, missing_text), report_path)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Fuse text retrieval and FacetGraphRAG evidence.")
    parser.add_argument("--config", default="configs/facet/facet.yaml")
    args = parser.parse_args()
    config = load_yaml(args.config)
    rows = run_fuse(config)
    print(f"Saved {len(rows)} rows to {config['paths']['hybrid_facet_reranked']}")


if __name__ == "__main__":
    main()
