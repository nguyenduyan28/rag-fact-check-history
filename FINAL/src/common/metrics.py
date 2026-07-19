from typing import Iterable

from sklearn.metrics import accuracy_score, classification_report, confusion_matrix


VALID_LABELS = ["real", "fake"]


def build_classification_report(rows: Iterable[dict], prediction_field: str = "label_rag") -> str:
    scored = [
        row
        for row in rows
        if row.get("label") in VALID_LABELS and row.get(prediction_field) in VALID_LABELS
    ]
    if not scored:
        return "No valid scored rows found.\n"

    y_true = [row["label"] for row in scored]
    y_pred = [row[prediction_field] for row in scored]
    accuracy = accuracy_score(y_true, y_pred)
    matrix = confusion_matrix(y_true, y_pred, labels=VALID_LABELS)
    report = classification_report(y_true, y_pred, labels=VALID_LABELS, zero_division=0)

    lines = []
    lines.append("RAG VERIFICATION REPORT")
    lines.append("=" * 40)
    lines.append(f"Total valid scored rows: {len(scored)}")
    lines.append(f"Accuracy: {accuracy:.4f} ({accuracy * 100:.2f}%)")
    lines.append("")
    lines.append("Classification report")
    lines.append("-" * 40)
    lines.append(report)
    lines.append("Confusion matrix rows=true cols=pred")
    lines.append("-" * 40)
    lines.append(f"labels: {VALID_LABELS}")
    lines.append(str(matrix))
    lines.append("")
    lines.append(f"False real: {sum(1 for row in scored if row['label'] == 'fake' and row[prediction_field] == 'real')}")
    lines.append(f"False fake: {sum(1 for row in scored if row['label'] == 'real' and row[prediction_field] == 'fake')}")
    return "\n".join(lines) + "\n"
