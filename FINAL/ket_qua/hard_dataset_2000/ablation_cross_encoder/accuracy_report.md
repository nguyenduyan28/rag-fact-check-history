# FacetGraphRAG Verification Report

## Summary

- Total verified rows: 2000
- Valid scored rows: 2000
- Unknown rows: 0
- Error rows: 0
- Valid coverage: 100.00%
- Correct: 1643
- Accuracy: 82.15%
- 
- No-evidence rows in scored set: 0

## Label Counts

| Label | Gold | Predicted |
|---|---:|---:|
| real | 1000 | 1043 |
| fake | 1000 | 957 |

## Per-Label Metrics

| Label | Precision | Recall | F1 |
|---|---:|---:|---:|
| real | 80.82% | 84.30% | 82.53% |
| fake | 83.59% | 80.00% | 81.76% |

## Confusion Matrix

| True \ Pred | real | fake |
|---|---:|---:|
| real | 843 | 157 |
| fake | 200 | 800 |

## Error Counts

- False real: 200
- False fake: 157

## Wrong Facets Mentioned On Errors

| Facet | Count |
|---|---:|
| time | 45 |
| concept | 37 |
| result | 32 |
| place | 31 |
| insufficient_evidence | 27 |
| action | 26 |
| event | 26 |
| person | 14 |
| organization | 12 |
| quantity | 9 |
