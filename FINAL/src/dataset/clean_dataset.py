"""
Clean dataset claims.

File nay dung de:
- Doc dataset JSON va cac duong dan input/output tu configs/dataset.yaml
- Loai claim bi gan nhieu label khac nhau
- Loai claim lap, giu ban dau tien
- Ghi dataset da clean va report thong ke

Command:
    python3 src/dataset/clean_dataset.py
    python3 src/dataset/clean_dataset.py --config configs/dataset.yaml

Input:
    configs/dataset.yaml -> input_path

Output:
    configs/dataset.yaml -> output_path, report_path
"""
import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT_DIR / "configs" / "dataset.yaml"


def resolve_path(path: str | Path) -> Path:
    path = Path(path)
    if path.is_absolute():
        return path
    return ROOT_DIR / path


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()


def load_config(config_path: Path) -> dict[str, Any]:
    with config_path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}

    required_keys = ["input_path", "output_path", "report_path"]
    missing = [key for key in required_keys if key not in config]
    if missing:
        raise ValueError(f"Missing config keys: {', '.join(missing)}")

    return config


def load_dataset(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError("Input dataset must be a JSON list.")

    return data


def validate_required_fields(
    rows: list[dict[str, Any]], required_fields: list[str]
) -> list[dict[str, Any]]:
    invalid_rows = []

    for index, row in enumerate(rows):
        missing = [
            field
            for field in required_fields
            if field not in row or normalize_text(row[field]) == ""
        ]
        if missing:
            invalid_rows.append({"index": index, "missing_fields": missing})

    return invalid_rows


def clean_dataset(
    rows: list[dict[str, Any]],
    deduplicate_by: str,
    conflict_strategy: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[normalize_text(row[deduplicate_by])].append(row)

    cleaned = []
    conflict_claims = []
    duplicate_rows_removed = 0

    for value, group in groups.items():
        labels = {normalize_text(row["label"]) for row in group}

        if len(labels) > 1:
            conflict_claims.append(
                {
                    deduplicate_by: value,
                    "labels": sorted(labels),
                    "count": len(group),
                    "ids": [row.get("ID") for row in group],
                }
            )
            if conflict_strategy == "drop_all":
                continue

        cleaned.append(group[0])
        duplicate_rows_removed += len(group) - 1

    report = {
        "input_rows": len(rows),
        "output_rows": len(cleaned),
        "removed_rows": len(rows) - len(cleaned),
        "duplicate_rows_removed": duplicate_rows_removed,
        "conflict_groups_removed": len(conflict_claims),
        "label_counts_before": dict(Counter(row["label"] for row in rows)),
        "label_counts_after": dict(Counter(row["label"] for row in cleaned)),
        "unique_keys_before": len({row["key"] for row in rows}),
        "unique_keys_after": len({row["key"] for row in cleaned}),
        "deduplicate_by": deduplicate_by,
        "conflict_strategy": conflict_strategy,
        "conflicts": conflict_claims,
    }
    return cleaned, report


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean dataset claims.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to YAML config.")
    args = parser.parse_args()

    config = load_config(resolve_path(args.config))
    input_path = resolve_path(config["input_path"])
    output_path = resolve_path(config["output_path"])
    report_path = resolve_path(config["report_path"])

    rows = load_dataset(input_path)
    required_fields = config.get("required_fields", ["ID", "key", "claim", "relevant", "label"])
    invalid_rows = validate_required_fields(rows, required_fields)
    if invalid_rows:
        raise ValueError(f"Found rows with missing fields: {invalid_rows[:5]}")

    cleaned, report = clean_dataset(
        rows=rows,
        deduplicate_by=config.get("deduplicate_by", "claim"),
        conflict_strategy=config.get("conflict_strategy", "drop_all"),
    )

    save_json(output_path, cleaned)
    save_json(report_path, report)

    print(f"Input rows: {report['input_rows']}")
    print(f"Output rows: {report['output_rows']}")
    print(f"Removed rows: {report['removed_rows']}")
    print(f"Output: {output_path.relative_to(ROOT_DIR)}")
    print(f"Report: {report_path.relative_to(ROOT_DIR)}")


if __name__ == "__main__":
    main()
