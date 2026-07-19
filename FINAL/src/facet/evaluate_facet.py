from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from statistics import mean

from src.common.io import load_json, load_yaml, save_json, save_text


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def build_eda(rows: list[dict]) -> dict:
    label_counts = Counter(row.get("label", "") for row in rows)
    facet_value_counts = Counter()
    claims_with_facet = Counter()
    match_totals = Counter()
    matched_totals = Counter()
    evidence_counts = []
    top_evidence_counts = []
    chunks = Counter()
    source_books = Counter()

    for row in rows:
        for facet_type, values in row.get("facets", {}).items():
            facet_value_counts[facet_type] += len(values)
            if values:
                claims_with_facet[facet_type] += 1
        for evidence in row.get("top_evidence", []):
            chunks[evidence.get("chunk_id")] += 1
            if evidence.get("book"):
                source_books[evidence.get("book")] += 1
        top_evidence_counts.append(len(row.get("top_evidence", [])))
        evidence_counts.append(int(row.get("evidence_summary", {}).get("candidate_chunks", 0) or 0))
        for facet_match in row.get("facet_matches", []):
            facet_type = facet_match.get("facet_type", "")
            match_totals[facet_type] += 1
            if facet_match.get("matched"):
                matched_totals[facet_type] += 1
        if not row.get("facet_matches"):
            summary = row.get("facet_match_summary", {})
            # Reranked rows do not keep all facet match rows, so estimate from facets.
            for facet_type, values in row.get("facets", {}).items():
                match_totals[facet_type] += len(values)

    total_rows = len(rows)
    rows_with_evidence = sum(1 for row in rows if row.get("top_evidence"))
    match_rates = {}
    for facet_type, total in match_totals.items():
        match_rates[facet_type] = {
            "total_facets": total,
            "matched_facets": matched_totals.get(facet_type, 0),
            "match_rate": (matched_totals.get(facet_type, 0) / total) if total else 0.0,
        }

    return {
        "claims": total_rows,
        "label_counts": dict(label_counts),
        "rows_with_evidence": rows_with_evidence,
        "evidence_coverage": (rows_with_evidence / total_rows) if total_rows else 0.0,
        "avg_candidate_chunks": mean(evidence_counts) if evidence_counts else 0.0,
        "avg_top_evidence": mean(top_evidence_counts) if top_evidence_counts else 0.0,
        "facet_value_counts": dict(facet_value_counts),
        "claims_with_facet": dict(claims_with_facet),
        "facet_match_rates": match_rates,
        "top_chunks": chunks.most_common(20),
        "source_books": dict(source_books),
    }


def build_markdown(eda: dict) -> str:
    lines = [
        "# FacetGraphRAG EDA Report",
        "",
        "## Summary",
        "",
        f"- Claims: {eda['claims']}",
        f"- Rows with top evidence: {eda['rows_with_evidence']} ({pct(eda['evidence_coverage'])})",
        f"- Avg candidate chunks per claim: {eda['avg_candidate_chunks']:.2f}",
        f"- Avg top evidence per claim: {eda['avg_top_evidence']:.2f}",
        "",
        "## Labels",
        "",
        "| Label | Count |",
        "|---|---:|",
    ]
    for label, count in sorted(eda["label_counts"].items()):
        lines.append(f"| {label} | {count} |")

    lines.extend(["", "## Facet Values", "", "| Facet | Values | Claims with facet |", "|---|---:|---:|"])
    facet_types = sorted(set(eda["facet_value_counts"]) | set(eda["claims_with_facet"]))
    for facet_type in facet_types:
        lines.append(
            f"| {facet_type} | {eda['facet_value_counts'].get(facet_type, 0)} | {eda['claims_with_facet'].get(facet_type, 0)} |"
        )

    lines.extend(["", "## Facet Match Rates", "", "| Facet | Matched | Total | Match rate |", "|---|---:|---:|---:|"])
    for facet_type, item in sorted(eda["facet_match_rates"].items()):
        lines.append(
            f"| {facet_type} | {item['matched_facets']} | {item['total_facets']} | {pct(item['match_rate'])} |"
        )

    lines.extend(["", "## Evidence Books", "", "| Book | Evidence hits |", "|---|---:|"])
    for book, count in sorted(eda["source_books"].items()):
        lines.append(f"| {book} | {count} |")

    lines.extend(["", "## Top Reused Chunks", "", "| Chunk | Count |", "|---|---:|"])
    for chunk_id, count in eda["top_chunks"]:
        lines.append(f"| {chunk_id} | {count} |")
    return "\n".join(lines) + "\n"


def run_evaluate(config: dict) -> dict:
    rows = load_json(config["paths"]["facet_reranked"])
    eda = build_eda(rows)
    save_json(eda, config["paths"]["run_report"])
    save_text(build_markdown(eda), config["paths"]["eda_report"])
    return eda


def main() -> None:
    parser = argparse.ArgumentParser(description="Build EDA report for FacetGraphRAG outputs.")
    parser.add_argument("--config", default="configs/facet/facet.yaml")
    args = parser.parse_args()
    config = load_yaml(args.config)
    eda = run_evaluate(config)
    print(f"Saved facet report to {config['paths']['eda_report']}")
    print(f"Evidence coverage: {pct(eda['evidence_coverage'])}")


if __name__ == "__main__":
    main()
