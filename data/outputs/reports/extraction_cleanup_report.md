# Extraction Cleanup Report

## Summary

- Input chunks: 540
- Output chunks: 540
- Raw entities: 6029
- Clean entities: 5866
- Raw relations: 5057
- Clean relations: 4867
- Rows with no entities after cleanup: 0
- Rows with no relations after cleanup: 0

## Entity Types

| Type | Count |
|---|---:|
| Place | 1313 |
| Time | 1148 |
| Concept | 1119 |
| Event | 925 |
| Organization | 906 |
| Person | 455 |

## Relation Types

| Type | Count |
|---|---:|
| RELATED_TO | 2973 |
| RESULTS_IN | 570 |
| OCCURRED_AT | 544 |
| CAUSES | 320 |
| PARTICIPATED_IN | 223 |
| LOCATED_IN | 124 |
| AFTER | 67 |
| BEFORE | 46 |

## Cleanup Actions

| Action | Count |
|---|---:|
| `drop_duplicate_relation_in_chunk` | 1 |
| `drop_entity_generic_concept` | 9 |
| `drop_entity_long_concept_name` | 3 |
| `drop_entity_over_chunk_cap` | 150 |
| `drop_relation_endpoint_removed_by_cap` | 150 |
| `drop_relation_low_confidence` | 7 |
| `drop_relation_self_loop` | 12 |
| `drop_relation_unknown_endpoint` | 20 |
| `fix_after_to_related_to` | 126 |
| `fix_before_to_related_to` | 41 |
| `fix_located_in_to_occurred_at` | 254 |
| `fix_located_in_to_related_to` | 502 |
| `fix_occurred_at_to_related_to` | 731 |
| `fix_participated_in_to_related_to` | 159 |
| `fix_swap_occurred_at` | 32 |
| `fix_swap_participated_in` | 47 |
| `merge_duplicate_entity_in_chunk` | 1 |
