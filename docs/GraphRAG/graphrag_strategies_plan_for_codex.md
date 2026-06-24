# GraphRAG Strategy Implementation Plan

## Project

Custom GraphRAG strategies for Vietnamese historical claim verification.

The system verifies claims with the format:

```json
{
  "ID": "...",
  "key": "topic summary",
  "claim": "historical claim to verify",
  "relevant": "gold/source evidence when available",
  "label": "real|fake"
}
```

The target output is a binary label:

```text
real | fake
```

The existing repository already has a Hybrid Text RAG baseline:

```text
src/rag/retrieve.py
src/rag/verify.py
src/rag/evaluate.py
```

Current baseline flow:

```text
Claim
-> BM25 + BGE-M3 dense retrieval
-> Reciprocal Rank Fusion
-> top-k textbook chunks
-> OpenAI verifier
-> real/fake
```

Reported baseline accuracy: approximately 79.98%.

The repository also has a partially built GraphRAG indexing pipeline:

```text
src/graph_rag/clean_corpus.py
src/graph_rag/extract_entities.py
src/graph_rag/clean_extractions.py
src/graph_rag/align_entities.py
src/graph_rag/build_graph.py
src/graph_rag/build_temporal_index.py
src/graph_rag/parse_claims.py
```

Existing graph artifacts:

```text
data/outputs/graph/history_graph.json
data/outputs/graph/graph_nodes.json
data/outputs/graph/graph_edges.json
data/outputs/graph/entity_aliases.json
data/outputs/graph/entities_aligned.json
data/outputs/graph/temporal_index.json
data/outputs/claims/parsed_claims.json
```

Known counts:

```text
Graph nodes: 4139
Graph edges: 10729
DocumentChunk nodes: 540
Aligned entities: 3599
Unique years in temporal index: 297
Parsed claims: 11482
```

Missing modules:

```text
src/graph_rag/retrieve_graph.py
src/graph_rag/verify_graph.py
```

The goal is to implement three non-incremental GraphRAG retrieval strategies and compare them across verifier models.

---

## Design Principle

Do not design the three strategies as:

```text
S1: graph only
S2: graph + time
S3: graph + time + rerank
```

That would only test incremental feature addition.

Instead, implement three strategies that test different hypotheses about how a graph can help claim verification:

```text
G1: FacetGraphRAG
- Graph as a facet-level precision filter.

G2: PathGraphRAG
- Graph as an explanatory reasoning structure.

G3: ContrastGraphRAG
- Graph as a counter-evidence and near-miss contradiction finder.
```

All three strategies should share the same final verifier interface.

The retrieval step should be mostly deterministic. LLM usage should be isolated to:

```text
1. Optional claim facet extraction, cached to disk.
2. Final verifier model.
3. Optional LLM reranking as a later ablation, not part of the initial three strategy comparison.
```

This keeps the experiment clean:

```text
GraphRAG strategy x Verifier model
```

---

## Proposed Module Structure

Create or update the following files:

```text
src/graph_rag/graph_store.py
src/graph_rag/claim_facets.py
src/graph_rag/retrieve_graph.py
src/graph_rag/format_evidence.py
src/graph_rag/verify_graph.py
src/graph_rag/evaluate_graph.py
```

Optional output directories:

```text
data/outputs/graph_rag/retrieval/
data/outputs/graph_rag/verification/
data/outputs/graph_rag/debug/
```

Suggested output files:

```text
data/outputs/claims/claim_facets.jsonl
data/outputs/graph_rag/retrieval/facet_graph_rag.jsonl
data/outputs/graph_rag/retrieval/path_graph_rag.jsonl
data/outputs/graph_rag/retrieval/contrast_graph_rag.jsonl
data/outputs/graph_rag/verification/{strategy}_{verifier}.jsonl
data/outputs/graph_rag/debug/seed_node_matches.jsonl
```

---

## Shared Pipeline

All three GraphRAG strategies should use the same high-level pipeline:

```text
Input claim
    |
    v
Claim facet parser
    |
    v
Seed node matching
    |
    v
Graph retrieval strategy
    |
    v
Evidence formatting
    |
    v
Verifier model
    |
    v
real / fake
```

The shared retrieval function should have this interface:

```python
def retrieve_graph(claim_row: dict, strategy: str, graph: GraphStore, top_k: int = 15) -> dict:
    ...
```

Expected output:

