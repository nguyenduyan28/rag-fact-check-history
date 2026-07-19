# FacetGraphRAG Verification Report

## Summary

- Total verified rows: 2000
- Valid scored rows: 2000
- Unknown rows: 0
- Error rows: 0
- Valid coverage: 100.00%
- Correct: 1657
- Accuracy: 82.85%
- No-evidence rows in scored set: 0

## Label Counts

| Label | Gold | Predicted |
|---|---:|---:|
| real | 1000 | 1065 |
| fake | 1000 | 935 |

## Per-Label Metrics

| Label | Precision | Recall | F1 |
|---|---:|---:|---:|
| real | 80.85% | 86.10% | 83.39% |
| fake | 85.13% | 79.60% | 82.27% |

## Confusion Matrix

| True \ Pred | real | fake |
|---|---:|---:|
| real | 861 | 139 |
| fake | 204 | 796 |

## Error Counts

- False real: 204
- False fake: 139

## Wrong Facets Mentioned On Errors

| Facet | Count |
|---|---:|
| time | 38 |
| concept | 35 |
| place | 32 |
| result | 32 |
| action | 24 |
| insufficient_evidence | 21 |
| event | 17 |
| person | 15 |
| organization | 12 |
| quantity | 7 |
