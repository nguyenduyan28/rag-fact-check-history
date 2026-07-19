# FacetGraphRAG Verification Report

## Summary

- Total verified rows: 2000
- Valid scored rows: 2000
- Unknown rows: 0
- Error rows: 0
- Valid coverage: 100.00%
- Correct: 1434
- Accuracy: 71.70%
- No-evidence rows in scored set: 0

## Label Counts

| Label | Gold | Predicted |
|---|---:|---:|
| real | 1000 | 550 |
| fake | 1000 | 1450 |

## Per-Label Metrics

| Label | Precision | Recall | F1 |
|---|---:|---:|---:|
| real | 89.45% | 49.20% | 63.48% |
| fake | 64.97% | 94.20% | 76.90% |

## Confusion Matrix

| True \ Pred | real | fake |
|---|---:|---:|
| real | 492 | 508 |
| fake | 58 | 942 |

## Error Counts

- False real: 58
- False fake: 508

## Wrong Facets Mentioned On Errors

| Facet | Count |
|---|---:|
| action | 196 |
| insufficient_evidence | 127 |
| concept | 121 |
| time | 101 |
| result | 78 |
| organization | 56 |
| event | 54 |
| place | 51 |
| quantity | 35 |
| person | 21 |
