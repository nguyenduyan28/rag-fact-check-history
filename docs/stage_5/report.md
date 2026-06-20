# Stage 5 Report: Entity, Event, Time, And Relation Extraction

## Summary

Stage 5 is complete.

This stage converts 540 cleaned textbook chunks into structured historical facts using Gemini through Vertex AI, then cleans the raw extraction output with deterministic postprocessing.

Main artifacts:

| Artifact | Count / Purpose |
|---|---|
| `data/outputs/corpus/chunks.json` | 540 cleaned input chunks |
| `data/outputs/graph/extracted_chunks.json` | 540 raw extracted chunk records |
| `data/outputs/graph/extraction_errors.json` | 0 current errors |
| `data/outputs/graph/extracted_chunks_cleaned.json` | 540 cleaned extracted chunk records |
| `data/outputs/reports/extraction_cleanup_report.md` | Cleanup statistics and actions |

## Problem

The Stage 3 corpus is clean and traceable, but it is still unstructured text.

Text RAG can retrieve related chunks, but it cannot explicitly represent facts such as:

```text
Nguyễn Ái Quốc --PARTICIPATED_IN--> Đại hội Tua
Đại hội Tua --OCCURRED_AT--> 1920
Chiến dịch Điện Biên Phủ --RESULTS_IN--> Hiệp định Giơnevơ
```

The main extraction problems were:

1. Vietnamese historical facts contain people, organizations, events, places, time expressions, and concepts in the same sentence.
2. Relation extraction is difficult with rules only.
3. LLM output can be invalid JSON, too long, or inconsistent.
4. OCR noise and broad textbook prose can create generic or low-value entities.
5. Full extraction must support resume because API jobs can be interrupted.

## Method

Method name:

```text
Schema-constrained LLM extraction of source-grounded Vietnamese historical facts
```

The final method has two parts:

1. LLM extraction with schema validation.
2. Deterministic cleanup before graph construction.

## Code Method: `extract_entities.py`

Implementation file:

```text
src/graph_rag/extract_entities.py
```

### Input Loading

The extractor reads cleaned chunks from:

```text
data/outputs/corpus/chunks.json
```

Each chunk includes source trace metadata:

```text
chunk_id, book, chapter, section, pages, source_pages, source_files, year_mentions, text
```

The extraction corpus is 540 chunks, not 591. The number 591 refers to the raw OCR page/file count before Stage 3 cleaning and section-aware chunking.

### Gemini Vertex Setup

The extractor uses:

```text
google-genai
Gemini Vertex AI
GOOGLE_CLOUD_PROJECT
GOOGLE_CLOUD_LOCATION
```

Configured model:

```text
gemini-2.5-flash
```

The client is thread-local so parallel workers can safely call Gemini.

### Prompt Construction

`build_prompt()` creates one prompt per chunk.

The prompt includes:

1. Allowed entity types from `configs/graph.yaml`.
2. Allowed relation types from `configs/graph.yaml`.
3. The exact JSON shape expected.
4. Chunk metadata for traceability.
5. The cleaned chunk text.

The prompt tells Gemini to:

1. Extract only source-supported facts.
2. Use local IDs like `e1`, `e2`, `e3`.
3. Use relation endpoints from entities in the same JSON.
4. Ignore OCR garbage, exercise questions, page numbers, and useless headings.
5. Return empty lists if there are no useful graph facts.

### JSON Constraint

Prompting alone was not enough.

During smoke testing, Gemini returned malformed or truncated JSON because output hit `MAX_TOKENS`.

The code resolves this with Gemini response constraints:

```text
response_mime_type = application/json
response_schema = build_response_schema(config)
thinking_budget = 0
max_output_tokens = 8192
```

Why this matters:

1. `response_mime_type` asks Gemini for JSON output.
2. `response_schema` restricts the JSON structure and allowed enum values.
3. `thinking_budget = 0` prevents hidden reasoning budget from consuming output tokens.
4. `max_output_tokens = 8192` gives enough room for extraction JSON.

This changed extraction from unstable prompt-only JSON to valid schema-constrained JSON.

### Validation

`validate_extraction()` performs local validation after Gemini responds.

Validation checks:

| Check | Behavior |
|---|---|
| Invalid entity type | Entity skipped |
| Empty entity name | Entity skipped |
| Duplicate local ID | Reassigned locally |
| Invalid relation type | Relation skipped |
| Relation endpoint missing | Relation skipped |
| Bad confidence | Coerced into `0.0` to `1.0` |
| Years in strings | Extracted as integer years where possible |

This means even if Gemini produces imperfect JSON content, the saved artifact remains structurally usable.

### Checkpointing And Resume

The extractor supports:

```text
--limit
--workers
--checkpoint-every
--no-resume
--retry-errors
--book
--confidence
--require-years
```

Main full-run command:

```bash
python3 -m src.graph_rag.extract_entities --config configs/graph.yaml --workers 2 --checkpoint-every 25
```

Retry failed chunks only:

```bash
python3 -m src.graph_rag.extract_entities --config configs/graph.yaml --retry-errors --workers 2 --checkpoint-every 25
```

The job was interrupted once and resumed safely. Current final state has 0 errors.

## Code Method: `clean_extractions.py`

Implementation file:

```text
src/graph_rag/clean_extractions.py
```