```python
{
    "id": claim_row["ID"],
    "key": claim_row.get("key"),
    "claim": claim_row["claim"],
    "strategy": strategy,
    "facets": {...},
    "seed_nodes": {...},
    "evidence": [...],
    "context_text": "...",
    "debug": {...}
}
```

---

## Step 1: GraphStore

Implement a lightweight in-memory graph store.

The graph is small enough to load JSON directly into memory.

### Responsibilities

`GraphStore` should:

```text
1. Load graph_nodes.json.
2. Load graph_edges.json.
3. Load entity_aliases.json.
4. Load temporal_index.json.
5. Build node_by_id.
6. Build outgoing adjacency.
7. Build incoming adjacency.
8. Build alias and normalized-name indexes.
9. Provide node matching.
10. Provide neighbor lookup.
11. Provide k-hop path search.
12. Provide temporal lookup.
```

### Suggested skeleton

```python
class GraphStore:
    def __init__(
        self,
        nodes_path: str,
        edges_path: str,
        aliases_path: str,
        temporal_path: str,
    ):
        self.nodes = load_json(nodes_path)
        self.edges = load_json(edges_path)
        self.aliases = load_json(aliases_path)
        self.temporal_index = load_json(temporal_path)

        self.node_by_id = self._build_node_by_id()
        self.adj_out = self._build_adj_out()
        self.adj_in = self._build_adj_in()
        self.alias_to_node = self._build_alias_index()
        self.normalized_name_to_node = self._build_normalized_name_index()

    def match_entity(self, text: str, top_k: int = 5) -> list[dict]:
        """
        Match a claim entity/facet string to graph nodes.

        Matching order:
        1. Exact alias match.
        2. Normalized string match.
        3. Optional embedding fallback.
        """
        ...

    def neighbors(self, node_id: str, direction: str = "both") -> list[dict]:
        """
        Return adjacent edges and neighbor nodes.
        """
        ...

    def find_paths(self, src: str, dst: str, max_hops: int = 2) -> list[dict]:
        """
        Find candidate paths between two graph nodes.
        Start with BFS up to max_hops.
        """
        ...

    def temporal_hits(self, years: list[int], window: int = 1) -> list[dict]:
        """
        Retrieve graph/chunk candidates from temporal_index.json.
        """
        ...
```

### Normalization

Implement Vietnamese-friendly normalization:

```python
def normalize_text(text: str) -> str:
    """
    Lowercase, strip, remove repeated spaces, and optionally remove Vietnamese accents.
    """
    ...
```

Matching priority:

```text
exact alias > normalized alias > normalized node name > embedding fallback
```

---

## Step 2: Claim Facet Parser

Implement `src/graph_rag/claim_facets.py`.

The parser should produce a structured representation of the claim.

### Target facet schema

```python
{
    "actor": [],
    "event": [],
    "time": [],
    "place": [],
    "cause": [],
    "result": [],
    "sequence": [],
    "number": [],
    "concept": [],
    "focus": []
}
```

### Source of facets

Use the existing `parsed_claims.json` first.

If `parsed_claims.json` only contains years and aliases, start with a deterministic parser:

```text
1. Extract years with regex.
2. Extract known aliases using entity_aliases.json.
3. Use the claim key as a topic/event hint.
4. Optionally classify entity type from graph node type.
```

Only add LLM-based facet extraction later if deterministic facets are too weak.

If using LLM facet extraction, cache it:

```text
data/outputs/claims/claim_facets.jsonl
```

Do not call the LLM repeatedly during retrieval experiments.

### Suggested interface

```python
def load_or_parse_facets(claim_row: dict, graph: GraphStore) -> dict:
    ...
```

---

## Step 3: Seed Node Matching

Seed nodes are graph nodes matched from claim facets.

Example claim:

```text
Thực dân Pháp khai thác thuộc địa lần hai chủ yếu ở Campuchia từ 1910 đến 1955.
```

Facets:

```python
{
    "actor": ["Thực dân Pháp"],
    "event": ["khai thác thuộc địa lần hai"],
    "place": ["Campuchia"],
    "time": ["1910", "1955"]
}
```

Seed nodes:

```python
{
    "actor": [
        {"text": "Thực dân Pháp", "node_id": "...", "score": 1.0, "method": "alias"}
    ],
    "event": [
        {"text": "khai thác thuộc địa lần hai", "node_id": "...", "score": 0.86, "method": "embedding"}
    ],
    "place": [
        {"text": "Campuchia", "node_id": "...", "score": 1.0, "method": "alias"}
    ],
    "time": [
        {"text": "1910", "year": 1910},
        {"text": "1955", "year": 1955}
    ]
}
```

