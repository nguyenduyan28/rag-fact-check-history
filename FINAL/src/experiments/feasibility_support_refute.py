"""Feasibility measurement for Claim-Conditioned Support-Refute Graph RAG.

Deterministic, NO API calls. Measures the funnel (router activation -> typed path
-> grounded -> claim-aligned -> replacement-eligible) and exports an audit sample
so support/refute precision can be hand-checked BEFORE spending any verifier request.

Runs on the already-seen dev claims (default: the balanced 2000) so the fresh test
set stays untouched.

Usage:
  python3 -m src.experiments.feasibility_support_refute \
    --config configs/facet/facet.yaml \
    --facet-matches data/outputs/facet/full-opt2/facet_matches.json \
    --text data/outputs/retrieved/hybrid_top20_nokey.json \
    --dev-ids data/outputs/facet/nokey-smoke-2000/verify/gemini-2.5-flash/facet_verified.json \
    --out-dir data/outputs/facet/feasibility \
    --audit-size 200
"""
from __future__ import annotations

import argparse
import json
import os
import re
import unicodedata
from collections import Counter, defaultdict

from src.common.io import load_json, load_yaml, save_json, save_text
from src.facet.graph_index import GraphIndex

TYPED_RELATIONS = {
    "PARTICIPATED_IN", "OCCURRED_AT", "LOCATED_IN",
    "CAUSES", "RESULTS_IN", "BEFORE", "AFTER",
}
SEQUENCE_RELATIONS = {"BEFORE", "AFTER"}
# key facet types whose absence in text should trigger the graph branch
KEY_FACET_TYPES = {"time", "place", "result"}


def norm_tokens(text: str) -> set[str]:
    text = unicodedata.normalize("NFC", (text or "")).lower()
    return {t for t in re.findall(r"\w+", text) if len(t) >= 3}


def years_in(text: str) -> set[str]:
    return set(re.findall(r"\b(1[0-9]{3}|20[0-2][0-9])\b", text or ""))


def build_edge_index(edges: list[dict]):
    """adjacency of typed edges: node -> list of (neighbor, type, edge)."""
    adj = defaultdict(list)
    typed_between = defaultdict(list)  # (u,v) undirected key -> edges
    for e in edges:
        if not isinstance(e, dict):
            continue
        t = e.get("type")
        if t not in TYPED_RELATIONS:
            continue
        u, v = e.get("source"), e.get("target")
        if not u or not v:
            continue
        adj[u].append((v, t, e))
        adj[v].append((u, t, e))
        typed_between[frozenset((u, v))].append(e)
    return adj, typed_between


def seed_nodes_for_claim(fm_row: dict):
    """node_id -> list of (facet_type, facet_value) from claim facet matches."""
    seeds = defaultdict(list)
    for fm in fm_row.get("facet_matches", []):
        for m in fm.get("matches", []):
            nid = m.get("node_id")
            if nid:
                seeds[nid].append((fm.get("facet_type"), fm.get("facet_value")))
    return seeds


def router_features(fm_row: dict, text_row: dict, seeds: dict) -> dict:
    ctx = (text_row or {}).get("retrieved_context", [])
    top5 = ctx[:5]
    top5_text = " ".join(str(d.get("text", "")) for d in top5)
    top5_tokens = norm_tokens(top5_text)

    # facet coverage: distinct facet values whose tokens appear in top-5 text
    all_vals = []
    for ftype, vals in fm_row.get("facets", {}).items():
        for v in vals:
            all_vals.append((ftype, v))
    covered = 0
    missing_key = False
    for ftype, v in all_vals:
        vt = norm_tokens(v)
        is_cov = bool(vt) and vt.issubset(top5_tokens)
        if is_cov:
            covered += 1
        elif ftype in KEY_FACET_TYPES:
            missing_key = True
    facet_coverage = covered / len(all_vals) if all_vals else 1.0

    # rank agreement: top-5 by bm25 vs top-5 by dense
    def top5_ids(scorekey):
        ranked = sorted(ctx, key=lambda d: float(d.get(scorekey, 0.0) or 0.0), reverse=True)[:5]
        return {d.get("doc_id") for d in ranked}
    bm, dn = top5_ids("bm25_score"), top5_ids("dense_score")
    rank_agreement = len(bm & dn) / 5.0 if ctx else 0.0

    # score gap top1/top2 (RRF score)
    scores = [float(d.get("score", 0.0) or 0.0) for d in ctx[:2]]
    score_gap = ((scores[0] - scores[1]) / scores[0]) if len(scores) == 2 and scores[0] else 0.0

    graph_seedable = len(seeds) >= 2

    return {
        "facet_coverage": facet_coverage,
        "rank_agreement": rank_agreement,
        "score_gap": score_gap,
        "missing_key_facet": missing_key,
        "graph_seedable": graph_seedable,
        "top3_doc_ids": [d.get("doc_id") for d in ctx[:3]],
    }


