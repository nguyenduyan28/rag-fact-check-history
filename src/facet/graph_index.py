from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from src.common.io import load_json
from src.facet.normalize import normalize_key, normalize_facet_value


@dataclass(frozen=True)
class AliasCandidate:
    alias: str
    normalized_alias: str
    entity_id: str
    canonical_name: str
    canonical_type: str
    mention_count: int


class GraphIndex:
    def __init__(self, config: dict):
        paths = config["paths"]
        self.nodes = load_json(paths["nodes"])
        self.edges = load_json(paths["edges"])
        self.aliases = load_json(paths["aliases"])
        self.temporal_index = load_json(paths["temporal_index"])
        self.nodes_by_id = {node["id"]: node for node in self.nodes if isinstance(node, dict)}
        self.edges_by_source: dict[str, list[dict]] = defaultdict(list)
        self.edges_by_target: dict[str, list[dict]] = defaultdict(list)
        self.mention_chunks_by_entity: dict[str, set[str]] = defaultdict(set)
        for edge in self.edges:
            if not isinstance(edge, dict):
                continue
            source = edge.get("source")
            target = edge.get("target")
            if source:
                self.edges_by_source[source].append(edge)
            if target:
                self.edges_by_target[target].append(edge)
            if edge.get("type") == "MENTIONS" and target and edge.get("source_chunk"):
                self.mention_chunks_by_entity[target].add(edge["source_chunk"])
        self.alias_candidates = self._build_alias_candidates(config)
        self.year_to_nodes = {
            int(year): set(node_ids)
            for year, node_ids in self.temporal_index.get("year_to_nodes", {}).items()
            if str(year).isdigit()
        }
        self.year_to_chunks = {
            int(year): set(chunk_ids)
            for year, chunk_ids in self.temporal_index.get("year_to_chunks", {}).items()
            if str(year).isdigit()
        }

    def _build_alias_candidates(self, config: dict) -> list[AliasCandidate]:
        min_alias_chars = int(config.get("matching", {}).get("min_alias_chars", 4))
        by_key: dict[tuple[str, str], AliasCandidate] = {}
        for row in self.aliases.get("aliases", []):
            if not isinstance(row, dict):
                continue
            alias = normalize_facet_value(str(row.get("alias", "")))
            normalized_alias = normalize_key(str(row.get("normalized_alias") or alias))
            entity_id = normalize_facet_value(str(row.get("canonical_id", "")))
            if not alias or not normalized_alias or not entity_id:
                continue
            if len(normalized_alias.replace(" ", "")) < min_alias_chars:
                continue
            candidate = AliasCandidate(
                alias=alias,
                normalized_alias=normalized_alias,
                entity_id=entity_id,
                canonical_name=normalize_facet_value(str(row.get("canonical_name", ""))),
                canonical_type=normalize_facet_value(str(row.get("canonical_type", ""))),
                mention_count=int(row.get("mention_count", 0) or 0),
            )
            key = (normalized_alias, entity_id)
            current = by_key.get(key)
            if current is None or len(candidate.alias) > len(current.alias):
                by_key[key] = candidate
        return sorted(
            by_key.values(),
            key=lambda item: (
                -len(item.normalized_alias.split()),
                -len(item.normalized_alias),
                -item.mention_count,
                item.normalized_alias,
            ),
        )

    def get_node(self, node_id: str) -> dict[str, Any]:
        return self.nodes_by_id.get(node_id, {})

    def get_chunk(self, chunk_id: str) -> dict[str, Any]:
        return self.nodes_by_id.get(f"chunk_{chunk_id}") or self.nodes_by_id.get(chunk_id, {})

    def match_aliases(
        self,
        text: str,
        graph_types: set[str] | None,
        max_matches: int,
    ) -> list[dict]:
        normalized_text = f" {normalize_key(text)} "
        matches = []
        seen_entities = set()
        occupied_spans: list[tuple[int, int]] = []
        for candidate in self.alias_candidates:
            if graph_types and candidate.canonical_type not in graph_types:
                continue
            needle = f" {candidate.normalized_alias} "
            start = normalized_text.find(needle)
            if start < 0:
                continue
            end = start + len(needle)
            if any(not (end <= left or start >= right) for left, right in occupied_spans):
                continue
            if candidate.entity_id in seen_entities:
                continue
            seen_entities.add(candidate.entity_id)
            occupied_spans.append((start, end))
            matches.append(
                {
                    "node_id": candidate.entity_id,
                    "node_name": candidate.canonical_name,
                    "node_type": candidate.canonical_type,
                    "matched_alias": candidate.alias,
                    "normalized_alias": candidate.normalized_alias,
                    "match_method": "alias_exact",
                    "mention_count": candidate.mention_count,
                }
            )
            if len(matches) >= max_matches:
                break
        return matches

    def match_aliases_substring(
        self,
        text: str,
        graph_types: set[str] | None,
        max_matches: int,
        min_chars: int = 6,
    ) -> list[dict]:
        """Fallback: match when the facet text is a sub-phrase of a longer alias
        (e.g. facet `Quốc dân Đảng` vs alias `Việt Nam Quốc dân Đảng`)."""
        normalized = normalize_key(text)
        if len(normalized.replace(" ", "")) < min_chars:
            return []
        needle = f" {normalized} "
        matches = []
        seen_entities = set()
        for candidate in self.alias_candidates:
            if graph_types and candidate.canonical_type not in graph_types:
                continue
            if needle not in f" {candidate.normalized_alias} ":
                continue
            if candidate.normalized_alias == normalized:
                continue
            if candidate.entity_id in seen_entities:
                continue
            seen_entities.add(candidate.entity_id)
            matches.append(
                {
                    "node_id": candidate.entity_id,
                    "node_name": candidate.canonical_name,
                    "node_type": candidate.canonical_type,
                    "matched_alias": candidate.alias,
                    "normalized_alias": candidate.normalized_alias,
                    "match_method": "alias_substring",
                    "mention_count": candidate.mention_count,
                }
            )
            if len(matches) >= max_matches:
                break
        return matches

    def match_year(self, year: int, max_matches: int) -> list[dict]:
        matches = []
        for node_id in sorted(self.year_to_nodes.get(year, set())):
            node = self.get_node(node_id)
            if node.get("type") != "Time":
                continue
            matches.append(
                {
                    "node_id": node_id,
                    "node_name": node.get("name", str(year)),
                    "node_type": node.get("type", "Time"),
                    "matched_alias": str(year),
                    "normalized_alias": str(year),
                    "match_method": "year_index",
                    "mention_count": int(node.get("mention_count", 0) or 0),
                }
            )
            if len(matches) >= max_matches:
                break
        return matches

    def relation_edges_for_node(self, node_id: str, allowed_relations: set[str]) -> list[dict]:
        edges = []
        for edge in self.edges_by_source.get(node_id, []) + self.edges_by_target.get(node_id, []):
            if edge.get("type") in allowed_relations:
                edges.append(edge)
        return edges

    def source_chunks_for_node(self, node_id: str) -> set[str]:
        chunks = set(self.mention_chunks_by_entity.get(node_id, set()))
        node = self.get_node(node_id)
        chunks.update(node.get("source_chunks", []) or [])
        return chunks