Suggested interface:

```python
def match_seed_nodes(facets: dict, graph: GraphStore, top_k_per_facet: int = 3) -> dict:
    ...
```

---

# Strategy G1: FacetGraphRAG

## Hypothesis

Graph retrieval can improve claim verification by retrieving evidence that covers the important facets of a claim:

```text
actor, event, time, place, cause, result, sequence, number, concept
```

This strategy treats the claim as a checklist.

It asks:

```text
Does the graph contain evidence for each important part of the claim?
```

## Retrieval idea

For each seed node, retrieve its direct graph neighborhood and source chunks.

Use mostly 1-hop retrieval.

Optionally include 2-hop retrieval only from event nodes.

### Flow

```text
claim
-> facets
-> seed nodes
-> 1-hop neighbors for each seed node
-> collect edges and source chunks
-> score by facet coverage and temporal match
-> top-k evidence
-> verifier
```

### Candidate evidence

Each candidate should look like:

```python
{
    "type": "edge",
    "facet": "event",
    "source_node": {...},
    "edge": {...},
    "target_node": {...},
    "source_chunks": [...],
    "score": 0.82,
    "score_breakdown": {
        "seed_match": 0.9,
        "relation": 0.8,
        "temporal": 0.5,
        "facet_coverage": 0.7,
        "chunk_support": 1.0
    }
}
```

### Scoring

Start with a simple weighted score:

```python
score = (
    0.30 * seed_match_score +
    0.20 * relation_score +
    0.20 * temporal_score +
    0.20 * facet_coverage_score +
    0.10 * chunk_support_score
)
```

Suggested relation weights:

```python
IMPORTANT_RELATIONS = {
    "HAS_TIME": 1.0,
    "OCCURRED_IN": 1.0,
    "OCCURRED_AT": 1.0,
    "LOCATED_IN": 0.9,
    "PARTICIPATED_IN": 0.9,
    "LEADER_OF": 0.8,
    "CAUSES": 0.9,
    "RESULT_OF": 0.9,
    "PART_OF": 0.8,
    "MENTIONS": 0.3,
}
```

Adjust names after inspecting the actual edge types in `graph_edges.json`.

### Pseudocode

```python
def retrieve_facet_graph(facets, seed_nodes, graph, top_k=15):
    candidates = []

    for facet_type, matches in seed_nodes.items():
        if facet_type == "time":
            continue

        for match in matches:
            node_id = match["node_id"]
            neighbors = graph.neighbors(node_id, direction="both")

            for item in neighbors:
                edge = item["edge"]
                other_node = item["neighbor"]

                candidate = build_edge_candidate(
                    facet_type=facet_type,
                    seed_match=match,
                    edge=edge,
                    other_node=other_node,
                    facets=facets,
                )

                candidate["score"] = score_facet_candidate(candidate, facets)
                candidates.append(candidate)

    temporal_candidates = retrieve_temporal_candidates(facets, graph)
    candidates.extend(temporal_candidates)

    candidates = deduplicate_candidates(candidates)
    candidates = sorted(candidates, key=lambda x: x["score"], reverse=True)

    return candidates[:top_k]
```

### Evidence format for verifier

Format as facet-level evidence:

```text
Claim:
...

Parsed claim facets:
- actor: ...
- event: ...
- time: ...
- place: ...

Graph evidence by facet:
[Actor]
...

[Event]
...

[Time]
...

[Place]
...

Potential mismatches:
...
```

---

# Strategy G2: PathGraphRAG

## Hypothesis

Graph topology helps verify claims that require multi-hop historical reasoning.

This strategy treats claim verification as finding a small explanatory subgraph.

It asks:

```text
Is there a connected path or subgraph that explains the claim?
```

## Retrieval idea

Use seed nodes from the claim, then search for short paths between important nodes.

Important facets:

```text
event, actor, place, time, cause, result, sequence
```

Start with max 2 hops.

Avoid 3 hops initially because it can introduce too much noise.

### Flow

```text
claim
-> facets
-> seed nodes
-> choose important nodes
-> find paths between seed node pairs
-> score paths
-> collect source chunks
-> top-k paths
-> verifier
```

### Candidate path

```python
{
    "type": "path",
    "path_nodes": [...],
    "path_edges": [...],
    "source_chunks": [...],
    "score": 0.88,
    "score_breakdown": {
        "path_length": 0.8,
        "relation_quality": 0.9,
        "facet_coverage": 0.7,
        "temporal_consistency": 1.0,
        "chunk_support": 0.9
    }
}
```

