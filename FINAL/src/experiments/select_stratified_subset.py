"""Select a stratified verifier-input subset for smoke testing.

Stratifies by claim source (exam-derived `His`/`MET` IDs vs key-generated
numeric IDs) and by label, taking every k-th row deterministically so the
sample is spread across the whole dataset instead of the (easier) prefix.

Usage:
  python3 -m src.experiments.select_stratified_subset \
    --input data/outputs/facet/full-ce/hybrid_facet_reranked.json \
    --output data/outputs/facet/ce-smoke-2000/verify_input.json \
    --per-cell exam:real=750 exam:fake=750 keygen:real=250 keygen:fake=250
"""
from __future__ import annotations

import argparse
import re

from src.common.io import load_json, save_json


def group_of(claim_id: str) -> str:
    return "exam" if re.search(r"His|MET", str(claim_id)) else "keygen"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--per-cell",
        nargs="+",
        default=["exam:real=750", "exam:fake=750", "keygen:real=250", "keygen:fake=250"],
    )
    args = parser.parse_args()

    quotas = {}
    for spec in args.per_cell:
        cell, count = spec.split("=")
        quotas[tuple(cell.split(":"))] = int(count)

    rows = load_json(args.input)
    cells: dict[tuple[str, str], list[dict]] = {key: [] for key in quotas}
    for row in rows:
        key = (group_of(row.get("ID")), str(row.get("label", "")))
        if key in cells:
            cells[key].append(row)

    selected = []
    for key, quota in quotas.items():
        pool = cells[key]
        if len(pool) < quota:
            raise SystemExit(f"cell {key}: pool {len(pool)} < quota {quota}")
        step = len(pool) / quota
        picks = [pool[int(i * step)] for i in range(quota)]
        selected.extend(picks)
        print(f"cell {key}: {quota}/{len(pool)} (every ~{step:.1f})")

    selected.sort(key=lambda row: int(row.get("row_index", 0) or 0))
    save_json(selected, args.output)
    print(f"Saved {len(selected)} rows to {args.output}")


if __name__ == "__main__":
    main()
