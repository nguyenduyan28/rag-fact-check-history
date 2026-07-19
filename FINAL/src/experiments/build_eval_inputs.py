"""Build verifier inputs for text-only and oracle ablations.

Reuses the exact claim IDs from an existing verified run so every ablation
is paired with the facet smoke runs. Output rows follow the same schema as
hybrid_facet_reranked.json, with empty facet fields (text/oracle evidence
carries no graph signals).

Usage:
  python3 -m src.experiments.build_eval_inputs \
    --retrieved data/outputs/retrieved/hybrid_top5_nokey.json \
    --ids-from data/outputs/facet/nokey-smoke-2000/verify/gemini-2.5-flash/facet_verified.json \
    --text-out data/outputs/facet/text-hybrid-2000/verify_input.json \
    --oracle-out data/outputs/facet/oracle-500/verify_input.json \
    --oracle-per-label 250 --top-k 5
"""
from __future__ import annotations

import argparse

from src.common.io import load_json, save_json


def text_evidence(doc: dict) -> dict:
    return {
        "chunk_id": doc.get("doc_id") or doc.get("source") or f"text_rank_{doc.get('rank')}",
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


def base_row(src: dict, row_index: int) -> dict:
    return {
        "ID": src.get("ID"),
        "row_index": row_index,
        "key": src.get("key", ""),
        "claim": src.get("claim", ""),
        "label": src.get("label", ""),
        "gold_relevant": src.get("gold_relevant", ""),
        "facets": {},
        "facet_matches": [],
        "facet_match_summary": {},
        "evidence_summary": {},
        "top_evidence": [],
        "facet_summary_for_verifier": {},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retrieved", required=True, help="Retrieval output JSON (claim-only queries).")
    parser.add_argument("--ids-from", required=True, help="Verified JSON whose claim IDs define the eval set.")
    parser.add_argument("--text-out", default=None, help="Output path for the text-only verifier input.")
    parser.add_argument("--oracle-out", default=None, help="Output path for the oracle verifier input.")
    parser.add_argument("--oracle-per-label", type=int, default=250)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    verified = load_json(args.ids_from)
    ordered_ids = [
        (int(row.get("row_index", 0) or 0), str(row.get("ID")))
        for row in verified
        if row.get("ID") is not None
    ]
    ordered_ids.sort()

    retrieved_by_id = {str(row.get("ID")): row for row in load_json(args.retrieved)}
    missing = [claim_id for _, claim_id in ordered_ids if claim_id not in retrieved_by_id]
    if missing:
        raise SystemExit(f"{len(missing)} IDs missing from retrieval file, e.g. {missing[:5]}")

    if args.text_out:
        rows = []
        for row_index, claim_id in ordered_ids:
            src = retrieved_by_id[claim_id]
            row = base_row(src, row_index)
            row["top_evidence"] = [text_evidence(doc) for doc in src.get("retrieved_context", [])[: args.top_k]]
            row["evidence_summary"] = {"selected_text": len(row["top_evidence"]), "selected_graph": 0}
            rows.append(row)
        save_json(rows, args.text_out)
        print(f"text input: {len(rows)} rows -> {args.text_out}")

    if args.oracle_out:
        rows = []
        counts = {"real": 0, "fake": 0}
        for row_index, claim_id in ordered_ids:
            src = retrieved_by_id[claim_id]
            label = src.get("label", "")
            if counts.get(label, args.oracle_per_label) >= args.oracle_per_label:
                continue
            counts[label] += 1
            row = base_row(src, row_index)
            row["top_evidence"] = [
                {
                    "chunk_id": "gold_evidence",
                    "source_branch": "oracle",
                    "book": "gold",
                    "chapter": None,
                    "section": "gold_relevant",
                    "pages": [],
                    "years": [],
                    "text": src.get("gold_relevant", ""),
                    "facet_hits": [],
                    "relation_hits": [],
                    "node_ids": [],
                    "scores": {"final": 1.0},
                }
            ]
            row["evidence_summary"] = {"selected_text": 0, "selected_graph": 0, "oracle": 1}
            rows.append(row)
        save_json(rows, args.oracle_out)
        print(f"oracle input: {len(rows)} rows ({counts}) -> {args.oracle_out}")


if __name__ == "__main__":
    main()