### Scoring

```python
score = (
    0.20 * path_length_score +
    0.25 * relation_quality_score +
    0.25 * facet_coverage_score +
    0.20 * temporal_consistency_score +
    0.10 * chunk_support_score
)
```

Path length score:

```text
1-hop path: 1.0
2-hop path: 0.8
3-hop path: 0.4
```

Start with max 2 hops.

### Pseudocode

```python
def retrieve_path_graph(facets, seed_nodes, graph, max_hops=2, top_k=10):
    important_nodes = select_important_seed_nodes(seed_nodes)

    paths = []

    for src in important_nodes:
        for dst in important_nodes:
            if src["node_id"] == dst["node_id"]:
                continue

            candidate_paths = graph.find_paths(
                src=src["node_id"],
                dst=dst["node_id"],
                max_hops=max_hops,
            )

            for path in candidate_paths:
                candidate = build_path_candidate(path, src, dst, facets, graph)
                candidate["score"] = score_path_candidate(candidate, facets)
                paths.append(candidate)

    paths = deduplicate_paths(paths)
    paths = sorted(paths, key=lambda x: x["score"], reverse=True)

    return paths[:top_k]
```

### Evidence format for verifier

Format as graph paths:

```text
Claim:
...

Parsed claim facets:
...

Graph explanation paths:
1. Node A --RELATION--> Node B --RELATION--> Node C
   Source chunks: ...

2. Node D --RELATION--> Node E
   Source chunks: ...

Temporal consistency:
...

Potential missing or contradictory links:
...
```

---

# Strategy G3: ContrastGraphRAG

## Hypothesis

Graph retrieval can improve fake-claim detection by finding near-miss true facts that contradict the claim.

This strategy treats claim verification as contrastive search.

It asks:

```text
What is the closest true fact in the graph, and does it contradict the claim?
```

This is especially useful for fake claims that are almost true:

```text
correct event, wrong year
correct actor, wrong place
correct conference, wrong decision
correct movement, wrong result
correct event, wrong sequence
```

## Retrieval idea

Keep core facets fixed, then query the graph for true values of other facets.

Example:

```text
Claim:
Bác Hồ đọc Tuyên ngôn Độc lập tại Huế ngày 2/9/1945.
```

Core facets:

```text
actor = Bác Hồ
event = đọc Tuyên ngôn Độc lập
time = 2/9/1945
```

Ask graph:

```text
For this actor + event + time, what is the true place?
```

If the graph says:

```text
Quảng trường Ba Đình, Hà Nội
```

Then:

```text
claim place = Huế
graph place = Hà Nội
=> place_conflict
```

### Flow

```text
claim
-> facets
-> seed nodes
-> choose core event/actor facets
-> retrieve graph facts around core event
-> extract true time/place/actor/result/cause facets
-> compare claim facets against graph facets
-> build support/refute evidence
-> verifier
```

### Conflict types

Implement explicit conflict types:

```text
time_conflict
place_conflict
actor_conflict
event_conflict
cause_conflict
result_conflict
sequence_conflict
number_conflict
```

### Candidate conflict

```python
{
    "type": "contrast",
    "conflict_type": "time_conflict",
    "fixed_facets": {
        "actor": "Thực dân Pháp",
        "event": "khai thác thuộc địa lần hai"
    },
    "claim_value": "1910-1955",
    "graph_value": "1919-1929",
    "evidence_edge": {...},
    "source_chunks": [...],
    "confidence": 0.91
}
```

### Pseudocode

```python
def retrieve_contrast_graph(facets, seed_nodes, graph, top_k=10):
    conflicts = []
    support = []

    core_nodes = select_core_nodes(seed_nodes)

    for core_node in core_nodes:
        neighbors = graph.neighbors(core_node["node_id"], direction="both")

        graph_facts = extract_typed_facts_from_neighbors(neighbors)

        support.extend(find_supporting_matches(facets, graph_facts))
        conflicts.extend(find_facet_conflicts(facets, graph_facts))

    conflicts = score_conflicts(conflicts, facets)
    support = score_support(support, facets)

    evidence = {
        "support": sorted(support, key=lambda x: x["score"], reverse=True)[:top_k],
        "conflicts": sorted(conflicts, key=lambda x: x["confidence"], reverse=True)[:top_k],
    }

    return evidence
```

### Conflict detection rules

Time conflict:

