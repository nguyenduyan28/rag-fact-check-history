from __future__ import annotations

import argparse
import math

from src.common.io import load_json, load_yaml, save_json
from src.common.normalize import extract_years, tokenize
from src.facet.normalize import normalize_key


try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover
    def tqdm(iterable, **_):
        return iterable


def text_overlap_score(claim: str, text: str) -> float:
    claim_tokens = {token for token in tokenize(claim) if len(token) >= 3}
    text_tokens = {token for token in tokenize(text) if len(token) >= 3}
    if not claim_tokens:
        return 0.0
    return len(claim_tokens & text_tokens) / len(claim_tokens)


def score_evidence(row: dict, evidence: dict, config: dict) -> dict:
    weights = config.get("rerank", {})
    total_facets = max(1, int(row.get("facet_match_summary", {}).get("total_facets", 0) or 0))
    facet_keys = {
        (hit.get("facet_type"), normalize_key(hit.get("facet_value", "")))
        for hit in evidence.get("facet_hits", [])
    }
    facet_coverage = len(facet_keys) / total_facets
    relation_score = min(1.0, math.log1p(len(evidence.get("relation_hits", []))) / math.log(4))
    claim_years = extract_years(row.get("claim", ""))
    evidence_years = set(evidence.get("years", []) or []) | extract_years(evidence.get("text", ""))
    temporal_score = (len(claim_years & evidence_years) / len(claim_years)) if claim_years else 0.0
    overlap = text_overlap_score(row.get("claim", ""), evidence.get("text", ""))
    score = (
        float(weights.get("facet_coverage_weight", 0.45)) * facet_coverage
        + float(weights.get("relation_weight", 0.25)) * relation_score
        + float(weights.get("temporal_weight", 0.20)) * temporal_score
        + float(weights.get("text_overlap_weight", 0.10)) * overlap
    )
    return {
        **evidence,
        "scores": {
            "final": score,
            "facet_coverage": facet_coverage,
            "relation": relation_score,
            "temporal": temporal_score,
            "text_overlap": overlap,
        },
    }


def rerank_row(row: dict, config: dict) -> dict:
    top_k = int(config.get("rerank", {}).get("top_k", 8))
    max_chars = int(config.get("evidence", {}).get("max_chunk_chars", 1400))
    scored = [score_evidence(row, evidence, config) for evidence in row.get("evidence", [])]
    scored.sort(key=lambda item: (-item["scores"]["final"], item["chunk_id"]))
    for item in scored:
        item["text"] = item.get("text", "")[:max_chars]
    matched_facets = row.get("facet_match_summary", {}).get("matched_facets", 0)
    total_facets = row.get("facet_match_summary", {}).get("total_facets", 0)
    return {
        "ID": row.get("ID"),
        "row_index": row.get("row_index"),
        "key": row.get("key", ""),
        "claim": row.get("claim", ""),
        "label": row.get("label", ""),
        "gold_relevant": row.get("gold_relevant", ""),
        "facets": row.get("facets", {}),
        "facet_matches": row.get("facet_matches", []),
        "facet_match_summary": row.get("facet_match_summary", {}),
        "evidence_summary": row.get("evidence_summary", {}),
        "top_evidence": scored[:top_k],
        "facet_summary_for_verifier": {
            "total_facets": total_facets,
            "matched_facets": matched_facets,
            "missing_facets": max(0, int(total_facets or 0) - int(matched_facets or 0)),
            "top_chunk_ids": [item["chunk_id"] for item in scored[:top_k]],
        },
    }


def run_rerank(config: dict) -> list[dict]:
    rows = load_json(config["paths"]["facet_evidence"])
    output = [rerank_row(row, config) for row in tqdm(rows, desc="Reranking evidence")]
    save_json(output, config["paths"]["facet_reranked"])
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Rerank facet evidence.")
    parser.add_argument("--config", default="configs/facet/facet.yaml")
    args = parser.parse_args()
    config = load_yaml(args.config)
    rows = run_rerank(config)
    print(f"Saved {len(rows)} rows to {config['paths']['facet_reranked']}")


if __name__ == "__main__":
    main()
