# FacetGraphRAG Verification Report

## Summary

- Total verified rows: 2000
- Valid scored rows: 2000
- Unknown rows: 0
- Error rows: 0
- Valid coverage: 100.00%
- Correct: 1762
- Accuracy: 88.10%
- No-evidence rows in scored set: 0

## Label Counts

| Label | Gold | Predicted |
|---|---:|---:|
| real | 1000 | 960 |
| fake | 1000 | 1040 |

## Per-Label Metrics

| Label | Precision | Recall | F1 |
|---|---:|---:|---:|
| real | 89.69% | 86.10% | 87.86% |
| fake | 86.63% | 90.10% | 88.33% |

## Confusion Matrix

| True \ Pred | real | fake |
|---|---:|---:|
| real | 861 | 139 |
| fake | 99 | 901 |

## Error Counts

- False real: 99
- False fake: 139

## Wrong Facets Mentioned On Errors

| Facet | Count |
|---|---:|
| time | 43 |
| concept | 30 |
| event | 26 |
| place | 21 |
| insufficient_evidence | 20 |
| action | 13 |
| organization | 6 |
| result | 6 |
| quantity | 5 |
| person | 4 |
