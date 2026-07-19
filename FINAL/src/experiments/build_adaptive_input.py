"""Adaptive fusion: gate the graph-evidence channel per claim.

Router (DETERMINISTIC, frozen a priori — same rule as the 2026-07-18 feasibility
study, no tuning against outcomes):
    ON  iff has_graph_evidence AND (
            missing_key_facet            # claim has time/place/result facet not
                                         #   covered by the text top-5
            OR facet_coverage < 0.8
            OR (rank_agreement < 0.4 AND graph_seedable))
    OFF -> evidence = text top-5 only (facets still shown to the verifier).

Usage:
  python3 -m src.experiments.build_adaptive_input \
    --fused data/outputs/facet/nokey-opt2-2000/hybrid_facet_reranked.json \
    --pool data/outputs/retrieved/hybrid_top20_nokey.json \
    --out data/outputs/facet/adaptive-2000/verify_input.json
"""
from __future__ import annotations

import argparse
import re
import unicodedata

from src.common.io import load_json, save_json

KEY_FACET_TYPES = {"time", "place", "result"}


def norm_tokens(text: str) -> set[str]:
    text = unicodedata.normalize("NFC", (text or "")).lower()
    return {t for t in re.findall(r"\w+", text) if len(t) >= 3}


def router_features(row: dict, pool_row: dict | None) -> dict:
    text_ev = [e for e in row.get("top_evidence", []) if e.get("source_branch") == "text"]
    graph_ev = [e for e in row.get("top_evidence", []) if e.get("source_branch") == "graph"]
    text_tokens = norm_tokens(" ".join(str(e.get("text", "")) for e in text_ev))

    values = [(ft, v) for ft, vals in (row.get("facets") or {}).items() for v in vals]
    covered = 0
    missing_key = False
    for ft, v in values:
        vt = norm_tokens(v)
        if vt and vt.issubset(text_tokens):
            covered += 1
        elif ft in KEY_FACET_TYPES:
            missing_key = True
    coverage = covered / len(values) if values else 1.0

    agreement = 1.0
    if pool_row:
        ctx = pool_row.get("retrieved_context", [])
        def top5(key):
            return {d.get("doc_id") for d in sorted(ctx, key=lambda d: float(d.get(key, 0) or 0), reverse=True)[:5]}
        agreement = len(top5("bm25_score") & top5("dense_score")) / 5.0 if ctx else 0.0

    seedable = sum(1 for fm in row.get("facet_matches", []) if fm.get("matched")) >= 2
    return {
        "facet_coverage": round(coverage, 3),
        "missing_key_facet": missing_key,
        "rank_agreement": round(agreement, 2),
        "graph_seedable": seedable,
        "has_graph_evidence": bool(graph_ev),
    }


def route_on(f: dict) -> bool:
    return f["has_graph_evidence"] and (
        f["missing_key_facet"]
        or f["facet_coverage"] < 0.8
        or (f["rank_agreement"] < 0.4 and f["graph_seedable"])
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fused", required=True)
    ap.add_argument("--pool", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    pool = {str(r.get("ID")): r for r in load_json(args.pool)}
    rows = load_json(args.fused)
    n_on = 0
    out = []
    for row in rows:
        feats = router_features(row, pool.get(str(row.get("ID"))))
        on = route_on(feats)
        new_row = dict(row)
        new_row["router"] = {**feats, "graph_activated": on}
        if not on:
            new_row["top_evidence"] = [
                e for e in row.get("top_evidence", []) if e.get("source_branch") == "text"
            ]
        out.append(new_row)
        n_on += on
    save_json(out, args.out)
    print(f"rows={len(out)}  router ON={n_on} ({100*n_on/len(out):.1f}%)  OFF={len(out)-n_on}")


if __name__ == "__main__":
    main()
