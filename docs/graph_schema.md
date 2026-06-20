# Historical Graph Schema

This document defines the graph schema used by the GraphRAG pipeline. It is the human-readable contract for `configs/graph.yaml`, which provides the machine-readable allowed node and edge types used by extraction and graph construction code.

The schema is intentionally compact. It is designed for Vietnamese history textbook facts, source-grounded extraction, entity alignment, graph retrieval, and later verification.

## Scope

The graph has two layers:

| Layer | Built By | Purpose |
|---|---|---|
| Corpus layer | Deterministic code | Represents cleaned textbook chunks and provenance. |
| Historical fact layer | Gemini extraction plus cleanup | Represents people, organizations, events, places, times, concepts, and relations extracted from chunks. |

The LLM extracts only historical fact layer entities and relations. It does not create corpus/provenance infrastructure nodes or edges.

## Node Types

The configured node types are:

```text
DocumentChunk
Person
Organization
Event
Place
Time
Concept
```

### `DocumentChunk`

A cleaned, section-aware textbook chunk from `data/outputs/corpus/chunks.json`.

`DocumentChunk` nodes are created deterministically during graph building. Gemini must not extract them.

Typical source fields:

```text
chunk_id, chunk_type, book, chapter, section, pages, source_pages, source_files, text
```

### `Person`

A historical individual.

Examples:

```text
Hồ Chí Minh
Nguyễn Ái Quốc
Võ Nguyên Giáp
```

Aliases should be preserved for Stage 6 entity alignment. For example, `Nguyễn Ái Quốc` and `Hồ Chí Minh` may be aligned as the same person only when context supports it.

### `Organization`

A political, military, social, state, party, or international organization.

Examples:

```text
Đảng Cộng sản Việt Nam
Đảng Cộng sản Đông Dương
Liên Xô
Hoa Kỳ
Việt Minh
```

Do not merge historically related organizations unless they are truly the same entity in context.

### `Event`

A historical event, campaign, movement, revolution, war, treaty, conference, congress, uprising, reform, or process with historical significance.

Examples:

```text
Cách mạng tháng Tám
Chiến dịch Điện Biên Phủ
Hội nghị Ianta
Hiệp định Giơnevơ
```

Events should include year metadata when the source chunk supports it.

### `Place`

A geographic place, region, country, city, battlefield, or historically meaningful location.

Examples:

```text
Việt Nam
Đông Dương
Hà Nội
Điện Biên Phủ
An Nam
```

Historical names such as `An Nam` should not be blindly merged with modern names. Stage 6 alignment should use context and confidence.

### `Time`

A date, year, period, era, or time expression.

Examples:

```text
1945
tháng 8 năm 1945
cuối thế kỉ XIX
```

Use integer years when directly supported by the source text.

### `Concept`

A historically meaningful concept, policy, ideology, social formation, economic system, or abstract historical category.

Examples:

```text
chủ nghĩa xã hội
phong trào giải phóng dân tộc
chiến tranh lạnh
```

Concepts can become noisy, so broad generic concepts should be filtered during cleanup when they do not help graph retrieval.

## Edge Types

The configured edge types are:

```text
MENTIONS
PARTICIPATED_IN
OCCURRED_AT
LOCATED_IN
RELATED_TO
CAUSES
RESULTS_IN
BEFORE
AFTER
SUPPORTED_BY
```

### `MENTIONS`

Connects a `DocumentChunk` to an entity mentioned in that chunk.

Direction:

```text
DocumentChunk -> Person|Organization|Event|Place|Time|Concept
```

This edge is deterministic. Gemini must not extract it.

### `PARTICIPATED_IN`

Connects a person or organization to an event they participated in, led, joined, organized, or otherwise directly took part in.

Direction:

```text
Person|Organization -> Event
```

### `OCCURRED_AT`

Connects an event to a place or time where/when it occurred.

Direction:

```text
Event -> Place|Time
```

### `LOCATED_IN`

Connects one place to a containing or associated place.

Direction:

```text
Place -> Place
```

Use `OCCURRED_AT` instead when the source is an event.

### `RELATED_TO`

A safe fallback edge for source-supported historical relationships that do not fit a more specific type with confidence.

Direction:

```text
Any extracted entity type -> Any extracted entity type
```

This relation should be used when a relation is real and source-grounded but the exact semantic type is uncertain.

### `CAUSES`

Connects a cause to a resulting event, process, or concept.

Direction:

```text
Event|Concept|Organization|Person -> Event|Concept
```

Only use when causal language is supported by the source text.

### `RESULTS_IN`

Connects an event, process, policy, or action to its result.

Direction:

```text
Event|Concept|Organization|Person -> Event|Concept
```

Only use when result language is supported by the source text.

### `BEFORE`

Connects an event or time expression to another event or time expression that happened later.

Direction:

```text
Event|Time -> Event|Time
```

### `AFTER`

Connects an event or time expression to another event or time expression that happened earlier.

