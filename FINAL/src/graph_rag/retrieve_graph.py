"""Retrieve source-grounded graph evidence for parsed claims."""

from __future__ import annotations

import argparse
import re
import unicodedata
from collections import Counter, defaultdict
from typing import Any

from src.common.io import load_json, load_yaml, save_json, save_text
from src.common.normalize import normalize_text

np = None

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover - keep CLI usable without optional progress bar.

    def tqdm(iterable, **_: Any):
        return iterable


STOPWORDS = {
    "a",
    "ai",
    "anh",
    "bà",
    "bài",
    "bị",
    "bộ",
    "bởi",
    "các",
    "cái",
    "cần",
    "có",
    "còn",
    "của",
    "cùng",
    "đã",
    "đang",
    "đây",
    "để",
    "đến",
    "đều",
    "đi",
    "đó",
    "được",
    "gì",
    "hay",
    "hơn",
    "khi",
    "là",
    "lại",
    "làm",
    "lên",
    "mà",
    "một",
    "này",
    "năm",
    "nên",
    "nếu",
    "người",
    "như",
    "những",
    "ở",
    "ra",
    "rằng",
    "sau",
    "sẽ",
    "so",
    "sự",
    "tại",
    "theo",
    "thì",
    "trong",
    "trên",
    "trước",
    "từ",
    "và",
    "vào",
    "về",
    "vì",
    "với",
    "cho",
    "chủ",
    "yếu",
    "nhiều",
    "không",
    "thành",
    "phần",
}


def as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def get_numpy():
    global np
    if np is None:
        try:
            import numpy as np_module
        except ImportError as exc:  # pragma: no cover - runtime dependency guard.
            raise RuntimeError(
                "Embedding graph retrieval requires numpy. Install requirements.txt first."
            ) from exc
        np = np_module
    return np


