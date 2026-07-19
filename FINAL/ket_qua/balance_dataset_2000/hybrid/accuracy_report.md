# FacetGraphRAG Verification Report

## Summary

- Total verified rows: 2000
- Valid scored rows: 2000
- Unknown rows: 0
- Error rows: 0
- Valid coverage: 100.00%
- Correct: 1741
- Accuracy: 87.05%
- No-evidence rows in scored set: 0

## Label Counts

| Label | Gold | Predicted |
|---|---:|---:|
| real | 1000 | 1011 |
| fake | 1000 | 989 |

## Per-Label Metrics

| Label | Precision | Recall | F1 |
|---|---:|---:|---:|
| real | 86.65% | 87.60% | 87.12% |
| fake | 87.46% | 86.50% | 86.98% |

## Confusion Matrix

| True \ Pred | real | fake |
|---|---:|---:|
| real | 876 | 124 |
| fake | 135 | 865 |

## Error Counts

- False real: 135
- False fake: 124

## Wrong Facets Mentioned On Errors

| Facet | Count |
|---|---:|
| time | 38 |
| place | 26 |
| action | 26 |
| event | 22 |
| result | 22 |
| concept | 21 |
| insufficient_evidence | 10 |
| quantity | 9 |
| organization | 7 |
| person | 1 |
