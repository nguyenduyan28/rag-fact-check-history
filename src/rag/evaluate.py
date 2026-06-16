import argparse

from src.common.io import load_json, load_yaml, save_text
from src.common.metrics import build_classification_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate RAG verification outputs.")
    parser.add_argument("--config", default="configs/eval.yaml")
    args = parser.parse_args()

    config = load_yaml(args.config)
    rows = load_json(config["paths"]["input_verified"])
    report = build_classification_report(rows, prediction_field="label_rag")
    print(report)
    save_text(report, config["paths"]["output_report"])
    print(f"Saved report to {config['paths']['output_report']}")


if __name__ == "__main__":
    main()