The raw Gemini extraction was valid but noisy. Gemini extracted too many generic concepts and sometimes overused specific relation types incorrectly.

The cleanup script is deterministic. It preserves the raw extraction file and writes a separate cleaned artifact.

Cleanup command:

```bash
python3 -m src.graph_rag.clean_extractions --config configs/graph.yaml
```

### Cleanup Rules

The cleanup stage performs these actions:

1. Normalize entity names and aliases.
2. Drop generic concepts such as `Khoa học` and `Lịch sử loài người`.
3. Drop very long concept names.
4. Drop low-confidence relations.
5. Merge duplicate entities inside the same chunk.
6. Drop self-loop relations.
7. Drop relations whose endpoints were removed or unknown.
8. Enforce `max_entities_per_chunk = 12`.
9. Enforce `max_relations_per_chunk = 20`.
10. Fix safe direction errors for `OCCURRED_AT` and `PARTICIPATED_IN`.
11. Convert unsafe specific relations to `RELATED_TO`.

### Why Relation Downgrading Was Needed

Raw extraction showed that Gemini often extracted useful descriptions but assigned overly specific relation types.

Example problem:

```text
Time --OCCURRED_AT--> Organization
```

This is not a valid historical graph pattern. If the safe target event is not clear, cleanup converts the relation to:

```text
RELATED_TO
```

This loses some specificity but avoids building a graph with false typed edges.

## Result Analysis

### Raw Extraction Result

| Metric | Count |
|---|---:|
| Input chunks | 540 |
| Extracted chunks | 540 |
| Extraction errors | 0 |
| Raw entities | 6029 |
| Raw relations | 5057 |

The successful `540/540` completion means Stage 5 extraction is operational across the full cleaned corpus.

### Cleaned Extraction Result

| Metric | Count |
|---|---:|
| Cleaned chunks | 540 |
| Clean entities | 5866 |
| Clean relations | 4867 |
| Rows with no entities | 0 |
| Rows with no relations | 0 |

Cleanup removed:

```text
163 entities
190 relations
```

This is not a large reduction, which means most Gemini output was structurally acceptable. The main cleanup value is not only deletion; it is relation repair and type safety.

### Cleaned Entity Type Distribution

| Type | Count |
|---|---:|
| Place | 1313 |
| Time | 1148 |
| Concept | 1119 |
| Event | 925 |
| Organization | 906 |
| Person | 455 |

Analysis:

1. `Place` and `Time` are high, which is expected for history textbooks.
2. `Concept` remains high and should be watched during retrieval because broad concepts can create noisy graph matches.
3. `Person` is lower than places and times, which is reasonable because many chunks describe movements, organizations, and periods rather than only individuals.

### Cleaned Relation Type Distribution

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

Analysis:

`RELATED_TO` dominates the cleaned graph facts:

```text
2973 / 4867 relations
```

This shows that Gemini can identify related historical facts, but many relations are not safe enough to keep as specific typed edges after validation.

This is acceptable for the first graph build because `RELATED_TO` still supports graph neighborhood retrieval, but it limits precise reasoning over relation types.

### Cleanup Action Analysis

Important cleanup counts:

| Action | Count | Meaning |
|---|---:|---|
| `fix_occurred_at_to_related_to` | 731 | Many `OCCURRED_AT` edges had non-event sources. |
| `fix_located_in_to_related_to` | 502 | Many `LOCATED_IN` edges were not place-to-place. |
| `fix_located_in_to_occurred_at` | 254 | Some event-to-place relations were repaired. |
| `fix_participated_in_to_related_to` | 159 | Some participation edges had invalid source/target types. |
| `fix_swap_participated_in` | 47 | Some event/person directions were reversed and repaired. |
| `fix_swap_occurred_at` | 32 | Some place/time-to-event directions were reversed and repaired. |
| `drop_entity_over_chunk_cap` | 150 | Entity cap enforced. |
| `drop_relation_endpoint_removed_by_cap` | 150 | Relations linked to capped-out entities removed. |

Interpretation:

Gemini extraction was useful but relation typing was imperfect. Deterministic cleanup makes the output safer for Stage 6 and Stage 7.

## Quality Assessment

Strengths:

1. Full extraction completed over all 540 cleaned chunks.
2. Current error file has 0 errors.
3. JSON output is structurally valid.
4. All chunks have entities and relations after cleanup.
5. Caps are enforced in the cleaned artifact.
6. Broken relation endpoints are removed.
7. Raw extraction is preserved for audit.

Weaknesses:

1. `RELATED_TO` dominates the relation set.
2. Some broad concepts remain and may hurt retrieval precision.
3. Entity aliases are not merged across chunks yet.
4. `Mỹ`, `Mĩ`, and `Hoa Kỳ` are still separate until Stage 6.
5. `Nguyễn Ái Quốc` and `Hồ Chí Minh` require careful historical alias alignment.

## Conclusion

Stage 5 successfully converts cleaned textbook chunks into structured, source-grounded extraction records.

The cleaned output is ready for Stage 6 entity alignment:

```text
data/outputs/graph/extracted_chunks_cleaned.json
```

It should not be treated as the final graph yet. It is the cleaned extraction layer that Stage 6 will normalize and merge into canonical graph entities.

Next stage:

```text
Stage 6: Entity Alignment
```
