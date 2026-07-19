from __future__ import annotations

import argparse

from src.common.io import load_json, load_yaml, save_json
from src.common.normalize import extract_years
from src.facet.graph_index import GraphIndex
from src.facet.normalize import normalize_key


try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover
    def tqdm(iterable, **_):
        return iterable


def match_facet_value(
    graph_index: GraphIndex,
    facet_type: str,
    value: str,
    config: dict,
) -> list[dict]:
    max_matches = int(config.get("matching", {}).get("max_matches_per_facet", 5))
    graph_type_map = config.get("facets", {}).get("graph_type_map", {})
    graph_types = set(graph_type_map.get(facet_type, []))
    matches = []
    if facet_type == "time" and config.get("matching", {}).get("use_year_index", True):
        for year in sorted(extract_years(value)):
            matches.extend(graph_index.match_year(year, max_matches=max_matches))
    if facet_type not in {"quantity", "action", "result"}:
        matches.extend(graph_index.match_aliases(value, graph_types=graph_types or None, max_matches=max_matches))
        if not matches and config.get("matching", {}).get("use_substring_match", False):
            matches.extend(
                graph_index.match_aliases_substring(
                    value,
                    graph_types=graph_types or None,
                    max_matches=max_matches,
                    min_chars=int(config.get("matching", {}).get("substring_min_chars", 6)),
                )
            )
    deduped = []
    seen = set()
    for match in matches:
        key = (match.get("node_id"), match.get("match_method"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(match)
        if len(deduped) >= max_matches:
            break
    return deduped


def match_row(row: dict, graph_index: GraphIndex, config: dict) -> dict:
    facet_matches = []
    matched_facet_keys = set()
    total_facets = 0
    for facet_type, values in row.get("facets", {}).items():
        for value in values:
            total_facets += 1
            matches = match_facet_value(graph_index, facet_type, value, config)
            if matches:
                matched_facet_keys.add((facet_type, normalize_key(value)))
            facet_matches.append(
                {
                    "facet_type": facet_type,
                    "facet_value": value,
                    "matches": matches,
                    "matched": bool(matches),
                }
            )
    return {
        **row,
        "facet_matches": facet_matches,
        "facet_match_summary": {
            "total_facets": total_facets,
            "matched_facets": len(matched_facet_keys),
            "match_rate": (len(matched_facet_keys) / total_facets) if total_facets else 0.0,
        },
    }


def run_match(config: dict) -> list[dict]:
    rows = load_json(config["paths"]["claim_facets"])
    graph_index = GraphIndex(config)
    output = [match_row(row, graph_index, config) for row in tqdm(rows, desc="Matching facets")]
    save_json(output, config["paths"]["facet_matches"])
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Match claim facets to graph nodes.")
    parser.add_argument("--config", default="configs/facet/facet.yaml")
    args = parser.parse_args()
    config = load_yaml(args.config)
    rows = run_match(config)
    print(f"Saved {len(rows)} rows to {config['paths']['facet_matches']}")


if __name__ == "__main__":
    main()
