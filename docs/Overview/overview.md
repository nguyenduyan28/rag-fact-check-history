# Vietnamese History Claim Verification — GraphRAG Report

## Task

Given 11,491 historical claims (e.g., _"Nguyễn Ái Quốc founded the Vietnam Revolutionary Youth League in 1925"_), classify each as **real** or **fake** using evidence from 10th–12th grade Vietnamese history textbooks.

---

## 1. Data Pipeline

### 1.1 Corpus: OCR → Cleaned Chunks

| Step | Description |
|------|-------------|
| **Input** | 591 raw OCR `.txt` files from grades 10, 11, 12 |
| **Cleaning** | Unicode NFC normalization, whitespace normalization, garbage-page removal (index pages, very short pages, publication pages) |
| **Output** | **540 section-aware chunks** (≤2,200 chars each, with page/chapter/source metadata) |

### 1.2 Entity & Relation Extraction

Each chunk is sent to **Gemini 2.5 Flash** with a schema-constrained JSON response (`response_mime_type=application/json`). It extracts:

| Entity Type | Count | Example |
|-------------|------:|---------|
| Place | 1,313 | Hà Nội, Điện Biên Phủ |
| Time | 1,148 | 1945, thế kỷ XIX |
| Concept | 1,119 | độc lập, dân chủ |
| Event | 925 | Cách mạng tháng Tám |
| Organization | 906 | Đảng CSVN, Quân đội ND |
| Person | 455 | Hồ Chí Minh, Võ Nguyên Giáp |

| Relation Type | Count | Example |
|---------------|------:|---------|
| RELATED_TO | 2,973 | (safe fallback) |
| RESULTS_IN | 570 | Chiến tranh → RESULTS_IN → độc lập |
| OCCURRED_AT | 544 | Điện Biên Phủ → OCCURRED_AT → Tây Bắc |
| CAUSES | 320 | Khai thác thuộc địa → CAUSES → mâu thuẫn |
| PARTICIPATED_IN | 223 | HCM → PARTICIPATED_IN → CMT8 |
| LOCATED_IN | 124 | Vịnh Bắc Bộ → LOCATED_IN → Bắc Bộ |
| AFTER / BEFORE | 113 | Khởi nghĩa Bắc Sơn → BEFORE → CMT8 |

**Total:** 5,866 entities, 4,867 relations. 0 errors.

### 1.3 Entity Alignment

Same entities appear with different names across chunks (e.g., `Nguyễn Ái Quốc` / `Hồ Chí Minh`, `Mỹ` / `Mĩ` / `Hoa Kỳ`).

- **Step 1 (deterministic):** Exact normalized-name merge → 2,124 merges
- **Step 2 (Gemini review):** 300 fuzzy candidate groups reviewed → 154 additional merges
- **Result:** 5,866 → **3,599 canonical entities** with 3,742 alias mappings

### 1.4 Graph Construction

Fully deterministic (no LLM, no embeddings).

| Metric | Value |
|--------|------:|
| Nodes | 4,139 (540 DocumentChunk + 3,599 entities) |
| Edges | 10,729 (5,862 MENTIONS + 4,867 extracted relations) |
| Validation | 0 duplicate IDs, 0 broken endpoints, 0 self-loops |

Edges connect chunks to entities (`MENTIONS`) and entities to each other via typed historical relations.

### 1.5 Temporal Index

A lookup table mapping years → nodes, edges, and chunks.

| Metric | Value |
|--------|------:|
| Unique years | 297 (1000–2020) |
| Nodes with years | 1,903 (46%) |
| Top year | 1945 (59 chunks) |

### 1.6 Claim Parsing

Each of 11,491 claims is parsed for:
- **Years** (regex): 6,877 claims have years
- **Alias matches** (deterministic lookup): 11,397 claims matched
- **Semantic structure** (Gemini): entity mentions, event mentions, relation hints, claim focus
- **Fallback:** 9 Gemini failures → deterministic-only parsing

**Result:** 11,491 parsed, 0 errors.

---

## 2. Retrieval & Verification Models