def normalize_key(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "").lower()
    text = re.sub(r"[\W_]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def token_set(text: str) -> set[str]:
    tokens = set()
    for token in normalize_key(text).split():
        if len(token) < 3 or token in STOPWORDS or token.isdigit():
            continue
        tokens.add(token)
    return tokens


def item_years(index: dict, kind: str, item_id: str) -> list[int]:
    key = f"{kind}_to_years"
    years = index.get(key, {}).get(item_id, [])
    return sorted(year for year in years if isinstance(year, int))


def node_label(node: dict | None) -> dict:
    if not node:
        return {"id": "", "type": "", "name": ""}
    return {
        "id": node.get("id", ""),
        "type": node.get("type", ""),
        "name": node.get("name", ""),
    }


def edge_search_text(edge: dict, nodes_by_id: dict[str, dict]) -> str:
    source = nodes_by_id.get(edge.get("source", ""), {})
    target = nodes_by_id.get(edge.get("target", ""), {})
    return " ".join(
        normalize_text(str(value))
        for value in [
            edge.get("type", ""),
            edge.get("description", ""),
            edge.get("evidence_text", ""),
            source.get("name", ""),
            source.get("description", ""),
            target.get("name", ""),
            target.get("description", ""),
        ]
    )


def chunk_search_text(chunk: dict) -> str:
    return " ".join(
        normalize_text(str(value))
        for value in [
            chunk.get("book", ""),
            chunk.get("chapter", ""),
            chunk.get("section", ""),
            chunk.get("text", ""),
            chunk.get("contextual_text", ""),
        ]
    )


def node_search_text(node: dict) -> str:
    return " ".join(
        normalize_text(str(value))
        for value in [
            node.get("type", ""),
            node.get("name", ""),
            " ".join(as_list(node.get("aliases"))),
            node.get("description", ""),
            " ".join(as_list(node.get("description_samples"))[:3]),
            " ".join(as_list(node.get("evidence_samples"))[:3]),
            " ".join(str(year) for year in as_list(node.get("years"))),
        ]
    )


def build_indexes(
    nodes: list[dict], edges: list[dict], chunks: list[dict], temporal_index: dict
) -> dict:
    nodes_by_id = {node["id"]: node for node in nodes if node.get("id")}
    edges_by_id = {edge["id"]: edge for edge in edges if edge.get("id")}
    chunks_by_id = {
        chunk["chunk_id"]: chunk for chunk in chunks if chunk.get("chunk_id")
    }
    incident_edges: dict[str, list[str]] = defaultdict(list)
    relation_incident_edges: dict[str, list[str]] = defaultdict(list)
    source_chunk_edges: dict[str, list[str]] = defaultdict(list)
    relation_degrees: Counter = Counter()

    edge_texts = {}
    edge_match_texts = {}
    edge_tokens = {}
    edge_years = {}
    token_to_edges: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        edge_id = edge.get("id")
        if not edge_id:
            continue
        source = edge.get("source")
        target = edge.get("target")
        if source:
            incident_edges[source].append(edge_id)
        if target:
            incident_edges[target].append(edge_id)
        if edge.get("source_chunk"):
            source_chunk_edges[edge["source_chunk"]].append(edge_id)
        source_node = nodes_by_id.get(source, {})
        target_node = nodes_by_id.get(target, {})
        is_relation_edge = (
            edge.get("type") != "MENTIONS"
            and source_node.get("type") != "DocumentChunk"
            and target_node.get("type") != "DocumentChunk"
        )
        if is_relation_edge:
            if source:
                relation_incident_edges[source].append(edge_id)
                relation_degrees[source] += 1
            if target:
                relation_incident_edges[target].append(edge_id)
                relation_degrees[target] += 1
        search_text = edge_search_text(edge, nodes_by_id)
        edge_texts[edge_id] = search_text
        edge_match_texts[edge_id] = f" {normalize_key(search_text)} "
        tokens = token_set(search_text)
        edge_tokens[edge_id] = tokens
        edge_years[edge_id] = set(item_years(temporal_index, "edge", edge_id))
        for token in tokens:
            token_to_edges[token].append(edge_id)

    chunk_texts = {}
    chunk_match_texts = {}
    chunk_tokens = {}
    chunk_years = {}
    token_to_chunks: dict[str, list[str]] = defaultdict(list)
    for chunk in chunks:
        chunk_id = chunk.get("chunk_id")
        if not chunk_id:
            continue
        search_text = chunk_search_text(chunk)
        chunk_texts[chunk_id] = search_text
        chunk_match_texts[chunk_id] = f" {normalize_key(search_text)} "
        tokens = token_set(search_text)
        chunk_tokens[chunk_id] = tokens
        chunk_years[chunk_id] = set(item_years(temporal_index, "chunk", chunk_id))
        for token in tokens:
            token_to_chunks[token].append(chunk_id)

    node_to_chunks: dict[str, set[str]] = defaultdict(set)
    for node in nodes:
        node_id = node.get("id")
        if not node_id:
            continue
        for chunk_id in as_list(node.get("source_chunks")):
            node_to_chunks[node_id].add(chunk_id)
    for edge in edges:
        if (
            edge.get("type") == "MENTIONS"
            and edge.get("target")
            and edge.get("source_chunk")
        ):
            node_to_chunks[edge["target"]].add(edge["source_chunk"])

    return {
        "nodes_by_id": nodes_by_id,
        "edges_by_id": edges_by_id,
        "chunks_by_id": chunks_by_id,
        "incident_edges": incident_edges,
        "relation_incident_edges": relation_incident_edges,
        "relation_degrees": relation_degrees,
        "source_chunk_edges": source_chunk_edges,
        "edge_texts": edge_texts,
        "edge_match_texts": edge_match_texts,
        "edge_tokens": edge_tokens,
        "edge_years": edge_years,
        "token_to_edges": token_to_edges,
        "chunk_texts": chunk_texts,
        "chunk_match_texts": chunk_match_texts,
        "chunk_tokens": chunk_tokens,
        "chunk_years": chunk_years,
        "token_to_chunks": token_to_chunks,
        "node_to_chunks": node_to_chunks,
        "temporal_index": temporal_index,
    }


def claim_keywords(claim: dict) -> list[str]:
    llm_parse = (
        claim.get("llm_parse", {}) if isinstance(claim.get("llm_parse"), dict) else {}
    )
    phrases = []
    for value in as_list(llm_parse.get("keywords")):
        if isinstance(value, str) and value.strip():
            phrases.append(value.strip())
    for mention in as_list(llm_parse.get("event_mentions")) + as_list(
        llm_parse.get("entity_mentions")
    ):
        if isinstance(mention, dict) and mention.get("text"):
            phrases.append(str(mention["text"]).strip())
    for match in as_list(claim.get("alias_matches")):
        if match.get("canonical_name"):
            phrases.append(str(match["canonical_name"]).strip())
        if match.get("matched_alias"):
            phrases.append(str(match["matched_alias"]).strip())

    seen = set()
    deduped = []
    for phrase in phrases:
        key = normalize_key(phrase)
        if key and key not in seen:
            seen.add(key)
            deduped.append(phrase)
    return deduped


def relation_types(claim: dict) -> set[str]:
    llm_parse = (
        claim.get("llm_parse", {}) if isinstance(claim.get("llm_parse"), dict) else {}
    )
    types = set()
    for relation in as_list(llm_parse.get("relation_hints")):
        if isinstance(relation, dict) and relation.get("relation"):
            types.add(str(relation["relation"]).strip())
    return types


def phrase_hits(phrases: list[str], text: str) -> int:
    normalized = f" {normalize_key(text)} "
    hits = 0
    for phrase in phrases:
        key = normalize_key(phrase)
        if len(key) >= 4 and f" {key} " in normalized:
            hits += 1
    return hits


def normalized_phrase_keys(phrases: list[str]) -> list[str]:
    seen = set()
    keys = []
    for phrase in phrases:
        key = normalize_key(phrase)
        if len(key) >= 4 and key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def phrase_key_hits(phrase_keys: list[str], normalized_text: str) -> int:
    return sum(1 for key in phrase_keys if f" {key} " in normalized_text)


def sorted_limited_token_ids(
    tokens: set[str],
    token_index: dict[str, list[str]],
    token_limit: int,
    per_token_limit: int,
) -> list[str]:
    selected_tokens = sorted(
        (token for token in tokens if token in token_index),
        key=lambda token: (len(token_index[token]), token),
    )[:token_limit]
    ids = []
    seen = set()
    for token in selected_tokens:
        for item_id in token_index[token][:per_token_limit]:
            if item_id not in seen:
                seen.add(item_id)
                ids.append(item_id)
    return ids


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


def top_indices(scores: np.ndarray, top_k: int) -> list[int]:
    np_module = get_numpy()
    if len(scores) == 0 or top_k <= 0:
        return []
    top_k = min(top_k, len(scores))
    return np_module.argsort(scores)[-top_k:][::-1].tolist()


def claim_query_text(claim: dict) -> str:
    llm_parse = (
        claim.get("llm_parse", {}) if isinstance(claim.get("llm_parse"), dict) else {}
    )
    parts = [claim.get("claim", ""), claim.get("query", "")]
    parts.extend(claim_keywords(claim))
    for relation in as_list(llm_parse.get("relation_hints")):
        if isinstance(relation, dict):
            parts.extend(
                [
                    relation.get("source", ""),
                    relation.get("relation", ""),
                    relation.get("target", ""),
                    relation.get("evidence_text", ""),
                ]
            )
    for match in as_list(claim.get("alias_matches")):
        if isinstance(match, dict):
            parts.extend(
                [
                    match.get("canonical_name", ""),
                    match.get("matched_alias", ""),
                    match.get("canonical_type", ""),
                ]
            )
    parts.extend(str(year) for year in as_list(claim.get("years")))
    return normalize_text(" ".join(str(part) for part in parts if part))


def build_embedding_index(
    nodes: list[dict],
    edges: list[dict],
    chunks: list[dict],
    indexes: dict,
    config: dict,
) -> dict:
    np_module = get_numpy()
    retrieval_config = config.get("graph_retrieval", {})
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:  # pragma: no cover - runtime dependency guard.
        raise RuntimeError(
            "Embedding graph retrieval requires sentence-transformers. Install requirements.txt first."
        ) from exc

    model_name = (
        retrieval_config.get("embedding_model")
        or config.get("models", {}).get("embedding")
        or "BAAI/bge-m3"
    )
    device = resolve_device(
        retrieval_config.get("device") or config.get("models", {}).get("device", "auto")
    )
    batch_size = int(retrieval_config.get("embedding_batch_size", 32))
    include_mentions = bool(retrieval_config.get("include_mention_edges", False))

    node_ids = [
        node["id"]
        for node in nodes
        if node.get("id") and node.get("type") != "DocumentChunk"
    ]
    node_texts = [
        node_search_text(indexes["nodes_by_id"][node_id]) for node_id in node_ids
    ]
    edge_ids = [
        edge["id"]
        for edge in edges
        if edge.get("id") and (include_mentions or edge.get("type") != "MENTIONS")
    ]
    edge_texts = [
        edge_search_text(indexes["edges_by_id"][edge_id], indexes["nodes_by_id"])
        for edge_id in edge_ids
    ]
    chunk_ids = [chunk["chunk_id"] for chunk in chunks if chunk.get("chunk_id")]
    chunk_texts = [
        chunk_search_text(indexes["chunks_by_id"][chunk_id]) for chunk_id in chunk_ids
    ]

    print(f"Loading embedding model on {device}: {model_name}")
    model = SentenceTransformer(model_name, device=device)
    print(
        f"Encoding graph index: {len(node_ids)} nodes, {len(edge_ids)} edges, {len(chunk_ids)} chunks"
    )
    node_embeddings = np_module.asarray(
        model.encode(
            node_texts,
            normalize_embeddings=True,
            batch_size=batch_size,
            show_progress_bar=True,
        )
    )
    edge_embeddings = np_module.asarray(
        model.encode(
            edge_texts,
            normalize_embeddings=True,
            batch_size=batch_size,
            show_progress_bar=True,
        )
    )
    chunk_embeddings = np_module.asarray(
        model.encode(
            chunk_texts,
            normalize_embeddings=True,
            batch_size=batch_size,
            show_progress_bar=True,
        )
    )

    return {
        "model": model,
        "batch_size": batch_size,
        "node_ids": node_ids,
        "edge_ids": edge_ids,
        "chunk_ids": chunk_ids,
        "node_embeddings": node_embeddings,
        "edge_embeddings": edge_embeddings,
        "chunk_embeddings": chunk_embeddings,
    }


def score_arrays(
    query_embedding: np.ndarray, embedding_index: dict
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    np_module = get_numpy()
    return (
        np_module.asarray(query_embedding @ embedding_index["node_embeddings"].T),
        np_module.asarray(query_embedding @ embedding_index["edge_embeddings"].T),
        np_module.asarray(query_embedding @ embedding_index["chunk_embeddings"].T),
    )


def dense_score_maps(
    embedding_index: dict,
    node_scores: np.ndarray,
    edge_scores: np.ndarray,
    chunk_scores: np.ndarray,
) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    return (
        {
            node_id: float(node_scores[index])
            for index, node_id in enumerate(embedding_index["node_ids"])
        },
        {
            edge_id: float(edge_scores[index])
            for index, edge_id in enumerate(embedding_index["edge_ids"])
        },
        {
            chunk_id: float(chunk_scores[index])
            for index, chunk_id in enumerate(embedding_index["chunk_ids"])
        },
    )


def edge_other_node(edge: dict, node_id: str) -> str:
    if edge.get("source") == node_id:
        return edge.get("target", "")
    if edge.get("target") == node_id:
        return edge.get("source", "")
    return ""


def relation_step_score(
    edge_id: str,
    next_node_id: str,
    claim: dict,
    indexes: dict,
    query_tokens: set[str],
    relation_type_set: set[str],
    node_dense: dict[str, float],
    edge_dense: dict[str, float],
    config: dict,
    depth: int,
) -> float:
    retrieval_config = config.get("graph_retrieval", {})
    edge = indexes["edges_by_id"].get(edge_id, {})
    score = max(0.0, edge_dense.get(edge_id, 0.0))
    score += max(0.0, node_dense.get(next_node_id, 0.0)) * 0.25
    score += min(
        0.6, len(query_tokens & indexes["edge_tokens"].get(edge_id, set())) * 0.08
    )
    if edge.get("type") in relation_type_set:
        score += 0.3
    claim_years = set(
        year for year in as_list(claim.get("years")) if isinstance(year, int)
    )
    if claim_years & indexes["edge_years"].get(edge_id, set()):
        score += 0.25
    degree = indexes["relation_degrees"].get(next_node_id, 0)
    max_expand_degree = max(1, int(retrieval_config.get("max_expand_degree", 80)))
    score -= float(retrieval_config.get("hub_penalty", 0.15)) * min(
        1.0, degree / max_expand_degree
    )
    score -= float(retrieval_config.get("hop_decay", 0.2)) * depth
    return score


def find_multihop_paths(
    seed_nodes: set[str],
    claim: dict,
    indexes: dict,
    config: dict,
    node_dense: dict[str, float],
    edge_dense: dict[str, float],
    query_tokens: set[str],
    relation_type_set: set[str],
) -> tuple[list[dict], Counter]:
    retrieval_config = config.get("graph_retrieval", {})
    max_hops = max(1, int(retrieval_config.get("max_hops", 2)))
    beam_size = max(1, int(retrieval_config.get("beam_size", 20)))
    top_neighbors = max(1, int(retrieval_config.get("top_neighbors_per_node", 20)))
    max_expand_degree = max(1, int(retrieval_config.get("max_expand_degree", 80)))
    max_seed_nodes = max(1, int(retrieval_config.get("max_seed_nodes", 80)))
    reasons: Counter = Counter()
    selected_seeds = sorted(
        seed_nodes, key=lambda node_id: (-node_dense.get(node_id, 0.0), node_id)
    )[:max_seed_nodes]
    paths = []

    for seed_id in selected_seeds:
        beam = [([seed_id], [], 0.0)]
        for depth in range(1, max_hops + 1):
            expanded = []
            for node_path, edge_path, base_score in beam:
                current_node = node_path[-1]
                incident = list(
                    indexes["relation_incident_edges"].get(current_node, [])
                )
                incident.sort(
                    key=lambda edge_id: (-edge_dense.get(edge_id, 0.0), edge_id)
                )
                if len(incident) > max_expand_degree:
                    incident = incident[:max_expand_degree]
                    reasons["hub_expansion_truncated"] += 1
                for edge_id in incident[:top_neighbors]:
                    edge = indexes["edges_by_id"].get(edge_id, {})
                    next_node = edge_other_node(edge, current_node)
                    if not next_node or next_node in node_path:
                        continue
                    step_score = relation_step_score(
                        edge_id,
                        next_node,
                        claim,
                        indexes,
                        query_tokens,
                        relation_type_set,
                        node_dense,
                        edge_dense,
                        config,
                        depth,
                    )
                    new_score = base_score + step_score
                    new_node_path = node_path + [next_node]
                    new_edge_path = edge_path + [edge_id]
                    expanded.append((new_node_path, new_edge_path, new_score))
                    paths.append(
                        {
                            "path_id": f"path_{len(paths) + 1}",
                            "score": round(new_score, 4),
                            "hop_count": len(new_edge_path),
                            "nodes": new_node_path,
                            "edges": new_edge_path,
                        }
                    )
                    reasons[f"path_{len(new_edge_path)}hop"] += 1
            expanded.sort(key=lambda item: (-item[2], item[1]))
            beam = expanded[:beam_size]
            if not beam:
                break

    paths.sort(key=lambda path: (-path["score"], path["edges"]))
    return paths, reasons


def path_support_scores(paths: list[dict], top_paths: int) -> dict[str, float]:
    support: dict[str, float] = defaultdict(float)
    for path in paths[:top_paths]:
        hop_count = max(1, int(path.get("hop_count", 1)))
        contribution = float(path.get("score", 0.0) or 0.0) / hop_count
        for edge_id in as_list(path.get("edges")):
            support[edge_id] = max(support[edge_id], contribution)
    return support


def cheap_edge_score(
    edge_id: str,
    claim: dict,
    indexes: dict,
    query_tokens: set[str],
    relation_type_set: set[str],
) -> float:
    edge = indexes["edges_by_id"][edge_id]
    matched_nodes = {
        match.get("entity_id")
        for match in as_list(claim.get("alias_matches"))
        if match.get("entity_id")
    }
    claim_years = set(
        year for year in as_list(claim.get("years")) if isinstance(year, int)
    )
    chunk_id = edge.get("source_chunk", "")
    score = 0.0
    score += (
        int(edge.get("source") in matched_nodes)
        + int(edge.get("target") in matched_nodes)
    ) * 6.0
    score += len(claim_years & indexes["edge_years"].get(edge_id, set())) * 3.0
    score += len(claim_years & indexes["chunk_years"].get(chunk_id, set())) * 2.0
    score += min(
        6.0, len(query_tokens & indexes["edge_tokens"].get(edge_id, set())) * 0.6
    )
    if edge.get("type") in relation_type_set:
        score += 3.0
    return score


def cheap_chunk_score(
    chunk_id: str,
    claim: dict,
    fact_scores_by_chunk: dict[str, float],
    indexes: dict,
    query_tokens: set[str],
) -> float:
    claim_years = set(
        year for year in as_list(claim.get("years")) if isinstance(year, int)
    )
    score = min(12.0, fact_scores_by_chunk.get(chunk_id, 0.0) * 0.6)
    score += len(claim_years & indexes["chunk_years"].get(chunk_id, set())) * 2.0
    score += min(
        8.0, len(query_tokens & indexes["chunk_tokens"].get(chunk_id, set())) * 0.4
    )
    for match in as_list(claim.get("alias_matches")):
        node_id = match.get("entity_id")
        if node_id and chunk_id in indexes["node_to_chunks"].get(node_id, set()):
            score += 2.0
    return score


def collect_candidate_edges(
    claim: dict, indexes: dict, config: dict
) -> tuple[set[str], Counter]:
    retrieval_config = config.get("graph_retrieval", {})
    temporal_index = indexes["temporal_index"]
    candidate_edges: set[str] = set()
    reasons: Counter = Counter()

    matched_nodes = {
        match.get("entity_id")
        for match in as_list(claim.get("alias_matches"))
        if match.get("entity_id") in indexes["nodes_by_id"]
    }
    for node_id in matched_nodes:
        for edge_id in indexes["incident_edges"].get(node_id, []):
            candidate_edges.add(edge_id)
            reasons["entity_1hop"] += 1

    for year in as_list(claim.get("years")):
        year_key = str(year)
        for edge_id in temporal_index.get("year_to_edges", {}).get(year_key, []):
            candidate_edges.add(edge_id)
            reasons["year_edge"] += 1
        for node_id in temporal_index.get("year_to_nodes", {}).get(year_key, []):
            for edge_id in indexes["incident_edges"].get(node_id, []):
                candidate_edges.add(edge_id)
                reasons["year_node_1hop"] += 1
        for chunk_id in temporal_index.get("year_to_chunks", {}).get(year_key, []):
            for edge_id in indexes["source_chunk_edges"].get(chunk_id, []):
                candidate_edges.add(edge_id)
                reasons["year_chunk_edge"] += 1

    keywords = claim_keywords(claim)
    query_tokens = token_set(" ".join([claim.get("query", ""), " ".join(keywords)]))
    for edge_id in sorted_limited_token_ids(
        query_tokens,
        indexes["token_to_edges"],
        int(retrieval_config.get("keyword_edge_token_limit", 20)),
        int(retrieval_config.get("max_token_edges", 500)),
    ):
        candidate_edges.add(edge_id)
        reasons["keyword_edge"] += 1

    return candidate_edges, reasons


def score_edge(
    edge_id: str,
    claim: dict,
    indexes: dict,
    phrase_keys: list[str],
    query_tokens: set[str],
    relation_type_set: set[str],
) -> tuple[float, dict]:
    edge = indexes["edges_by_id"][edge_id]
    edge_tokens = indexes["edge_tokens"].get(edge_id, set())
    matched_nodes = {
        match.get("entity_id")
        for match in as_list(claim.get("alias_matches"))
        if match.get("entity_id")
    }
    claim_years = set(
        year for year in as_list(claim.get("years")) if isinstance(year, int)
    )
    edge_years = indexes["edge_years"].get(edge_id, set())
    chunk_years = indexes["chunk_years"].get(edge.get("source_chunk", ""), set())
    endpoint_matches = int(edge.get("source") in matched_nodes) + int(
        edge.get("target") in matched_nodes
    )
    year_overlap = claim_years & edge_years
    chunk_year_overlap = claim_years & chunk_years
    keyword_overlap = query_tokens & edge_tokens
    phrase_count = phrase_key_hits(
        phrase_keys, indexes["edge_match_texts"].get(edge_id, "")
    )
    relation_match = edge.get("type") in relation_type_set
    source = indexes["nodes_by_id"].get(edge.get("source", ""), {})
    target = indexes["nodes_by_id"].get(edge.get("target", ""), {})
    type_match = any(
        match.get("canonical_type") in {source.get("type"), target.get("type")}
        for match in as_list(claim.get("alias_matches"))
    )

    breakdown = {
        "entity_endpoint": endpoint_matches * 6.0,
        "edge_year_overlap": len(year_overlap) * 3.0,
        "source_chunk_year_overlap": len(chunk_year_overlap) * 2.0,
        "keyword_overlap": min(6.0, len(keyword_overlap) * 0.6),
        "keyword_phrase": min(6.0, phrase_count * 2.0),
        "relation_type": 3.0 if relation_match else 0.0,
        "node_type": 1.0 if type_match else 0.0,
        "confidence": min(1.0, float(edge.get("confidence", 0.0) or 0.0)) * 0.5,
    }
    score = round(sum(breakdown.values()), 4)
    details = {
        "breakdown": breakdown,
        "matched_years": sorted(year_overlap | chunk_year_overlap),
        "matched_keywords": sorted(keyword_overlap)[:20],
        "matched_phrase_count": phrase_count,
    }
    return score, details


def collect_embedding_candidate_edges(
    claim: dict,
    indexes: dict,
    config: dict,
    embedding_index: dict,
    node_scores: np.ndarray,
    edge_scores: np.ndarray,
    node_dense: dict[str, float],
    edge_dense: dict[str, float],
    query_tokens: set[str],
    relation_type_set: set[str],
) -> tuple[set[str], Counter, list[dict], dict[str, float], set[str]]:
    retrieval_config = config.get("graph_retrieval", {})
    temporal_index = indexes["temporal_index"]
    top_dense_nodes = int(retrieval_config.get("top_dense_nodes", 50))
    top_dense_edges = int(retrieval_config.get("top_dense_edges", 200))
    top_paths = int(retrieval_config.get("top_paths", 20))
    candidate_edges: set[str] = set()
    seed_nodes: set[str] = set()
    reasons: Counter = Counter()

    for index in top_indices(node_scores, top_dense_nodes):
        node_id = embedding_index["node_ids"][index]
        seed_nodes.add(node_id)
        reasons["dense_node_seed"] += 1

    for index in top_indices(edge_scores, top_dense_edges):
        edge_id = embedding_index["edge_ids"][index]
        candidate_edges.add(edge_id)
        reasons["dense_edge"] += 1
        edge = indexes["edges_by_id"].get(edge_id, {})
        if edge.get("source") in indexes["nodes_by_id"]:
            seed_nodes.add(edge["source"])
        if edge.get("target") in indexes["nodes_by_id"]:
            seed_nodes.add(edge["target"])

    for match in as_list(claim.get("alias_matches")):
        node_id = match.get("entity_id")
        if node_id in indexes["nodes_by_id"]:
            seed_nodes.add(node_id)
            reasons["alias_seed"] += 1

    for year in as_list(claim.get("years")):
        year_key = str(year)
        for edge_id in temporal_index.get("year_to_edges", {}).get(year_key, []):
            if (
                edge_id in indexes["edges_by_id"]
                and indexes["edges_by_id"][edge_id].get("type") != "MENTIONS"
            ):
                candidate_edges.add(edge_id)
                reasons["year_edge"] += 1
        for node_id in temporal_index.get("year_to_nodes", {}).get(year_key, []):
            if (
                node_id in indexes["nodes_by_id"]
                and indexes["nodes_by_id"][node_id].get("type") != "DocumentChunk"
            ):
                seed_nodes.add(node_id)
                reasons["year_seed"] += 1

    paths, path_reasons = find_multihop_paths(
        seed_nodes,
        claim,
        indexes,
        config,
        node_dense,
        edge_dense,
        query_tokens,
        relation_type_set,
    )
    reasons.update(path_reasons)
    for path in paths[:top_paths]:
        for edge_id in as_list(path.get("edges")):
            candidate_edges.add(edge_id)
            reasons["multihop_path_edge"] += 1

    return (
        candidate_edges,
        reasons,
        paths[:top_paths],
        path_support_scores(paths, top_paths),
        seed_nodes,
    )


def score_edge_embedding(
    edge_id: str,
    claim: dict,
    indexes: dict,
    phrase_keys: list[str],
    query_tokens: set[str],
    relation_type_set: set[str],
    node_dense: dict[str, float],
    edge_dense: dict[str, float],
    path_support: dict[str, float],
) -> tuple[float, dict]:
    base_score, base_details = score_edge(
        edge_id, claim, indexes, phrase_keys, query_tokens, relation_type_set
    )
    edge = indexes["edges_by_id"][edge_id]
    dense_edge = max(0.0, edge_dense.get(edge_id, 0.0))
    dense_endpoint = max(
        max(0.0, node_dense.get(edge.get("source", ""), 0.0)),
        max(0.0, node_dense.get(edge.get("target", ""), 0.0)),
    )
    embedding_breakdown = {
        "dense_edge": dense_edge * 12.0,
        "dense_endpoint": dense_endpoint * 4.0,
        "multihop_path_support": min(
            4.0, max(0.0, path_support.get(edge_id, 0.0)) * 2.0
        ),
        "deterministic_signals": base_score * 0.45,
    }
    score = round(sum(embedding_breakdown.values()), 4)
    details = dict(base_details)
    details["breakdown"] = {**base_details.get("breakdown", {}), **embedding_breakdown}
    details["dense_edge_score"] = round(edge_dense.get(edge_id, 0.0), 6)
    details["dense_source_score"] = round(
        node_dense.get(edge.get("source", ""), 0.0), 6
    )
    details["dense_target_score"] = round(
        node_dense.get(edge.get("target", ""), 0.0), 6
    )
    details["path_support"] = round(path_support.get(edge_id, 0.0), 6)
    return score, details


def format_fact(edge_id: str, score: float, details: dict, indexes: dict) -> dict:
    edge = indexes["edges_by_id"][edge_id]
    source = indexes["nodes_by_id"].get(edge.get("source", ""))
    target = indexes["nodes_by_id"].get(edge.get("target", ""))
    return {
        "fact_id": edge_id,
        "score": score,
        "type": edge.get("type", ""),
        "source": node_label(source),
        "target": node_label(target),
        "description": edge.get("description", ""),
        "evidence_text": edge.get("evidence_text", ""),
        "source_chunk": edge.get("source_chunk", ""),
        "years": item_years(indexes["temporal_index"], "edge", edge_id),
        "source_chunk_years": item_years(
            indexes["temporal_index"], "chunk", edge.get("source_chunk", "")
        ),
        "score_details": details,
    }


def format_path(path: dict, indexes: dict) -> dict:
    nodes = [
        node_label(indexes["nodes_by_id"].get(node_id))
        for node_id in as_list(path.get("nodes"))
    ]
    edges = []
    for edge_id in as_list(path.get("edges")):
        edge = indexes["edges_by_id"].get(edge_id, {})
        edges.append(
            {
                "fact_id": edge_id,
                "type": edge.get("type", ""),
                "source": node_label(
                    indexes["nodes_by_id"].get(edge.get("source", ""))
                ),
                "target": node_label(
                    indexes["nodes_by_id"].get(edge.get("target", ""))
                ),
                "description": edge.get("description", ""),
                "evidence_text": edge.get("evidence_text", ""),
                "source_chunk": edge.get("source_chunk", ""),
            }
        )
    return {
        "path_id": path.get("path_id", ""),
        "score": path.get("score", 0.0),
        "hop_count": path.get("hop_count", 0),
        "nodes": nodes,
        "edges": edges,
    }


def collect_candidate_chunks(
    claim: dict, facts: list[dict], indexes: dict, config: dict
) -> set[str]:
    retrieval_config = config.get("graph_retrieval", {})
    temporal_index = indexes["temporal_index"]
    chunks: set[str] = {
        fact.get("source_chunk") for fact in facts if fact.get("source_chunk")
    }
    for match in as_list(claim.get("alias_matches")):
        node_id = match.get("entity_id")
        if node_id:
            chunks.update(indexes["node_to_chunks"].get(node_id, set()))
    for year in as_list(claim.get("years")):
        chunks.update(temporal_index.get("year_to_chunks", {}).get(str(year), []))

    keywords = claim_keywords(claim)
    query_tokens = token_set(" ".join([claim.get("query", ""), " ".join(keywords)]))
    chunks.update(
        sorted_limited_token_ids(
            query_tokens,
            indexes["token_to_chunks"],
            int(retrieval_config.get("keyword_chunk_token_limit", 20)),
            int(retrieval_config.get("max_token_chunks", 200)),
        )
    )
    return {chunk_id for chunk_id in chunks if chunk_id in indexes["chunks_by_id"]}


def score_chunk(
    chunk_id: str,
    claim: dict,
    fact_scores_by_chunk: dict[str, float],
    indexes: dict,
    phrase_keys: list[str],
    query_tokens: set[str],
) -> tuple[float, dict]:
    chunk = indexes["chunks_by_id"][chunk_id]
    claim_years = set(
        year for year in as_list(claim.get("years")) if isinstance(year, int)
    )
    chunk_years = indexes["chunk_years"].get(chunk_id, set())
    keyword_overlap = query_tokens & indexes["chunk_tokens"].get(chunk_id, set())
    phrase_count = phrase_key_hits(
        phrase_keys, indexes["chunk_match_texts"].get(chunk_id, "")
    )
    matched_node_bonus = 0.0
    for match in as_list(claim.get("alias_matches")):
        node_id = match.get("entity_id")
        if node_id and chunk_id in indexes["node_to_chunks"].get(node_id, set()):
            matched_node_bonus += 2.0
    breakdown = {
        "graph_fact_support": min(12.0, fact_scores_by_chunk.get(chunk_id, 0.0) * 0.6),
        "entity_source_chunk": min(8.0, matched_node_bonus),
        "year_overlap": len(claim_years & chunk_years) * 2.0,
        "keyword_overlap": min(8.0, len(keyword_overlap) * 0.4),
        "keyword_phrase": min(8.0, phrase_count * 2.0),
    }
    score = round(sum(breakdown.values()), 4)
    return score, {
        "breakdown": breakdown,
        "matched_years": sorted(claim_years & chunk_years),
        "matched_keywords": sorted(keyword_overlap)[:30],
        "matched_phrase_count": phrase_count,
    }


def format_chunk(chunk_id: str, score: float, details: dict, indexes: dict) -> dict:
    chunk = indexes["chunks_by_id"][chunk_id]
    return {
        "chunk_id": chunk_id,
        "score": score,
        "book": chunk.get("book", ""),
        "chapter": chunk.get("chapter", ""),
        "section": chunk.get("section", ""),
        "pages": chunk.get("pages", []),
        "years": item_years(indexes["temporal_index"], "chunk", chunk_id),
        "text": chunk.get("text", ""),
        "score_details": details,
    }


def retrieve_claim(
    claim: dict, indexes: dict, config: dict, top_facts: int, top_chunks: int
) -> dict:
    retrieval_config = config.get("graph_retrieval", {})
    phrases = claim_keywords(claim)
    phrase_keys = normalized_phrase_keys(phrases)
    query_tokens = token_set(" ".join([claim.get("query", ""), " ".join(phrases)]))
    relation_type_set = relation_types(claim)
    candidate_edges, candidate_reasons = collect_candidate_edges(claim, indexes, config)
    max_candidate_edges = int(retrieval_config.get("max_candidate_edges", 1500))
    if len(candidate_edges) > max_candidate_edges:
        candidate_edges = set(
            sorted(
                candidate_edges,
                key=lambda edge_id: (
                    -cheap_edge_score(
                        edge_id, claim, indexes, query_tokens, relation_type_set
                    ),
                    edge_id,
                ),
            )[:max_candidate_edges]
        )
    scored_edges = []
    for edge_id in candidate_edges:
        score, details = score_edge(
            edge_id, claim, indexes, phrase_keys, query_tokens, relation_type_set
        )
        if score > 0:
            scored_edges.append((edge_id, score, details))
    scored_edges.sort(key=lambda item: (-item[1], item[0]))
    facts = [
        format_fact(edge_id, score, details, indexes)
        for edge_id, score, details in scored_edges[:top_facts]
    ]

    fact_scores_by_chunk: dict[str, float] = defaultdict(float)
    for fact in facts:
        if fact.get("source_chunk"):
            fact_scores_by_chunk[fact["source_chunk"]] += float(
                fact.get("score", 0.0) or 0.0
            )
    candidate_chunks = collect_candidate_chunks(claim, facts, indexes, config)
    max_candidate_chunks = int(retrieval_config.get("max_candidate_chunks", 700))
    if len(candidate_chunks) > max_candidate_chunks:
        candidate_chunks = set(
            sorted(
                candidate_chunks,
                key=lambda chunk_id: (
                    -cheap_chunk_score(
                        chunk_id, claim, fact_scores_by_chunk, indexes, query_tokens
                    ),
                    chunk_id,
                ),
            )[:max_candidate_chunks]
        )
    scored_chunks = []
    for chunk_id in candidate_chunks:
        score, details = score_chunk(
            chunk_id, claim, fact_scores_by_chunk, indexes, phrase_keys, query_tokens
        )
        if score > 0:
            scored_chunks.append((chunk_id, score, details))
    scored_chunks.sort(key=lambda item: (-item[1], item[0]))
    linked_chunks = [
        format_chunk(chunk_id, score, details, indexes)
        for chunk_id, score, details in scored_chunks[:top_chunks]
    ]

    matched_entities = []
    for match in as_list(claim.get("alias_matches")):
        node = indexes["nodes_by_id"].get(match.get("entity_id", ""))
        if not node:
            continue
        matched_entities.append(
            {
                "entity_id": match.get("entity_id", ""),
                "canonical_name": match.get("canonical_name", ""),
                "canonical_type": match.get("canonical_type", ""),
                "matched_alias": match.get("matched_alias", ""),
                "node_years": item_years(
                    indexes["temporal_index"], "node", match.get("entity_id", "")
                ),
            }
        )

    return {
        "ID": claim.get("ID"),
        "label": claim.get("label"),
        "key": claim.get("key", ""),
        "claim": claim.get("claim", ""),
        "query": claim.get("query", ""),
        "claim_years": as_list(claim.get("years")),
        "matched_entities": matched_entities,
        "graph_facts": facts,
        "linked_chunks": linked_chunks,
        "retrieval_stats": {
            "candidate_edges": len(candidate_edges),
            "candidate_chunks": len(candidate_chunks),
            "candidate_edge_reasons": dict(candidate_reasons),
            "query_token_count": len(query_tokens),
            "keyword_phrase_count": len(phrases),
        },
    }


def retrieve_claim_embedding(
    claim: dict,
    indexes: dict,
    config: dict,
    top_facts: int,
    top_chunks: int,
    embedding_index: dict,
    query_embedding: np.ndarray,
) -> dict:
    retrieval_config = config.get("graph_retrieval", {})
    phrases = claim_keywords(claim)
    phrase_keys = normalized_phrase_keys(phrases)
    query_text = claim_query_text(claim)
    query_tokens = token_set(query_text)
    relation_type_set = relation_types(claim)
    node_scores, edge_scores, chunk_scores = score_arrays(
        query_embedding, embedding_index
    )
    node_dense, edge_dense, chunk_dense = dense_score_maps(
        embedding_index, node_scores, edge_scores, chunk_scores
    )

    candidate_edges, candidate_reasons, paths, path_support, seed_nodes = (
        collect_embedding_candidate_edges(
            claim,
            indexes,
            config,
            embedding_index,
            node_scores,
            edge_scores,
            node_dense,
            edge_dense,
            query_tokens,
            relation_type_set,
        )
    )
    max_candidate_edges = int(retrieval_config.get("max_candidate_edges", 500))
    if len(candidate_edges) > max_candidate_edges:
        candidate_edges = set(
            sorted(
                candidate_edges,
                key=lambda edge_id: (
                    -max(
                        edge_dense.get(edge_id, 0.0),
                        path_support.get(edge_id, 0.0),
                        cheap_edge_score(
                            edge_id, claim, indexes, query_tokens, relation_type_set
                        )
                        / 20.0,
                    ),
                    edge_id,
                ),
            )[:max_candidate_edges]
        )
        candidate_reasons["candidate_edge_cap_applied"] += 1

    scored_edges = []
    for edge_id in candidate_edges:
        if (
            edge_id not in indexes["edges_by_id"]
            or indexes["edges_by_id"][edge_id].get("type") == "MENTIONS"
        ):
            continue
        score, details = score_edge_embedding(
            edge_id,
            claim,
            indexes,
            phrase_keys,
            query_tokens,
            relation_type_set,
            node_dense,
            edge_dense,
            path_support,
        )
        if score > 0:
            scored_edges.append((edge_id, score, details))
    scored_edges.sort(key=lambda item: (-item[1], item[0]))
    facts = [
        format_fact(edge_id, score, details, indexes)
        for edge_id, score, details in scored_edges[:top_facts]
    ]

    fact_scores_by_chunk: dict[str, float] = defaultdict(float)
    candidate_chunks: set[str] = set()
    for fact in facts:
        if fact.get("source_chunk"):
            candidate_chunks.add(fact["source_chunk"])
            fact_scores_by_chunk[fact["source_chunk"]] += float(
                fact.get("score", 0.0) or 0.0
            )
    for node_id in seed_nodes:
        candidate_chunks.update(indexes["node_to_chunks"].get(node_id, set()))
    for year in as_list(claim.get("years")):
        candidate_chunks.update(
            indexes["temporal_index"].get("year_to_chunks", {}).get(str(year), [])
        )
    top_dense_chunks = int(retrieval_config.get("top_dense_chunks", 80))
    for index in top_indices(chunk_scores, top_dense_chunks):
        candidate_chunks.add(embedding_index["chunk_ids"][index])
        candidate_reasons["dense_chunk"] += 1
    candidate_chunks = {
        chunk_id for chunk_id in candidate_chunks if chunk_id in indexes["chunks_by_id"]
    }
    max_candidate_chunks = int(retrieval_config.get("max_candidate_chunks", 250))
    if len(candidate_chunks) > max_candidate_chunks:
        candidate_chunks = set(
            sorted(
                candidate_chunks,
                key=lambda chunk_id: (
                    -max(
                        chunk_dense.get(chunk_id, 0.0),
                        cheap_chunk_score(
                            chunk_id, claim, fact_scores_by_chunk, indexes, query_tokens
                        )
                        / 20.0,
                    ),
                    chunk_id,
                ),
            )[:max_candidate_chunks]
        )
        candidate_reasons["candidate_chunk_cap_applied"] += 1

    scored_chunks = []
    for chunk_id in candidate_chunks:
        score, details = score_chunk(
            chunk_id, claim, fact_scores_by_chunk, indexes, phrase_keys, query_tokens
        )
        dense_chunk_score = max(0.0, chunk_dense.get(chunk_id, 0.0))
        details["breakdown"]["dense_chunk"] = dense_chunk_score * 8.0
        details["dense_chunk_score"] = round(chunk_dense.get(chunk_id, 0.0), 6)
        score = round(score + dense_chunk_score * 8.0, 4)
        if score > 0:
            scored_chunks.append((chunk_id, score, details))
    scored_chunks.sort(key=lambda item: (-item[1], item[0]))
    linked_chunks = [
        format_chunk(chunk_id, score, details, indexes)
        for chunk_id, score, details in scored_chunks[:top_chunks]
    ]

    matched_entities = []
    for match in as_list(claim.get("alias_matches")):
        node = indexes["nodes_by_id"].get(match.get("entity_id", ""))
        if not node:
            continue
        matched_entities.append(
            {
                "entity_id": match.get("entity_id", ""),
                "canonical_name": match.get("canonical_name", ""),
                "canonical_type": match.get("canonical_type", ""),
                "matched_alias": match.get("matched_alias", ""),
                "node_years": item_years(
                    indexes["temporal_index"], "node", match.get("entity_id", "")
                ),
            }
        )

    top_seed_nodes = sorted(
        seed_nodes, key=lambda node_id: (-node_dense.get(node_id, 0.0), node_id)
    )[: int(retrieval_config.get("report_seed_nodes", 10))]
    return {
        "ID": claim.get("ID"),
        "label": claim.get("label"),
        "key": claim.get("key", ""),
        "claim": claim.get("claim", ""),
        "query": query_text,
        "claim_years": as_list(claim.get("years")),
        "matched_entities": matched_entities,
        "seed_nodes": [
            {
                **node_label(indexes["nodes_by_id"].get(node_id)),
                "dense_score": round(node_dense.get(node_id, 0.0), 6),
            }
            for node_id in top_seed_nodes
        ],
        "graph_facts": facts,
        "graph_paths": [format_path(path, indexes) for path in paths],
        "linked_chunks": linked_chunks,
        "retrieval_stats": {
            "method": "embedding_multihop",
            "candidate_edges": len(candidate_edges),
            "candidate_chunks": len(candidate_chunks),
            "candidate_edge_reasons": dict(candidate_reasons),
            "seed_nodes": len(seed_nodes),
            "graph_paths": len(paths),
            "query_token_count": len(query_tokens),
            "keyword_phrase_count": len(phrases),
        },
    }


def build_report(
    results: list[dict],
    nodes: list[dict],
    edges: list[dict],
    chunks: list[dict],
    config: dict,
) -> str:
    fact_counts = [len(row.get("graph_facts", [])) for row in results]
    chunk_counts = [len(row.get("linked_chunks", [])) for row in results]
    edge_types = Counter(
        fact.get("type") for row in results for fact in row.get("graph_facts", [])
    )
    claim_year_coverage = sum(1 for row in results if row.get("claim_years"))
    entity_coverage = sum(1 for row in results if row.get("matched_entities"))
    method = config.get("graph_retrieval", {}).get("method", "deterministic")
    if method == "embedding_multihop":
        method_lines = [
            "Embedding-guided multi-hop graph retrieval. No LLM is used during retrieval.",
            "",
            "Signals used:",
            "",
            "1. Dense similarity between claim query and graph nodes.",
            "2. Dense similarity between claim query and graph edges/facts.",
            "3. Beam-search multi-hop expansion over non-`MENTIONS` relation edges.",
            "4. Stage 9 alias matches and temporal signals as seeds/bonuses.",
            "5. Lexical keyword, phrase overlap, relation hints, and source chunks for reranking.",
        ]
    else:
        method_lines = [
            "Deterministic graph-only retrieval. No LLM is used.",
            "",
            "Signals used:",
            "",
            "1. Stage 9 alias matches to canonical graph nodes.",
            "2. Stage 9 years against the temporal index.",
            "3. One-hop incident edges from matched and temporal nodes.",
            "4. Source chunks linked to candidate graph facts.",
            "5. Lexical keyword and phrase overlap from parsed claim signals.",
            "6. Relation type hints from Stage 9 Gemini parsing when available.",
        ]
    lines = [
        "# Graph Retrieval Report",
        "",
        "## Summary",
        "",
        f"- Claims retrieved: {len(results)}",
        f"- Graph nodes loaded: {len(nodes)}",
        f"- Graph edges loaded: {len(edges)}",
        f"- Chunks loaded: {len(chunks)}",
        f"- Claims with years: {claim_year_coverage}",
        f"- Claims with matched graph entities: {entity_coverage}",
        f"- Claims with graph facts: {sum(1 for count in fact_counts if count > 0)}",
        f"- Claims with linked chunks: {sum(1 for count in chunk_counts if count > 0)}",
        f"- Average graph facts per claim: {(sum(fact_counts) / len(results)) if results else 0:.2f}",
        f"- Average linked chunks per claim: {(sum(chunk_counts) / len(results)) if results else 0:.2f}",
        "",
        "## Method",
        "",
        *method_lines,
        "",
        "## Config",
        "",
        "```yaml",
    ]
    for key, value in sorted(config.get("graph_retrieval", {}).items()):
        lines.append(f"{key}: {value}")
    lines.extend(
        ["```", "", "## Retrieved Fact Types", "", "| Type | Count |", "|---|---:|"]
    )
    for edge_type, count in edge_types.most_common():
        lines.append(f"| {edge_type} | {count} |")
    lines.extend(
        ["", "## Empty Retrievals", "", "| Empty field | Claims |", "|---|---:|"]
    )
    lines.append(f"| graph_facts | {sum(1 for count in fact_counts if count == 0)} |")
    lines.append(
        f"| linked_chunks | {sum(1 for count in chunk_counts if count == 0)} |"
    )
    return "\n".join(lines) + "\n"


def run_retrieval(
    config: dict,
    limit: int | None = None,
    top_facts: int | None = None,
    top_chunks: int | None = None,
) -> tuple[list[dict], str]:
    paths = config["paths"]
    retrieval_config = config.get("graph_retrieval", {})
    top_facts = top_facts or int(retrieval_config.get("top_facts", 8))
    top_chunks = top_chunks or int(retrieval_config.get("top_chunks", 3))
    claims = load_json(paths["parsed_claims"])
    if limit is not None:
        claims = claims[:limit]
    nodes = load_json(paths["graph_nodes"])
    edges = load_json(paths["graph_edges"])
    chunks = load_json(paths["cleaned_chunks"])
    temporal_index = load_json(paths["temporal_index"])
    indexes = build_indexes(nodes, edges, chunks, temporal_index)
    method = retrieval_config.get("method", "deterministic")

    results = []
    if method == "embedding_multihop":
        np_module = get_numpy()
        embedding_index = build_embedding_index(nodes, edges, chunks, indexes, config)
        query_texts = [claim_query_text(claim) for claim in claims]
        print(f"Encoding {len(query_texts)} graph retrieval queries")
        query_embeddings = np_module.asarray(
            embedding_index["model"].encode(
                query_texts,
                normalize_embeddings=True,
                batch_size=embedding_index["batch_size"],
                show_progress_bar=True,
            )
        )
        for claim, query_embedding in tqdm(
            zip(claims, query_embeddings),
            total=len(claims),
            desc="Retrieving graph evidence",
        ):
            results.append(
                retrieve_claim_embedding(
                    claim,
                    indexes,
                    config,
                    top_facts,
                    top_chunks,
                    embedding_index,
                    query_embedding,
                )
            )
    elif method == "deterministic":
        for claim in tqdm(claims, desc="Retrieving graph evidence"):
            results.append(
                retrieve_claim(claim, indexes, config, top_facts, top_chunks)
            )
    else:
        raise ValueError(f"Unsupported graph retrieval method: {method}")
    report = build_report(results, nodes, edges, chunks, config)
    return results, report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Retrieve graph evidence for parsed claims."
    )
    parser.add_argument("--config", default="configs/graph.yaml")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--top-facts", type=int, default=None)
    parser.add_argument("--top-chunks", type=int, default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--report-output", default=None)
    args = parser.parse_args()

    config = load_yaml(args.config)
    results, report = run_retrieval(
        config, limit=args.limit, top_facts=args.top_facts, top_chunks=args.top_chunks
    )
    output_path = args.output or config["paths"]["graph_topk"]
    report_path = args.report_output or config["paths"].get("graph_retrieval_report")
    save_json(results, output_path)
    if report_path:
        save_text(report, report_path)
    print(f"Saved {len(results)} graph retrieval rows to {output_path}")
    if report_path:
        print(f"Saved graph retrieval report to {report_path}")


if __name__ == "__main__":
    main()
