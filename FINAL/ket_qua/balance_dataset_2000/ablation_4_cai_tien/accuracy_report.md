# FacetGraphRAG Verification Report

## Summary

- Total verified rows: 2000
- Valid scored rows: 1998
- Unknown rows: 0
- Error rows: 2
- Valid coverage: 99.90%
- Correct: 1595
- Accuracy: 79.83%
- No-evidence rows in scored set: 0

## Label Counts

| Label | Gold | Predicted |
|---|---:|---:|
| real | 999 | 836 |
| fake | 999 | 1162 |

## Per-Label Metrics

| Label | Precision | Recall | F1 |
|---|---:|---:|---:|
| real | 85.65% | 71.67% | 78.04% |
| fake | 75.65% | 87.99% | 81.35% |

## Confusion Matrix

| True \ Pred | real | fake |
|---|---:|---:|
| real | 716 | 283 |
| fake | 120 | 879 |

## Error Counts

- False real: 120
- False fake: 283

## Wrong Facets Mentioned On Errors

| Facet | Count |
|---|---:|
| time | 86 |
| action | 68 |
| insufficient_evidence | 60 |
| result | 54 |
| place | 51 |
| concept | 44 |
| event | 38 |
| quantity | 24 |
| organization | 24 |
| person | 7 |