All models share the same claim set (11,491) and the same corpus (540 chunks).

---

### 2.1 BM25-Only RAG

```
Claim → BM25 sparse retrieval (batch-encoded) → Top 5 chunks → Gemini 2.5 Flash → real/fake
```

**BM25:** A TF-IDF-style ranking function. Each chunk is scored by lexical keyword overlap with the claim. Simple, fast, needs no GPU.

**Batch encoding:** All 540 chunks are encoded once into an inverted index (~0.5s). All 11,491 queries are scored against it (~20s total).

**Verifier:** Gemini 2.5 Flash receives 5 text chunks per claim and returns structured JSON (`predicted_label`, `confidence`, `reasoning`, `insufficient_evidence`).

| Result | Value |
|--------|------:|
| Accuracy | **84.36%** |
| Real recall | 85.59% |
| Fake recall | 83.81% |
| Errors | 0 |
| Insufficient evidence | 920 (8.0%) |

---

### 2.2 Dense-Only RAG

```
Claim → Dense embedding retrieval (batch-encoded) → Top 5 chunks → Gemini 2.5 Flash → real/fake
```

**Dense retrieval:** Uses `all-MiniLM-L6-v2` to encode both chunks and claims into 384-dimensional vectors. Chunks closest to the claim in vector space are retrieved — captures semantic similarity even without keyword overlap.

**Batch encoding:** All 540 chunks are pre-encoded. All 11,491 queries are encoded and searched in batch (~3 min total).

**Verifier:** Same Gemini 2.5 Flash with identical prompt structure.

| Result | Value |
|--------|------:|
| Accuracy | **83.85%** |
| Real recall | 81.63% |
| Fake recall | 84.85% |
| Errors | 3 |
| Insufficient evidence | 1,162 (10.1%) |

---

### 2.3 Hybrid Text + Graph RAG

```
Claim ──→ Text retrieval (BM25 + Dense → re-rank) ──→ Top 3 text chunks ──┐
         └→ Graph retrieval (deterministic) ─────────→ Top 5 graph facts    ├→ Fuse → Gemini → real/fake
                                                        + 3 linked chunks ┘
```

**Text retrieval** (same as baseline): BM25 + Dense → re-rank → top 3 chunks.

**Graph retrieval** (deterministic, no LLM, no embeddings):

1. **Parse claim signals:** years (regex), entity aliases (lookup), semantic structure (Gemini)
2. **Node lookup:** Match aliases to graph node IDs
3. **Temporal lookup:** Find nodes/edges/chunks related to claim years
4. **1-hop expansion:** From matched nodes and year-related nodes, collect all incident edges and neighbor nodes
5. **Score candidates** on 4 signals:
   - Entity match (how many claim entities appear in the fact)
   - Year overlap (do claim years match fact years)
   - Relation type fit (is the relation type relevant to the claim focus)
   - Phrase overlap (lexical overlap between claim and linked chunk)
6. **Top-k:** 5 graph facts + 3 linked chunks per claim

**Fusion:** Deterministic join by claim ID — context has 3 groups:
- `text_1` … `text_3`: text chunks
- `graph_fact_1` … `graph_fact_5`: structured facts with typed relations
- `graph_chunk_1` … `graph_chunk_3`: chunks linked via graph topology

**Verifier:** Gemini 2.5 Flash sees all evidence with citation IDs.

| Result | Value |
|--------|------:|
| Accuracy | **86.36%** |
| Real recall | 92.16% |
| Fake recall | 83.77% |
| Errors | 10 |
| Insufficient evidence | 479 (4.2%) |

**Key design choice:** The entire graph retrieval pipeline is **deterministic** — no LLM calls, no embeddings. This makes it reproducible, debuggable, and free ($0 inference cost for 11,491 queries in ~4 minutes).

---

## 3. Results Comparison

All three models use **Gemini 2.5 Flash** as the verifier — numbers are directly comparable.

