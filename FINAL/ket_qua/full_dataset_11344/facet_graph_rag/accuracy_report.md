# FacetGraphRAG Verification Report

## Summary

- Total verified rows: 11344
- Valid scored rows: 11341
- Unknown rows: 0
- Error rows: 3
- Valid coverage: 99.97%
- Correct: 9238
- Accuracy: 81.46%
- No-evidence rows in scored set: 0

## Label Counts

| Label | Gold | Predicted |
|---|---:|---:|
| real | 3511 | 4214 |
| fake | 7830 | 7127 |

## Per-Label Metrics

| Label | Precision | Recall | F1 |
|---|---:|---:|---:|
| real | 66.71% | 80.06% | 72.78% |
| fake | 90.18% | 82.08% | 85.94% |

## Confusion Matrix

| True \ Pred | real | fake |
|---|---:|---:|
| real | 2811 | 700 |
| fake | 1403 | 6427 |

## Error Counts

- False real: 1403
- False fake: 700

## Wrong Facets Mentioned On Errors

| Facet | Count |
|---|---:|
| time | 227 |
| result | 163 |
| action | 162 |
| place | 151 |
| insufficient_evidence | 147 |
| concept | 125 |
| event | 106 |
| person | 87 |
| organization | 76 |
| quantity | 45 |
