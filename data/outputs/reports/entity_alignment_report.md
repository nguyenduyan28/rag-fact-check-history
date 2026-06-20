# Entity Alignment Report

## Summary

- Raw entity mentions: 5866
- Unique normalized type/name entities: 3742
- Exact normalized mentions collapsed: 2124
- Candidate groups generated: 150
- Gemini used: yes
- Gemini decisions: 0
- Gemini errors: 150
- Accepted Gemini merge decisions: 0
- Rejected/low-confidence merge decisions: 0
- Final aligned entities: 3742
- Unique representatives merged beyond exact normalization: 0
- Alias rows: 3742
- Aligned entities with multiple aliases: 373

## Raw Entity Types

| Type | Count |
|---|---:|
| Place | 1313 |
| Time | 1148 |
| Concept | 1119 |
| Event | 925 |
| Organization | 906 |
| Person | 455 |

## Aligned Entity Types

| Type | Count |
|---|---:|
| Concept | 865 |
| Time | 862 |
| Event | 707 |
| Place | 521 |
| Organization | 473 |
| Person | 314 |

## Accepted Merge Examples

- None

## Output Artifacts

- `data/outputs/graph/entities_raw.json`
- `data/outputs/graph/entities_aligned.json`
- `data/outputs/graph/entity_aliases.json`
- `data/outputs/graph/entity_alignment_decisions.json`
- `data/outputs/graph/entity_alignment_errors.json`
