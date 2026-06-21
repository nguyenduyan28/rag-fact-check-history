# Stage 8 Report: Temporal Index

## Summary

Stage 8 is complete.

This stage builds a temporal lookup index over graph nodes, graph edges, and cleaned chunks.

Main artifacts:

| Artifact | Count / Purpose |
|---|---|
| `data/outputs/graph/temporal_index.json` | Temporal mappings for nodes, edges, chunks, and years |
| `data/outputs/reports/temporal_index_report.md` | Temporal index statistics |

## Problem

Historical verification often depends on time. A claim may be wrong because the year, period, or chronology is wrong.

Plain graph traversal is not enough for this. Retrieval needs fast access to graph nodes, graph facts, and chunks related to a given year.

## Method

Method name:

```text
Deterministic temporal indexing from source-grounded graph artifacts
```

No LLM is used in this stage.

Implementation file:

```text
src/graph_rag/build_temporal_index.py
```

Command:

```bash
python3 -m src.graph_rag.build_temporal_index --config configs/graph.yaml
```

Inputs:

```text
data/outputs/graph/graph_nodes.json
data/outputs/graph/graph_edges.json
data/outputs/corpus/chunks.json
```

Output:

```text
data/outputs/graph/temporal_index.json
```

## Index Structure

The temporal index stores both forward and reverse mappings:

```text
node_to_years
edge_to_years
chunk_to_years
year_to_nodes
year_to_edges
year_to_chunks
```

Years are extracted from:

1. Existing `years` fields on graph nodes.
2. Node names, aliases, descriptions, evidence samples, and chunk text.
3. Edge descriptions and evidence text.
4. Cleaned chunk `year_mentions`, section text, and contextual text.

## Result

Summary:

| Metric | Count |
|---|---:|
| Nodes indexed | 4139 |
| Edges indexed | 10729 |
| Chunks indexed | 540 |
| Nodes with years | 1903 |
| Edges with years | 2285 |
| Chunks with years | 447 |
| Unique years | 297 |
| Min year | 1000 |
| Max year | 2020 |

Top years by chunk coverage:

| Year | Chunks |
|---:|---:|
| 1945 | 59 |
| 1939 | 41 |
| 1954 | 41 |
| 2000 | 40 |
| 1975 | 38 |
| 1973 | 36 |
| 1950 | 31 |
| 1918 | 30 |
| 1991 | 29 |
| 1929 | 28 |

Validation:

| Check | Result |
|---|---:|
| Reverse mapping errors | 0 |
| Node records indexed | 4139 / 4139 |
| Edge records indexed | 10729 / 10729 |
| Chunk records indexed | 540 / 540 |

## Quality Notes

Strengths:

1. Temporal lookup is deterministic and cheap.
2. It indexes all graph nodes, graph edges, and cleaned chunks.
3. It supports future year-aware graph retrieval and claim parsing.
4. Reverse mappings make it easy to retrieve all evidence around a year.

Limitations:

1. Current extraction only captures explicit four-digit years from `1000` to `2020`.
2. Relative phrases such as `thế kỉ XIX`, `đầu thế kỉ XX`, or `sau Chiến tranh thế giới thứ hai` are not normalized into ranges yet.
3. Stage 10 retrieval should treat temporal matching as a signal, not a hard filter.

## Conclusion

Stage 8 produced a usable temporal index for graph retrieval.

The next stage is Stage 9 claim parsing: extracting years and entity candidates from `key + claim` so claims can query the graph and temporal index.