```text
If claim has a year/range and graph has a year/range for the same core event,
and the ranges do not overlap,
then create time_conflict.
```

Place conflict:

```text
If claim has a place and graph has a different place for the same core event,
and the graph place is strongly supported,
then create place_conflict.
```

Actor conflict:

```text
If claim has an actor and graph has a different actor for the same event/action,
then create actor_conflict.
```

Number conflict:

```text
If claim has a number and graph has a different number attached to the same event/concept,
then create number_conflict.
```

Be conservative:

```text
Only create a conflict when there is high overlap on the core event and at least one directly incompatible facet.
```

### Evidence format for verifier

Format as support/refute evidence:

```text
Claim:
...

Parsed claim facets:
...

Supporting evidence:
...

Contrastive evidence:
1. Same actor/event, but graph time is X while claim time is Y.
2. Same event/time, but graph place is A while claim place is B.

Detected conflicts:
- time_conflict
- place_conflict

Instruction:
Classify as fake if an important claim facet is directly contradicted by high-confidence contrastive evidence.
Otherwise classify as real only if the important facets are supported.
```

---

# Shared Evidence Formatting

Implement `src/graph_rag/format_evidence.py`.

Suggested interface:

```python
def format_evidence(claim_row: dict, retrieval_result: dict) -> str:
    strategy = retrieval_result["strategy"]

    if strategy == "facet":
        return format_facet_evidence(claim_row, retrieval_result)

    if strategy == "path":
        return format_path_evidence(claim_row, retrieval_result)

    if strategy == "contrast":
        return format_contrast_evidence(claim_row, retrieval_result)

    raise ValueError(f"Unknown strategy: {strategy}")
```

Each formatter should produce compact context.

Avoid dumping too many graph edges.

Keep context under a controlled token budget.

Suggested limit:

```text
top 10-15 graph evidence items
maximum 3000-5000 tokens per claim
```

---

# Verifier

Implement `src/graph_rag/verify_graph.py`.

The verifier should be strategy-agnostic.

It receives:

```text
claim
context_text
verifier_model
```

It returns:

```python
{
    "label": "real" | "fake",
    "confidence": float,
    "reason": str,
    "evidence_used": [...],
    "failed_facets": [...]
}
```

### Suggested verifier prompt

```text
You are verifying Vietnamese historical claims using evidence from a textbook-derived graph.

Task:
Classify the claim as exactly one label:
- real
- fake

Rules:
1. Label real only if the evidence supports the important factual parts of the claim.
2. Label fake if the evidence directly contradicts an important part of the claim.
3. Pay special attention to actor, event, time, place, cause, result, sequence, and numbers.
4. Do not use outside knowledge.
5. If evidence is insufficient, choose the label best supported by the provided evidence and explain the uncertainty.

Claim:
{claim}

Evidence:
{context_text}

Return JSON only:
{
  "label": "real|fake",
  "confidence": 0.0,
  "reason": "...",
  "evidence_used": ["..."],
  "failed_facets": ["..."]
}
```

---

# Evaluation Plan

Compare:

```text
Hybrid Text RAG baseline
FacetGraphRAG
PathGraphRAG
ContrastGraphRAG
Hybrid Text RAG + best GraphRAG
```

Across verifier models:

```text
GPT-4o-mini
Gemini 2.5 Flash
Any local/open model if available
```

Recommended metrics:

```text
Accuracy
Macro-F1
Real-F1
Fake-F1
Precision/Recall for fake
Average retrieved evidence count
Average context tokens
Average latency
Cost per 1000 claims
```

If gold evidence is available in the `relevant` field:

```text
Evidence recall@k
Evidence precision@k
```

Graph-specific diagnostics:

```text
Seed node match rate
Facet coverage rate
Temporal match rate
Path found rate
Conflict found rate
```

---

# Experiment Matrix

```text
Method                         Verifier A      Verifier B      Verifier C
Hybrid Text RAG                acc/f1          acc/f1          acc/f1
FacetGraphRAG                  acc/f1          acc/f1          acc/f1
PathGraphRAG                   acc/f1          acc/f1          acc/f1
ContrastGraphRAG               acc/f1          acc/f1          acc/f1
Hybrid Text + Best GraphRAG    acc/f1          acc/f1          acc/f1
```

---

# Implementation Order

## Phase 0: Inspect graph schema

Before implementing retrieval logic, inspect node and edge types.

