# FacetGraphRAG Verification Report

## Summary

- Total verified rows: 500
- Valid scored rows: 500
- Unknown rows: 0
- Error rows: 0
- Valid coverage: 100.00%
- Correct: 499
- Accuracy: 99.80%
- No-evidence rows in scored set: 0

## Label Counts

| Label | Gold | Predicted |
|---|---:|---:|
| real | 250 | 251 |
| fake | 250 | 249 |

## Per-Label Metrics

| Label | Precision | Recall | F1 |
|---|---:|---:|---:|
| real | 99.60% | 100.00% | 99.80% |
| fake | 100.00% | 99.60% | 99.80% |

## Confusion Matrix

| True \ Pred | real | fake |
|---|---:|---:|
| real | 250 | 0 |
| fake | 1 | 249 |

## Error Counts

- False real: 1
- False fake: 0

## Wrong Facets Mentioned On Errors

| Facet | Count |
|---|---:|
| - | 0 |
