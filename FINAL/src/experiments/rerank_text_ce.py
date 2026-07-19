"""Cross-encoder reranking for text retrieval candidates.

Reads a retrieval file whose retrieved_context holds a wide candidate pool
(e.g. top-20 from BM25+dense RRF), rescores every (claim, chunk) pair with a
cross-encoder (default BAAI/bge-reranker-v2-m3, local GPU), and writes the
same schema with retrieved_context replaced by the CE top-k.

Chunks are cropped to the claim-relevant window before scoring so the pair
fits the CE context without losing the decisive sentence.

Usage:
  python3 -m src.experiments.rerank_text_ce \
    --input data/outputs/retrieved/hybrid_top20_nokey.json \
    --output data/outputs/retrieved/hybrid_top5_ce_nokey.json \
    --top-k 5 --batch-size 64
"""
from __future__ import annotations

import argparse

from src.common.io import load_json, save_json
from src.facet.verify_facet import crop_text_to_claim

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover
    def tqdm(iterable, **_):
        return iterable


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", default="BAAI/bge-reranker-v2-m3")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--max-chars", type=int, default=1200, help="Crop chunk to this window before scoring.")
    parser.add_argument("--max-length", type=int, default=512, help="CE tokenizer max length.")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--device", default=None, help="cuda/cpu; default auto.")
    args = parser.parse_args()

    from sentence_transformers import CrossEncoder

    rows = load_json(args.input)
    pairs = []
    index = []  # (row_idx, doc_idx)
    for row_idx, row in enumerate(rows):
        claim = str(row.get("claim", ""))
        for doc_idx, doc in enumerate(row.get("retrieved_context", [])):
            cropped = crop_text_to_claim(str(doc.get("text", "")), claim, args.max_chars)
            pairs.append((claim, cropped))
            index.append((row_idx, doc_idx))
    print(f"Scoring {len(pairs)} (claim, chunk) pairs from {len(rows)} claims")

    model = CrossEncoder(args.model, max_length=args.max_length, device=args.device)
    scores = model.predict(pairs, batch_size=args.batch_size, show_progress_bar=True)

    by_row: dict[int, list[tuple[float, int]]] = {}
    for (row_idx, doc_idx), score in zip(index, scores):
        by_row.setdefault(row_idx, []).append((float(score), doc_idx))

    kept_total = 0
    for row_idx, row in enumerate(tqdm(rows, desc="Selecting CE top-k")):
        docs = row.get("retrieved_context", [])
        ranked = sorted(by_row.get(row_idx, []), key=lambda item: (-item[0], item[1]))
        selected = []
        for rank, (score, doc_idx) in enumerate(ranked[: args.top_k], start=1):
            doc = dict(docs[doc_idx])
            doc["ce_score"] = score
            doc["retrieval_rank"] = doc.get("rank")
            doc["rank"] = rank
            selected.append(doc)
        row["retrieved_context"] = selected
        kept_total += len(selected)

    save_json(rows, args.output)
    print(f"Saved {len(rows)} rows ({kept_total} chunks) to {args.output}")


if __name__ == "__main__":
    main()