```python
import json
from collections import Counter

nodes = json.load(open("data/outputs/graph/graph_nodes.json"))
edges = json.load(open("data/outputs/graph/graph_edges.json"))

print(Counter(node.get("type") for node in nodes).most_common())
print(Counter(edge.get("type") for edge in edges).most_common())
print(edges[0])
print(nodes[0])
```

This is necessary because the exact relation names determine scoring.

## Phase 1: Build GraphStore

Implement:

```text
src/graph_rag/graph_store.py
```

Test:

```text
- load nodes
- load edges
- build adjacency
- match alias
- get neighbors
- temporal hits
```

## Phase 2: Build claim facet loading

Implement:

```text
src/graph_rag/claim_facets.py
```

Start with deterministic parsing:

```text
- years by regex
- entity aliases by lookup
- key as topic/event hint
```

Cache output.

## Phase 3: Implement FacetGraphRAG

Implement:

```text
retrieve_facet_graph()
```

This is the first strategy to implement because it reuses the simplest graph operations.

## Phase 4: Implement ContrastGraphRAG

Implement:

```text
retrieve_contrast_graph()
```

This is likely useful for improving fake-claim F1.

## Phase 5: Implement PathGraphRAG

Implement:

```text
retrieve_path_graph()
```

Use BFS max 2 hops first.

## Phase 6: Implement evidence formatting

Implement:

```text
format_facet_evidence()
format_path_evidence()
format_contrast_evidence()
```

## Phase 7: Implement verifier

Implement:

```text
verify_graph.py
```

Reuse the existing LLM calling pattern from:

```text
src/rag/verify.py
```

## Phase 8: Implement graph evaluation

Implement:

```text
evaluate_graph.py
```

Reuse evaluation logic from:

```text
src/rag/evaluate.py
```

Add graph-specific debug metrics.

---

# Minimal CLI Design

Suggested commands:

```bash
python -m src.graph_rag.retrieve_graph   --strategy facet   --claims data/claims/test.jsonl   --output data/outputs/graph_rag/retrieval/facet_graph_rag.jsonl

python -m src.graph_rag.retrieve_graph   --strategy path   --claims data/claims/test.jsonl   --output data/outputs/graph_rag/retrieval/path_graph_rag.jsonl

python -m src.graph_rag.retrieve_graph   --strategy contrast   --claims data/claims/test.jsonl   --output data/outputs/graph_rag/retrieval/contrast_graph_rag.jsonl

python -m src.graph_rag.verify_graph   --retrieval data/outputs/graph_rag/retrieval/facet_graph_rag.jsonl   --model gpt-4o-mini   --output data/outputs/graph_rag/verification/facet_gpt4omini.jsonl

python -m src.graph_rag.evaluate_graph   --predictions data/outputs/graph_rag/verification/facet_gpt4omini.jsonl   --gold data/claims/test.jsonl
```

---

# Acceptance Criteria

The implementation is complete when:

```text
1. All three retrieval strategies run end-to-end.
2. Each strategy writes a JSONL retrieval file.
3. Each retrieval result contains facets, seed nodes, evidence, context text, and debug info.
4. The verifier can run on any retrieval output.
5. Evaluation reports accuracy, macro-F1, real-F1, fake-F1.
6. Debug metrics are available for seed match rate, facet coverage, path found rate, and conflict found rate.
7. The pipeline can compare GraphRAG strategy x Verifier model.
```

---

# Key Warning

Do not make the initial strategies depend heavily on LLM reranking.

If LLM reranking is used inside retrieval, the experiment will no longer cleanly measure the effect of the GraphRAG strategy.

Recommended clean setup:

```text
claim
-> cached deterministic/LLM facets
-> deterministic graph retrieval strategy
-> verifier LLM
-> real/fake
```

Add LLM reranking later as a separate ablation:

```text
FacetGraphRAG
FacetGraphRAG + LLM rerank

PathGraphRAG
PathGraphRAG + LLM rerank

ContrastGraphRAG
ContrastGraphRAG + LLM rerank
```

---

# Summary For Codex

Implement the missing GraphRAG modules using three retrieval strategies:

```text
1. FacetGraphRAG:
   Retrieve graph evidence around each claim facet.
   Best for checking actor/event/time/place precision.

2. PathGraphRAG:
   Retrieve short graph paths connecting claim entities.
   Best for multi-hop historical reasoning.

3. ContrastGraphRAG:
   Retrieve near-miss true facts that contradict claim facets.
   Best for detecting fake claims with small factual mutations.
```

Keep retrieval deterministic where possible, cache claim facets, and use the verifier LLM only after evidence has been retrieved.
