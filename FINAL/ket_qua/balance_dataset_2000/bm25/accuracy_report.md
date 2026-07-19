# FacetGraphRAG Verification Report

## Summary

- Total verified rows: 2000
- Valid scored rows: 2000
- Unknown rows: 0
- Error rows: 0
- Valid coverage: 100.00%
- Correct: 1749
- Accuracy: 87.45%
- No-evidence rows in scored set: 0

## Label Counts

| Label | Gold | Predicted |
|---|---:|---:|
| real | 1000 | 963 |
| fake | 1000 | 1037 |

## Per-Label Metrics

| Label | Precision | Recall | F1 |
|---|---:|---:|---:|
| real | 88.89% | 85.60% | 87.21% |
| fake | 86.11% | 89.30% | 87.68% |

## Confusion Matrix

| True \ Pred | real | fake |
|---|---:|---:|
| real | 856 | 144 |
| fake | 107 | 893 |

## Error Counts

- False real: 107
- False fake: 144

## Wrong Facets Mentioned On Errors

| Facet | Count |
|---|---:|
| time | 49 |
| place | 27 |
| insufficient_evidence | 27 |
| concept | 27 |
| event | 23 |
| action | 11 |
| result | 8 |
| organization | 7 |
| quantity | 5 |
| person | 1 |
