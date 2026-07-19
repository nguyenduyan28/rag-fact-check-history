"""Compute gold-evidence hit rate on the full cleaned set (11,344 claims).

Metric (as described in Chapter 4): a passage contains the gold evidence when
>= 60% of the gold's content tokens (length >= 3, multiset counting) appear in
the passage. A claim is a hit when any selected passage passes the threshold.

Reports, for BM25/Dense/Hybrid top-5 and Facet Graph RAG top-8:
  - full-set hit rate
  - by-source-group breakdown (textbook-generated vs exam-derived)
  - structural-loss stats (best corpus-wide coverage for retrieval misses)

Usage: python -m src.experiments.gold_hit_rate
"""

import json
import re
import statistics
import unicodedata
from collections import Counter

BASE = "data/outputs"
FULL_FACET = f"{BASE}/facet/full-opt2/hybrid_facet_reranked.json"
CORPUS = f"{BASE}/corpus/chunks.json"
TEXT_RUNS = [
    ("Dense top-5", f"{BASE}/retrieved/dense_top5_nokey.json"),
    ("BM25 top-5", f"{BASE}/retrieved/bm25_top5_nokey.json"),
    ("Hybrid top-5", f"{BASE}/retrieved/hybrid_top5_nokey.json"),
]
THRESH = 0.6


def tokens(text: str):
    text = unicodedata.normalize("NFC", text.lower())
    return [t for t in re.findall(r"\w+", text) if len(t) >= 3]


def coverage(gold_counter: Counter, total: int, passage: str) -> float:
    p = Counter(tokens(passage))
    return sum(min(c, p[t]) for t, c in gold_counter.items()) / total


def is_hit(gold: str, passages) -> bool | None:
    g = Counter(tokens(gold))
    total = sum(g.values())
    if not total:
        return None
    return any(coverage(g, total, p) >= THRESH for p in passages if p)


def source_group(claim_id) -> str:
    cid = str(claim_id)
    return "exam" if ("His" in cid or "MET" in cid) else "generated"


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def report(name, rows, get_passages, full_ids):
    n = h = 0
    per_group = {"generated": [0, 0], "exam": [0, 0]}
    for r in rows:
        if full_ids is not None and str(r["ID"]) not in full_ids:
            continue
        hit = is_hit(r.get("gold_relevant", ""), get_passages(r))
        if hit is None:
            continue
        n += 1
        h += hit
        g = per_group[source_group(r["ID"])]
        g[0] += hit
        g[1] += 1
    print(f"{name:14s} full: {100 * h / n:5.1f}% ({h}/{n})  "
          + "  ".join(f"{k}: {100 * v[0] / v[1]:5.1f}%" for k, v in per_group.items()))


def main():
    full = load(FULL_FACET)
    full_ids = {str(r["ID"]) for r in full}

    text_passages = lambda r: [c.get("text", "") for c in r.get("retrieved_context", [])]
    facet_passages = lambda r: [c.get("text", "") for c in r.get("top_evidence", [])]

    for name, path in TEXT_RUNS:
        report(name, load(path), text_passages, full_ids)
    report("Facet top-8", full, facet_passages, None)

    # Structural loss: for facet misses, best coverage across the whole corpus
    corpus_tokens = [Counter(tokens(c.get("text", ""))) for c in load(CORPUS)]
    best_covs = []
    for r in full:
        gold = r.get("gold_relevant", "")
        if is_hit(gold, facet_passages(r)) is not False:
            continue
        g = Counter(tokens(gold))
        total = sum(g.values())
        best = max(sum(min(c, p[t]) for t, c in g.items()) / total for p in corpus_tokens)
        best_covs.append(best)
    structural = sum(1 for c in best_covs if c < THRESH)
    print(f"misses: {len(best_covs)} ({100 * len(best_covs) / len(full):.1f}% of full set)")
    print(f"structural (best corpus coverage < {THRESH}): {structural} "
          f"({100 * structural / len(full):.1f}% of full set); "
          f"median best coverage among misses: {statistics.median(best_covs):.2f}")


if __name__ == "__main__":
    main()
