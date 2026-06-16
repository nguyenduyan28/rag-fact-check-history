import argparse
import re
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

from src.common.io import load_json, load_yaml, project_path, save_json
from src.common.normalize import normalize_text, tokenize


PAGE_RE = re.compile(r"_(\d+)(?:\.jpg)?\.txt$")


def resolve_device(device: str) -> str:
    if device != "auto":
        return device
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def extract_page(path: Path) -> int:
    match = PAGE_RE.search(path.name)
    return int(match.group(1)) if match else 0


def load_corpus(corpus_dir: str) -> list[dict]:
    documents = []
    for txt_file in sorted(project_path(corpus_dir).rglob("*.txt")):
        text = normalize_text(txt_file.read_text(encoding="utf-8", errors="ignore"))
        if not text:
            continue
        book = txt_file.parent.name
        doc_id = f"{book}/{txt_file.name}"
        documents.append(
            {
                "doc_id": doc_id,
                "book": book,
                "page": extract_page(txt_file),
                "source": str(txt_file.relative_to(project_path("."))),
                "text": text,
            }
        )
    return documents


def build_query(item: dict, query_fields: list[str]) -> str:
    return normalize_text(" ".join(str(item.get(field, "")) for field in query_fields))


def reciprocal_rank_fusion(rankings: list[list[int]], k: int) -> dict[int, float]:
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + rank + 1)
    return scores


def top_indices(scores: np.ndarray, top_k: int) -> list[int]:
    if len(scores) == 0:
        return []
    top_k = min(top_k, len(scores))
    return np.argsort(scores)[-top_k:][::-1].tolist()


def retrieve_all(config: dict) -> list[dict]:
    paths = config["paths"]
    retrieval = config["retrieval"]
    model_config = config["models"]

    documents = load_corpus(paths["corpus_dir"])
    if not documents:
        raise ValueError(f"No corpus .txt files found in {paths['corpus_dir']}")

    claims = load_json(paths["input_claims"])
    corpus_texts = [doc["text"] for doc in documents]

    print(f"Loaded {len(documents)} corpus chunks")
    print(f"Loaded {len(claims)} claims")

    tokenized_corpus = [tokenize(text) for text in corpus_texts]
    bm25 = BM25Okapi(tokenized_corpus)

    device = resolve_device(model_config.get("device", "auto"))
    print(f"Loading embedding model on {device}: {model_config['embedding']}")
    dense_model = SentenceTransformer(model_config["embedding"], device=device)
    corpus_embeddings = dense_model.encode(
        corpus_texts,
        normalize_embeddings=True,
        batch_size=32,
        show_progress_bar=True,
    )
    corpus_embeddings = np.asarray(corpus_embeddings)

    method = retrieval.get("method", "hybrid")
    query_fields = retrieval.get("query_fields", ["key", "claim"])
    final_top_k = retrieval["final_top_k"]

    output = []
    for item in tqdm(claims, desc="Retrieving"):
        query = build_query(item, query_fields)

        bm25_scores = np.asarray(bm25.get_scores(tokenize(query)))
        bm25_top = top_indices(bm25_scores, retrieval["bm25_top_k"])

        query_embedding = dense_model.encode(query, normalize_embeddings=True)
        dense_scores = np.asarray(query_embedding @ corpus_embeddings.T)
        dense_top = top_indices(dense_scores, retrieval["dense_top_k"])

        if method == "bm25":
            ranked = bm25_top[:final_top_k]
            fused_scores = {idx: float(bm25_scores[idx]) for idx in ranked}
        elif method == "dense":
            ranked = dense_top[:final_top_k]
            fused_scores = {idx: float(dense_scores[idx]) for idx in ranked}
        elif method == "hybrid":
            fused_scores = reciprocal_rank_fusion([bm25_top, dense_top], retrieval["rrf_k"])
            ranked = sorted(fused_scores, key=fused_scores.get, reverse=True)[:final_top_k]
        else:
            raise ValueError(f"Unsupported retrieval method: {method}")

        retrieved_context = []
        for rank, doc_idx in enumerate(ranked, start=1):
            doc = documents[doc_idx]
            retrieved_context.append(
                {
                    "rank": rank,
                    "doc_id": doc["doc_id"],
                    "book": doc["book"],
                    "page": doc["page"],
                    "source": doc["source"],
                    "score": fused_scores.get(doc_idx, 0.0),
                    "bm25_score": float(bm25_scores[doc_idx]),
                    "dense_score": float(dense_scores[doc_idx]),
                    "text": doc["text"],
                }
            )

        output.append(
            {
                "ID": item.get("ID"),
                "key": item.get("key", ""),
                "claim": item.get("claim", ""),
                "label": item.get("label", ""),
                "gold_relevant": item.get("relevant", ""),
                "query": query,
                "retrieved_context": retrieved_context,
            }
        )

    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Retrieve evidence for claim verification.")
    parser.add_argument("--config", default="configs/rag.yaml")
    args = parser.parse_args()

    config = load_yaml(args.config)
    output = retrieve_all(config)
    save_json(output, config["paths"]["output_retrieved"])
    print(f"Saved retrieved evidence to {config['paths']['output_retrieved']}")


if __name__ == "__main__":
    main()