Direction:

```text
Event|Time -> Event|Time
```

### `SUPPORTED_BY`

Connects a graph fact to a source chunk that supports it.

Direction:

```text
Entity|RelationFact -> DocumentChunk
```

This edge is deterministic provenance. Gemini must not extract it.

## LLM Extraction Contract

Gemini extraction is constrained by `configs/graph.yaml` and the response schema in `src/graph_rag/extract_entities.py`.

Gemini may extract only these node types:

```text
Person
Organization
Event
Place
Time
Concept
```

Gemini may extract only these relation types:

```text
PARTICIPATED_IN
OCCURRED_AT
LOCATED_IN
RELATED_TO
CAUSES
RESULTS_IN
BEFORE
AFTER
```

Gemini must not extract:

```text
DocumentChunk
MENTIONS
SUPPORTED_BY
```

Those are produced deterministically in later graph construction.

## Required Extraction Fields

Each extracted entity record must contain:

```text
local_id
type
name
aliases
description
years
evidence_text
confidence
```

Field meanings:

| Field | Meaning |
|---|---|
| `local_id` | Chunk-local ID such as `e1`, used by relations in the same extraction record. |
| `type` | One configured extractable node type. |
| `name` | Surface name from the source chunk. |
| `aliases` | Alternate names when directly supported by the source or safely known from context. |
| `description` | Short source-grounded description. |
| `years` | Integer years supported by the entity text, description, or evidence. |
| `evidence_text` | Short phrase or sentence from the chunk supporting the entity. |
| `confidence` | Float from `0.0` to `1.0`. |

Each extracted relation record must contain:

```text
source
target
type
description
evidence_text
confidence
```

Field meanings:

| Field | Meaning |
|---|---|
| `source` | Chunk-local source entity ID. |
| `target` | Chunk-local target entity ID. |
| `type` | One configured extractable edge type. |
| `description` | Short source-grounded description of the relation. |
| `evidence_text` | Short phrase or sentence from the chunk supporting the relation. |
| `confidence` | Float from `0.0` to `1.0`. |

## Final Graph Node Fields

After Stage 6 entity alignment and Stage 7 graph construction, final graph nodes should contain at least:

```text
id
type
name
aliases
description
years
source_chunks
```

Field meanings:

| Field | Meaning |
|---|---|
| `id` | Stable graph node ID. |
| `type` | Configured node type. |
| `name` | Canonical display name. |
| `aliases` | Surface names merged into the canonical entity. |
| `description` | Short merged description derived from source-grounded extraction records. |
| `years` | Sorted unique supported years. |
| `source_chunks` | Chunk IDs supporting this node. |

For `DocumentChunk`, the final graph node should preserve corpus trace metadata such as book, chapter, section, pages, source pages, source files, and text.

## Final Graph Edge Fields

After Stage 7 graph construction, final graph edges should contain at least:

```text
source
target
type
description
source_chunk
confidence
```

Field meanings:

| Field | Meaning |
|---|---|
| `source` | Source graph node ID. |
| `target` | Target graph node ID. |
| `type` | Configured edge type. |
| `description` | Source-grounded relation or provenance description. |
| `source_chunk` | Chunk ID supporting the edge. |
| `confidence` | Float from `0.0` to `1.0`. |

Edges may also include evidence text and source page metadata when useful for auditability.

## Validation Rules

Extraction and cleanup should enforce these rules:

1. Reject entities with invalid types.
2. Reject entities with empty names.
3. Reject relations with invalid types.
4. Reject relations whose endpoints do not exist in the same chunk extraction.
5. Reject self-loop relations unless a later stage explicitly justifies them.
6. Downgrade unsafe specific relations to `RELATED_TO` rather than keeping false precision.
7. Keep source evidence for every entity and relation where available.
8. Preserve original surface names for Stage 6 alignment.
9. Do not infer facts that are not supported by source text.

## Entity Alignment Notes

This schema does not define final canonical IDs before Stage 6. Stage 5 extraction keeps chunk-local entity IDs and source names. Stage 6 is responsible for aligning duplicate or alias entities across chunks.

Examples of alignment candidates:

```text
Mỹ / Mĩ / Hoa Kỳ
Liên Xô / Liên bang Xô viết
Nguyễn Ái Quốc / Hồ Chí Minh
An Nam / Việt Nam
```

Alignment should be conservative and context-aware. Related entities should not be merged only because they are historically connected.

## Config Alignment

This document is aligned with `configs/graph.yaml`:

```yaml
schema:
  node_types:
    - DocumentChunk
    - Person
    - Organization
    - Event
    - Place
    - Time
    - Concept
  edge_types:
    - MENTIONS
    - PARTICIPATED_IN
    - OCCURRED_AT
    - LOCATED_IN
    - RELATED_TO
    - CAUSES
    - RESULTS_IN
    - BEFORE
    - AFTER
    - SUPPORTED_BY
```
