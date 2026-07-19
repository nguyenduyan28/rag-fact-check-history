# FacetGraphRAG Verification Report

## Summary

- Total verified rows: 2000
- Valid scored rows: 2000
- Unknown rows: 0
- Error rows: 0
- Valid coverage: 100.00%
- Correct: 1692
- Accuracy: 84.60%
- No-evidence rows in scored set: 0

## Label Counts

| Label | Gold | Predicted |
|---|---:|---:|
| real | 1000 | 888 |
| fake | 1000 | 1112 |

## Per-Label Metrics

| Label | Precision | Recall | F1 |
|---|---:|---:|---:|
| real | 88.96% | 79.00% | 83.69% |
| fake | 81.12% | 90.20% | 85.42% |

## Confusion Matrix

| True \ Pred | real | fake |
|---|---:|---:|
| real | 790 | 210 |
| fake | 98 | 902 |

## Error Counts

- False real: 98
- False fake: 210

## Wrong Facets Mentioned On Errors

| Facet | Count |
|---|---:|
| time | 70 |
| insufficient_evidence | 55 |
| event | 39 |
| concept | 35 |
| place | 26 |
| action | 16 |
| quantity | 11 |
| organization | 10 |
| result | 7 |
| person | 6 |
