# FacetGraphRAG Verification Report

## Summary

- Total verified rows: 11344
- Valid scored rows: 11344
- Unknown rows: 0
- Error rows: 0
- Valid coverage: 100.00%
- Correct: 8748
- Accuracy: 77.12%
- No-evidence rows in scored set: 467

## Label Counts

| Label | Gold | Predicted |
|---|---:|---:|
| real | 3514 | 3218 |
| fake | 7830 | 8126 |

## Per-Label Metrics

| Label | Precision | Recall | F1 |
|---|---:|---:|---:|
| real | 64.26% | 58.85% | 61.44% |
| fake | 82.21% | 85.31% | 83.73% |

## Confusion Matrix

| True \ Pred | real | fake |
|---|---:|---:|
| real | 2068 | 1446 |
| fake | 1150 | 6680 |

## Error Counts

- False real: 1150
- False fake: 1446

## Wrong Facets Mentioned On Errors

| Facet | Count |
|---|---:|
| insufficient_evidence | 1331 |
| result | 116 |
| action | 103 |
| time | 70 |
| place | 35 |
| quantity | 27 |
| event | 18 |
| concept | 12 |
| organization | 10 |
| person | 6 |
