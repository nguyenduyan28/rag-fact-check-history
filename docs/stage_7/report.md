# Stage 7 Report: Graph Build

## Summary

Stage 7 is complete.

This stage builds a source-grounded JSON graph from cleaned chunks, cleaned extraction records, and aligned entities.

Main artifacts:

| Artifact | Count / Purpose |
|---|---|
| `data/outputs/graph/graph_nodes.json` | 4139 graph nodes |
| `data/outputs/graph/graph_edges.json` | 10729 graph edges |
| `data/outputs/graph/history_graph.json` | Combined graph with metadata, nodes, and edges |
| `data/outputs/reports/graph_build_report.md` | Graph build validation report |

## Problem

Stage 5 produced extracted entities and relations. Stage 6 aligned duplicate entities. These are still intermediate artifacts, not a graph.

Stage 7 solves this by creating graph nodes and graph edges with stable IDs and source trace metadata.

## Method

Method name:

```text
Deterministic source-grounded graph construction from aligned historical extractions
```

No LLM is used in this stage. Graph construction is a deterministic transformation.

Inputs:

```text
data/outputs/corpus/chunks.json
data/outputs/graph/extracted_chunks_cleaned.json
data/outputs/graph/entities_aligned.json
data/outputs/graph/entity_aliases.json
```

Implementation file:

```text
src/graph_rag/build_graph.py
```

Command:

```bash
python3 -m src.graph_rag.build_graph --config configs/graph.yaml
```

## Graph Construction Steps

1. Build one `DocumentChunk` node for every cleaned chunk.
2. Build one entity node for every aligned entity from Stage 6.
3. Use `entity_aliases.json` to map chunk-local mention IDs to aligned entity IDs.
4. Add `MENTIONS` edges from chunk nodes to aligned entity nodes.
5. Convert cleaned extracted relations into canonical entity-to-entity graph edges.
6. Preserve `source_chunk`, `evidence_text`, `description`, and `confidence` on relation edges.
7. Deduplicate equivalent edges while preserving separate source evidence.
8. Validate node IDs, edge IDs, edge endpoints, source chunks, and evidence fields.

## Result

Node types:

| Type | Count |
|---|---:|
| Concept | 853 |
| Time | 850 |
| Event | 672 |
| DocumentChunk | 540 |
| Place | 503 |
| Organization | 427 |
| Person | 294 |

Edge types:

| Type | Count |
|---|---:|
| MENTIONS | 5862 |
| RELATED_TO | 2973 |
| RESULTS_IN | 570 |
| OCCURRED_AT | 544 |
| CAUSES | 320 |
| PARTICIPATED_IN | 223 |
| LOCATED_IN | 124 |
| AFTER | 67 |
| BEFORE | 46 |

Validation:

| Check | Result |
|---|---:|
| Duplicate node IDs | 0 |
| Duplicate edge IDs | 0 |
| Broken edge endpoints | 0 |
| Edges missing `source_chunk` | 0 |
| Relation edges missing evidence | 0 |
| Self-loop edges | 0 |

## Quality Notes

Strengths:

1. Graph construction is deterministic and reproducible.
2. All edges point to existing nodes.
3. Every relation edge keeps source evidence for later verification.
4. `MENTIONS` edges connect graph facts back to textbook chunks.
5. JSON output is easy to inspect before adding retrieval.

Limitations:

1. `RELATED_TO` is the largest relation type, inherited from Stage 5 cleanup.
2. The graph is not yet optimized for retrieval scoring.
3. Temporal lookup is built separately in Stage 8.

## Conclusion

Stage 7 produced a valid debuggable JSON graph.

Stage 8 can now index temporal signals from graph nodes, graph edges, and cleaned chunks.