def route_decision(f: dict) -> bool:
    return bool(
        f["missing_key_facet"]
        or f["facet_coverage"] < 0.8
        or (f["rank_agreement"] < 0.4 and f["graph_seedable"])
    )


def find_typed_paths(seeds: dict, adj: dict, typed_between: dict, max_deg: int = 60):
    """Return list of path dicts connecting two claim-seed nodes (1-hop or 2-hop)."""
    seed_ids = list(seeds.keys())
    seed_set = set(seed_ids)
    paths = []

    # 1-hop: typed edge directly between two seeds
    for i in range(len(seed_ids)):
        for j in range(i + 1, len(seed_ids)):
            key = frozenset((seed_ids[i], seed_ids[j]))
            for e in typed_between.get(key, []):
                paths.append({"hops": 1, "edges": [e], "endpoints": (e["source"], e["target"])})

    # 2-hop: seed -> mid -> seed
    for u in seed_ids:
        neigh = adj.get(u, [])[:max_deg]
        for mid, t1, e1 in neigh:
            if mid in seed_set:
                continue
            for w, t2, e2 in adj.get(mid, [])[:max_deg]:
                if w in seed_set and w != u:
                    paths.append({"hops": 2, "edges": [e1, e2], "endpoints": (u, w)})
    return paths


