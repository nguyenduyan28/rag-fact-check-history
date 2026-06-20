# Stage 4 Report: Historical Graph Schema

## Summary

Stage 4 is complete.

This stage defines the graph schema used by the GraphRAG pipeline. The schema is not only documentation; it is also the contract used by Stage 5 extraction code to decide which entity and relation types are valid.

Main artifacts:

| Artifact | Purpose |
|---|---|
| `docs/graph_schema.md` | Human-readable graph schema and extraction contract. |
| `configs/graph.yaml` | Machine-readable schema configuration used by code. |

## Problem

The Stage 3 output is clean text chunks, not structured knowledge.

For GraphRAG, plain chunks are not enough because claim verification often depends on structured historical signals:

1. Who participated in an event.
2. Where an event happened.
3. When an event happened.
4. What caused or resulted from an event.
5. Which names refer to the same historical entity.

Without a schema, Gemini extraction would produce inconsistent JSON across chunks. Later graph stages would then need to guess which fields and relation types are valid.

## Method

We use a compact source-grounded historical graph schema.

Method name:

```text
Source-grounded historical graph schema for Vietnamese textbook GraphRAG
```

The schema has two layers:

| Layer | Location | Role |
|---|---|---|
| Documentation layer | `docs/graph_schema.md` | Explains node types, edge types, fields, and extraction rules. |
| Config layer | `configs/graph.yaml` | Supplies allowed types to extraction and cleanup code. |

## Node Design

Configured node types:

```text
DocumentChunk, Person, Organization, Event, Place, Time, Concept
```

Important design decision:

```text
The LLM does not extract DocumentChunk nodes.
```

Reason:

`DocumentChunk` nodes are already known from `data/outputs/corpus/chunks.json`. They should be created deterministically during graph building, not hallucinated by the LLM.

LLM-extracted entity types are therefore limited to:

```text
Person, Organization, Event, Place, Time, Concept
```

This keeps extraction focused on historical facts instead of graph infrastructure.

## Edge Design

Configured edge types:

```text
MENTIONS, PARTICIPATED_IN, OCCURRED_AT, LOCATED_IN, RELATED_TO, CAUSES, RESULTS_IN, BEFORE, AFTER, SUPPORTED_BY
```

Important design decision:

```text
The LLM does not extract MENTIONS or SUPPORTED_BY edges.
```

Reason:

`MENTIONS` and `SUPPORTED_BY` are provenance edges. They should be created deterministically from chunk IDs and source metadata. Letting the LLM create them would make citation and provenance less reliable.

LLM-extracted relation types are therefore limited to:

```text
PARTICIPATED_IN, OCCURRED_AT, LOCATED_IN, RELATED_TO, CAUSES, RESULTS_IN, BEFORE, AFTER
```

## Why RELATED_TO Exists

Vietnamese textbook OCR is noisy, and historical relations are often expressed broadly.

If we force every relation into a specific type, the graph becomes falsely precise. For example, Gemini may incorrectly label an organization-to-time relation as `OCCURRED_AT`.

`RELATED_TO` is the safe fallback relation for source-supported facts where the exact relation type is uncertain.

This is a deliberate tradeoff:

| Choice | Benefit | Risk |
|---|---|---|
| Use `RELATED_TO` fallback | Safer graph, fewer invalid typed edges | Less semantic specificity |
| Force only specific relations | More expressive graph | More wrong relation types |

For this project stage, safety is more important than false precision.

## Required Extraction Fields

Each extracted entity must contain:

```text
local_id, type, name, aliases, description, years, evidence_text, confidence
```

Each extracted relation must contain:

```text
source, target, type, description, evidence_text, confidence
```

These fields were chosen because later stages need:

| Field | Later Use |
|---|---|
| `local_id` | Connect relations to entities inside one chunk. |
| `type` | Build typed nodes and edges. |
| `name` | Entity alignment and alias matching. |
| `aliases` | Canonical entity merging. |
| `description` | Graph fact text for retrieval and verifier context. |
| `years` | Temporal index and year-aware retrieval. |
| `evidence_text` | Auditability and source grounding. |
| `confidence` | Filtering noisy extractions. |

## Code Impact

Stage 4 directly affects Stage 5 code.

In `src/graph_rag/extract_entities.py`:

1. `allowed_types(config)` reads node and edge types from `configs/graph.yaml`.
2. `DocumentChunk`, `MENTIONS`, and `SUPPORTED_BY` are excluded from LLM extraction.
3. `build_prompt()` injects the allowed entity and relation types into the Gemini prompt.
4. `build_response_schema()` creates a Gemini JSON response schema from those allowed types.
5. `validate_extraction()` rejects invalid entity types, invalid relation types, and broken relation endpoints.

This means the schema is not passive documentation. It actively constrains extraction behavior.

## Result

Stage 4 produced a stable extraction contract.

Completed checklist:

| Item | Status |
|---|---|
| Create `docs/graph_schema.md` | Done |
| Align schema with `configs/graph.yaml` | Done |
| Define node types | Done |
| Define edge types | Done |
| Define required entity fields | Done |
| Define required relation fields | Done |

## Quality Assessment

The schema is appropriate for the current corpus size and project stage.

Strengths:

1. Small enough for reliable LLM extraction.
2. Expressive enough for historical claim verification.
3. Keeps provenance deterministic.
4. Supports temporal retrieval through `Time` nodes and `years` fields.
5. Supports later entity alignment through `name` and `aliases` fields.

Weaknesses:

1. `RELATED_TO` is broad and may dominate the graph.
2. `Concept` can become noisy if not filtered.
3. The schema does not yet define final canonical IDs for aligned entities.
4. Cross-chunk alias merging is deferred to Stage 6.

## Conclusion

Stage 4 is complete and sufficient for Stage 5 extraction.

The schema should not be treated as final production ontology. It is a practical graph contract for building the first auditable Vietnamese historical GraphRAG pipeline.

Next stage:

```text
Stage 5: Entity/Event/Time Extraction
```
