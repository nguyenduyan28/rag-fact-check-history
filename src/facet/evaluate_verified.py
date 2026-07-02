from __future__ import annotations

import argparse
from collections import Counter
import re

from src.common.io import load_json, load_yaml, save_text


VALID_LABELS = ["real", "fake"]


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def safe_div(num: int, den: int) -> float:
    return num / den if den else 0.0


def build_report(rows: list[dict]) -> str:
    normalized_rows = [{**row, "label_rag": normalize_prediction(row)} for row in rows]
    scored = [
        row
        for row in normalized_rows
        if row.get("label") in VALID_LABELS and row.get("label_rag") in VALID_LABELS
    ]
    total = len(scored)
    total_rows = len(normalized_rows)
    unknown_rows = sum(1 for row in normalized_rows if row.get("label_rag") == "unknown")
    error_rows = sum(1 for row in normalized_rows if row.get("label_rag") == "error")
    correct = sum(1 for row in scored if row.get("label") == row.get("label_rag"))
    labels = Counter(row.get("label") for row in scored)
    preds = Counter(row.get("label_rag") for row in scored)
    wrong_facets = Counter(
        facet
        for row in scored
        if row.get("label") != row.get("label_rag")
        for facet in normalize_wrong_facets(row.get("wrong_facets", []))
    )
    no_evidence = sum(1 for row in scored if not row.get("top_evidence"))

    matrix = {
        true_label: {
            pred_label: sum(
                1
                for row in scored
                if row.get("label") == true_label and row.get("label_rag") == pred_label
            )
            for pred_label in VALID_LABELS
        }
        for true_label in VALID_LABELS
    }

    lines = [
        "# FacetGraphRAG Verification Report",
        "",
        "## Summary",
        "",
        f"- Total verified rows: {total_rows}",
        f"- Valid scored rows: {total}",
        f"- Unknown rows: {unknown_rows}",
        f"- Error rows: {error_rows}",
        f"- Valid coverage: {pct(safe_div(total, total_rows))}",
        f"- Correct: {correct}",
        f"- Accuracy: {pct(safe_div(correct, total))}",
        f"- No-evidence rows in scored set: {no_evidence}",
        "",
        "## Label Counts",
        "",
        "| Label | Gold | Predicted |",
        "|---|---:|---:|",
    ]
    for label in VALID_LABELS:
        lines.append(f"| {label} | {labels.get(label, 0)} | {preds.get(label, 0)} |")

    lines.extend(["", "## Per-Label Metrics", "", "| Label | Precision | Recall | F1 |", "|---|---:|---:|---:|"])
    for label in VALID_LABELS:
        tp = matrix[label][label]
        fp = sum(matrix[other][label] for other in VALID_LABELS if other != label)
        fn = sum(matrix[label][other] for other in VALID_LABELS if other != label)
        precision = safe_div(tp, tp + fp)
        recall = safe_div(tp, tp + fn)
        f1 = safe_div(2 * precision * recall, precision + recall)
        lines.append(f"| {label} | {pct(precision)} | {pct(recall)} | {pct(f1)} |")

    lines.extend(["", "## Confusion Matrix", "", "| True \\ Pred | real | fake |", "|---|---:|---:|"])
    for label in VALID_LABELS:
        lines.append(f"| {label} | {matrix[label]['real']} | {matrix[label]['fake']} |")

    lines.extend(
        [
            "",
            "## Error Counts",
            "",
            f"- False real: {matrix['fake']['real']}",
            f"- False fake: {matrix['real']['fake']}",
            "",
            "## Wrong Facets Mentioned On Errors",
            "",
            "| Facet | Count |",
            "|---|---:|",
        ]
    )
    for facet, count in wrong_facets.most_common():
        lines.append(f"| {facet} | {count} |")
    if not wrong_facets:
        lines.append("| - | 0 |")

    return "\n".join(lines) + "\n"


def normalize_wrong_facets(value) -> list[str]:
    allowed = {
        "time",
        "place",
        "person",
        "organization",
        "event",
        "quantity",
        "action",
        "result",
        "concept",
        "insufficient_evidence",
    }
    if isinstance(value, str):
        raw_items = re.split(r"[|,;/\s]+", value)
    elif isinstance(value, list):
        raw_items = []
        for item in value:
            raw_items.extend(re.split(r"[|,;/\s]+", str(item)))
    else:
        raw_items = []
    output = []
    for item in raw_items:
        cleaned = item.strip().lower()
        if cleaned in allowed and cleaned not in output:
            output.append(cleaned)
    return output


def normalize_prediction(row: dict) -> str:
    label = str(row.get("label_rag") or "").lower().strip()
    if label in VALID_LABELS or label == "error":
        return label
    raw = str(row.get("raw_response") or "").lower()
    if "insufficient_evidence" in raw or "insufficient evidence" in raw:
        return "fake"
    if "fake" in label and "real" not in label:
        return "fake"
    if "real" in label and "fake" not in label:
        return "real"
    return "unknown"


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate FacetGraphRAG verified labels.")
    parser.add_argument("--config", default="configs/facet/facet.yaml")
    args = parser.parse_args()

    config = load_yaml(args.config)
    rows = load_json(config["paths"]["facet_verified"])
    report = build_report(rows)
    save_text(report, config["paths"]["accuracy_report"])
    print(report)
    print(f"Saved report to {config['paths']['accuracy_report']}")


if __name__ == "__main__":
    main()