def classify_path(path: dict, fm_row: dict, seeds: dict, chunk_years: dict) -> dict:
    """Conservative provisional label for hand audit: SUPPORT / EXPLICIT_REFUTE /
    POSSIBLE_CONFLICT / UNKNOWN. Structural detection only; precision is what we audit."""
    edges = path["edges"]
    rels = [e.get("type") for e in edges]
    grounded = all(bool(e.get("source_chunk")) and bool(e.get("evidence_text")) for e in edges)
    source_chunks = [e.get("source_chunk") for e in edges]

    claim_years = set()
    for v in fm_row.get("facets", {}).get("time", []):
        claim_years |= years_in(v)

    label = "UNKNOWN"
    reason = ""
    # sequence reversal candidate
    if any(r in SEQUENCE_RELATIONS for r in rels):
        label = "EXPLICIT_REFUTE?"
        reason = "sequence_relation_present (cần audit chiều BEFORE/AFTER vs claim)"
    # temporal conflict candidate: claim year vs years asserted in source chunk
    elif claim_years:
        src_years = set()
        for sc in source_chunks:
            src_years |= chunk_years.get(sc, set())
        if src_years and not (claim_years & src_years):
            label = "POSSIBLE_CONFLICT"
            reason = f"claim_years={sorted(claim_years)} vs source_years={sorted(src_years)}"
        elif claim_years & src_years:
            label = "SUPPORT"
            reason = "claim year present in source chunk"
        else:
            label = "SUPPORT" if grounded else "UNKNOWN"
            reason = "typed path between claim entities"
    else:
        label = "SUPPORT" if grounded else "UNKNOWN"
        reason = "typed path between claim entities (no time facet)"

    return {"label": label, "reason": reason, "grounded": grounded,
            "relations": rels, "source_chunks": source_chunks}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="configs/facet/facet.yaml")
    ap.add_argument("--facet-matches", required=True)
    ap.add_argument("--text", required=True, help="hybrid top-20 retrieval json")
    ap.add_argument("--dev-ids", required=True, help="verified json defining the claim set")
    ap.add_argument("--out-dir", default="data/outputs/facet/feasibility")
    ap.add_argument("--audit-size", type=int, default=200)
    args = ap.parse_args()

    config = load_yaml(args.config)
    gi = GraphIndex(config)  # loads nodes/edges/aliases/temporal
    adj, typed_between = build_edge_index(gi.edges)

    # chunk -> years (from corpus) for temporal conflict detection
    chunk_years = {}
    try:
        corpus = load_json(config["paths"].get("corpus_path", "data/outputs/corpus/chunks.json")) \
            if "corpus_path" in config.get("paths", {}) else load_json("data/outputs/corpus/chunks.json")
        for c in corpus:
            cid = c.get("chunk_id")
            if cid:
                chunk_years[cid] = {str(y) for y in c.get("year_mentions", [])}
    except Exception:
        pass

    fm_by_id = {str(r.get("ID")): r for r in load_json(args.facet_matches)}
    text_by_id = {str(r.get("ID")): r for r in load_json(args.text)}
    dev_ids = [str(r.get("ID")) for r in load_json(args.dev_ids) if r.get("ID") is not None]

    funnel = Counter()
    audit = []
    activation_reasons = Counter()
    n = 0
    for cid in dev_ids:
        fm_row = fm_by_id.get(cid)
        text_row = text_by_id.get(cid)
        if fm_row is None or text_row is None:
            continue
        n += 1
        seeds = seed_nodes_for_claim(fm_row)
        feats = router_features(fm_row, text_row, seeds)
        if not route_decision(feats):
            continue
        funnel["router_activated"] += 1

        paths = find_typed_paths(seeds, adj, typed_between)
        if not paths:
            continue
        funnel["typed_path_found"] += 1

        classified = [classify_path(p, fm_row, seeds, chunk_years) for p in paths]
        grounded_paths = [c for c in classified if c["grounded"]]
        if grounded_paths:
            funnel["grounded_path"] += 1
        # claim-aligned is by construction (endpoints are claim seeds); count non-redundant
        top3 = set(feats["top3_doc_ids"])
        eligible = [
            c for c in grounded_paths
            if c["label"] in ("SUPPORT", "EXPLICIT_REFUTE?", "POSSIBLE_CONFLICT")
            and not (set(c["source_chunks"]) & top3)
        ]
        if eligible:
            funnel["replacement_eligible"] += 1
            for c in eligible:
                activation_reasons[c["label"]] += 1

        if len(audit) < args.audit_size and grounded_paths:
            best = eligible[0] if eligible else grounded_paths[0]
            edge0 = paths[classified.index(best)]["edges"][0] if best in classified else paths[0]["edges"][0]
            audit.append({
                "ID": cid,
                "label_gold": fm_row.get("label"),
                "claim": fm_row.get("claim", "")[:300],
                "facets": {k: v for k, v in fm_row.get("facets", {}).items() if v},
                "router": {k: (round(v, 3) if isinstance(v, float) else v)
                           for k, v in feats.items() if k != "top3_doc_ids"},
                "path_label": best["label"],
                "path_reason": best["reason"],
                "relations": best["relations"],
                "source_chunks": best["source_chunks"],
                "evidence_text": [e.get("evidence_text", "")[:200] for e in
                                  (paths[classified.index(best)]["edges"] if best in classified else [])],
                "n_paths": len(paths),
            })

    os.makedirs(args.out_dir, exist_ok=True)
    save_json(audit, os.path.join(args.out_dir, "audit_sample.json"))

    def pct(a, b):
        return f"{100*a/b:.1f}%" if b else "n/a"

    activated = funnel["router_activated"]
    lines = [
        "# Feasibility — Support/Refute Graph RAG",
        "",
        f"- Claim set (dev, đã seen): {n}",
        f"- Router activated: {funnel['router_activated']} ({pct(funnel['router_activated'], n)})",
        "",
        "## Funnel (trên nhóm router bật)",
        "",
        "| Bước | Số claim | Tỉ lệ / activated |",
        "|---|---:|---:|",
        f"| Router activated | {activated} | 100% |",
        f"| Typed path found | {funnel['typed_path_found']} | {pct(funnel['typed_path_found'], activated)} |",
        f"| Grounded path | {funnel['grounded_path']} | {pct(funnel['grounded_path'], activated)} |",
        f"| Replacement-eligible | {funnel['replacement_eligible']} | {pct(funnel['replacement_eligible'], activated)} |",
        "",
        f"**valid_path_rate** (typed+grounded / activated) = {pct(funnel['grounded_path'], activated)}",
        f"**effective_replacement_rate** (eligible / toàn dev) = {pct(funnel['replacement_eligible'], n)}",
        "",
        "## Phân bố nhãn provisional (trên eligible paths, CẦN AUDIT TAY)",
        "",
        "| Nhãn | Count |",
        "|---|---:|",
    ]
    for lab, c in activation_reasons.most_common():
        lines.append(f"| {lab} | {c} |")
    lines += [
        "",
        f"Audit sample: {len(audit)} claim -> {os.path.join(args.out_dir, 'audit_sample.json')}",
        "",
        "## Go/No-Go (đối chiếu doc)",
        "- GO: typed-grounded-path-rate >= 20-30% (nhóm bật); replacement-eligible >= 5-10% (toàn dev);",
        "  precision support/refute thủ công >= 85%; RELATED_TO không dùng làm chứng cứ (đã loại).",
        "- NO-GO / sửa schema: đa số path vô nghĩa; precision refute thấp; graph lặp lại top text.",
        "",
        "**BƯỚC TIẾP: kiểm tra tay audit_sample.json để chấm precision nhãn SUPPORT / EXPLICIT_REFUTE? / POSSIBLE_CONFLICT trước khi quyết chạy verifier.**",
    ]
    save_text("\n".join(lines) + "\n", os.path.join(args.out_dir, "feasibility_report.md"))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