| Model | Accuracy | Real Recall | Fake Recall | Insufficient |
|-------|:--------:|:-----------:|:-----------:|:------------:|
| Dense-only | 83.85% | 81.63% | 84.85% | 1,162 |
| BM25-only | 84.36% | 85.59% | 83.81% | 920 |
| **Hybrid Text+Graph** | **86.36%** | **92.16%** | **83.77%** | **479** |

### Confusion Matrices

| Model | | Pred real | Pred fake |
|-------|-|:---------:|:---------:|
| **BM25-only** | Gold real | 3,040 | 512 |
| | Gold fake | 1,285 | 6,654 |
| **Dense-only** | Gold real | 2,898 | 652 |
| | Gold fake | 1,203 | 6,735 |
| **Hybrid Text+Graph** | Gold real | 3,268 | 278 |
| | Gold fake | 1,288 | 6,647 |

### Key Findings

- **Graph adds +2.00pp** over the best text-only method (BM25: 84.36% → Hybrid: 86.36%) under the same Gemini verifier. This is a genuine retrieval improvement, not a verifier artifact.
- **Graph dramatically reduces insufficient evidence:** Hybrid has 479 (4.2%) vs BM25's 920 (8.0%) and Dense's 1,162 (10.1%). The graph provides signals even when text retrieval misses relevant chunks.
- **BM25 slightly outperforms Dense** (84.36% vs 83.85%). For this domain (historical facts with specific named entities), lexical matching is competitive with or better than semantic embedding — likely because historical names (`Nguyễn Ái Quốc`, `Cách mạng tháng Tám`) are distinctive keywords.
- **Hybrid real recall is notably higher** (92.16%) than BM25 (85.59%) and Dense (81.63%). The graph helps the verifier find supporting evidence for true claims that text-only methods miss.
- **Fake recall is stable** across all methods (~83-85%). The graph does not especially help or hurt false claim detection — false claims are usually contradicted by text evidence when it is found.

---

## 4. Future Work

### 4.1 Remaining Ablation Experiments

| Experiment | Description | Status |
|-----------|-------------|:------:|
| Graph-only | No text chunks, only graph facts + linked chunks | Planned |
| + Temporal | Explicit year summary added to hybrid context | Planned |
| Hybrid top-1/3/5 | Text-only with different k values (same Gemini verifier) | Planned |

These will complete the ablation table and isolate the contribution of each graph component.

### 4.2 Multi-Hop Reasoning

Current graph retrieval is limited to **1-hop neighborhood expansion**. Many claims require multi-step reasoning:

> "Which organization did Hồ Chí Minh found that later merged with the Việt Minh?"

This requires: HCM → PARTICIPATED_IN → ? → RESULTS_IN → Việt Minh.

**Plan:** Implement 2-hop and 3-hop deterministic retrieval with path scoring, bounded by configurable max edges per hop to control explosion.

### 4.3 Relation Type Quality

61% of extracted relations are generic `RELATED_TO` — a safe fallback when Gemini is uncertain. Improving relation type specificity would make graph retrieval more precise.

**Plan:** Fine-tune a small classifier (e.g., PhoBERT) on the existing 4,867 relations to re-classify or subtype `RELATED_TO` edges — making the graph more informative at no additional LLM cost.

### 4.4 Error Analysis

Three persistent error patterns:

| Pattern | Example | Current issue |
|---------|---------|---------------|
| Rare entity spelling | `Quốc dân Đảng` vs `Việt Nam Quốc dân Đảng` | Alias map missing variant |
| Insufficient context | Claims about minor local events | Not mentioned in any chunk |
| Verifier hallucination | Claim is fake, context has no info, but verifier labels real | Need stronger "abstain" mechanism |

**Plan:** Audit the 1,288 false real errors (gold fake, predicted real) — the largest error bucket — to identify actionable improvements.

### 4.5 Production Considerations

- **End-to-end deterministic retrieval** means the graph pipeline can serve as a free pre-filter before a paid LLM call
- **JSON graph format** (no Neo4j) keeps deployment simple
- **Batch retrieval:** 11,491 claims in ~4 minutes for graph, ~20s for BM25 — scalable to much larger claim sets
