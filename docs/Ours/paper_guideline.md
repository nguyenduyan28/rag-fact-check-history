# Paper Guideline: Vietnamese Historical Claim Verification With Graph-Enhanced RAG

This guideline maps the paper direction to the current project roadmap in `TODO.md`. It is intentionally not a concrete implementation spec. Use it to keep the research story, method design, experiments, and TODO stages aligned.

## 1. Paper Goal

The project should be framed as Vietnamese historical claim verification, not multiple-choice question answering.

Core task:

> Given a Vietnamese historical claim and textbook-grounded evidence, predict whether the claim is `real` or `fake`.

Main research question:

> Can structured historical retrieval improve real/fake claim verification compared with blind LLM verification and plain text RAG?

Recommended paper direction:

> We introduce a Vietnamese historical claim-verification benchmark and analyze how blind LLM judging, hybrid text RAG, and graph-enhanced temporal/entity retrieval behave under evidence quality, label imbalance, and generated fake-claim noise.

## 2. Difference From HisGraphRAG

HisGraphRAG is useful inspiration, but the task is different.

| Aspect | HisGraphRAG | Our Project |
|---|---|---|
| Main task | Vietnamese history multiple-choice QA | Vietnamese historical claim verification |
| Input | Question with A/B/C/D options | Declarative claim with `real/fake` label |
| Corpus | Mainly Grade 12 textbook | Grades 10, 11, and 12 textbook chunks |
| Key method | GraphRAG, entity alignment, temporal retrieval, answer filtering, reranking | Hybrid RAG baseline, then graph-enhanced claim verification |
| Evaluation | MCQ accuracy | Accuracy, macro F1, balanced accuracy, real recall, fake recall, false real, false fake |

Do not directly compare headline accuracy with HisGraphRAG unless the same MCQ benchmark is implemented. Use it as architectural motivation for entity alignment, temporal retrieval, and reranking.

## 3. Method Components Mapped To TODO

| Paper Component | Our Adaptation | TODO Stage |
|---|---|---|
| Text RAG baseline | BM25 + dense embedding + RRF retrieval, followed by LLM verification | Stage 1 |
| Baseline error analysis | Identify retrieval misses, wrong dates, wrong entities, broad evidence, and OCR noise | Stage 2 |
| Corpus cleaning and chunking | Clean page-level chunks first; optionally later split by section or paragraph | Stage 3 |
| Graph schema | Define historical node and edge types before extraction | Stage 4 |
| Entity/event/time extraction | Extract people, organizations, events, places, times, concepts, and relations | Stage 5 |
| Entity alignment | Merge aliases and duplicate historical entities | Stage 6 |
| Graph construction | Build a debuggable JSON or NetworkX graph before considering Neo4j | Stage 7 |
| Temporal index | Store year mappings for chunks, graph nodes, and graph edges | Stage 8 |
| Claim parser | Extract years and entity candidates from `key + claim` | Stage 9 |
| Graph-only retrieval | Retrieve graph facts using entity, time, and semantic matching | Stage 10 |
| Hybrid text + graph retrieval | Fuse text chunks, graph facts, and graph-linked chunks | Stage 11 |
| GraphRAG verification | Verify using both text evidence and graph facts with citations | Stage 12 |
| Evaluation and ablation | Compare baselines and method variants | Stage 13 |
| Final error analysis | Explain when graph-enhanced retrieval helps and fails | Stage 14 |

## 4. What Chunking Improves

Chunking and corpus cleaning improve the raw evidence layer used by both text RAG and graph extraction.

Stage 3 should be config-driven. Before writing extraction or graph code, `configs/graph.yaml` should define the paths and options used by corpus cleaning and later GraphRAG stages. This keeps the pipeline reproducible and prevents hard-coded output paths from drifting away from `TODO.md`.

Minimum goal:

- Keep the original `.txt` files unchanged.
- Normalize Unicode and whitespace.
- Remove empty, very short, or garbage OCR chunks.
- Assign stable metadata: `chunk_id`, `book`, `page`, `source`, `text`.
- Add trace fields where useful: `char_count`, `year_mentions`, `prev_chunk_id`, `next_chunk_id`.
- Save cleaned chunks to `data/outputs/corpus/chunks.json`.
- Save a short cleaning report to `data/outputs/reports/corpus_cleaning_report.md`.

Recommended Stage 3 config keys:

```yaml
paths:
  corpus_dir: data/corpus
  cleaned_chunks: data/outputs/corpus/chunks.json
  corpus_report: data/outputs/reports/corpus_cleaning_report.md

corpus_cleaning:
  unicode_form: NFC
  normalize_whitespace: true
  min_chars: 80
  keep_original_txt: true
  include_prev_next_pages: true
  chunk_id_template: "{book}_p{page}"
```

Expected Stage 3 command:

```bash
python3 -m src.graph_rag.clean_corpus --config configs/graph.yaml
```

Expected benefits:

- Cleaner BM25 and dense retrieval.
- More reliable evidence citation.
- Better graph extraction because the LLM receives cleaner input.
- Easier error analysis by tracing every claim decision back to source chunks.

Advanced version, if Stage 2 shows broad or noisy chunks are causing errors:

- Recover chapter/section headings from textbooks.
- Use section-aware chunking instead of fixed page-level chunks.
- Add overlap from the previous section to preserve context continuity.
- Split oversized sections into smaller paragraph-level chunks.
- Filter quiz questions, unrelated page headers, table noise, and visual artifacts where possible.

Do not over-invest in advanced chunking before Stage 1 and Stage 2 show that current page-level chunks are a real bottleneck.

For this project, Stage 2 showed broad evidence and OCR noise, but the next step should still be conservative: clean page-level chunks first, add stable metadata, and add previous/next chunk links. Section-aware or paragraph-level chunking should be treated as a later upgrade only if cleaned page-level chunks remain a bottleneck.

## 4.1 GraphRAG Config Contract

The graph pipeline should use one shared config file, `configs/graph.yaml`, for Stages 3-12. This file should not only define graph node types; it should also define all intermediate artifacts so each stage can be rerun independently.

Required path groups:

- Stage 3 corpus cleaning: `corpus_dir`, `cleaned_chunks`, `corpus_report`.
- Stage 4 schema: `graph_schema`.
- Stage 5 extraction: `extracted_chunks`, `extraction_errors`.
- Stage 6 alignment: `entities_aligned`, `entity_aliases`.
- Stage 7 graph build: `graph_nodes`, `graph_edges`, `history_graph`.
- Stage 8 temporal index: `temporal_index`.
- Stage 9 claim parser: `parsed_claims`.
- Stage 10 graph retrieval: `graph_topk`.
- Stage 11 hybrid text + graph retrieval: `graph_hybrid_topk`.
- Stage 12 verification: `graph_verified`.

Recommended graph schema config:

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

This config contract should be reflected in `TODO.md`: each stage should name its expected input and output artifact before implementation starts.

## 5. What Entity Extraction Does

Entity extraction converts textbook chunks into structured historical facts.

Input example:

```text
Ngày 25-12-1920, Nguyễn Ái Quốc tham dự Đại hội đại biểu toàn quốc lần thứ XVIII của Đảng Xã hội Pháp tại Tua.
```

Possible extracted structure:

```json
{
  "people": ["Nguyễn Ái Quốc"],
  "organizations": ["Đảng Xã hội Pháp"],
  "places": ["Tua"],
  "times": ["25-12-1920"],
  "events": ["Nguyễn Ái Quốc tham dự Đại hội Đảng Xã hội Pháp"],
  "relations": [
    {
      "source": "Nguyễn Ái Quốc",
      "type": "PARTICIPATED_IN",
      "target": "Đại hội Đảng Xã hội Pháp"
    },
    {
      "source": "Đại hội Đảng Xã hội Pháp",
      "type": "OCCURRED_AT",
      "target": "Tua"
    }
  ]
}
```

Recommended node types:

- `DocumentChunk`
- `Person`
- `Organization`
- `Event`
- `Place`
- `Time`
- `Concept`

Recommended edge types:

- `MENTIONS`
- `PARTICIPATED_IN`
- `OCCURRED_AT`
- `LOCATED_IN`
- `RELATED_TO`
- `CAUSES`
- `RESULTS_IN`
- `BEFORE`
- `AFTER`
- `SUPPORTED_BY`

Expected benefits:

- Retrieve by historical entities instead of only surface text similarity.
- Match years and periods more precisely.
- Reduce false positives from broad but non-decisive chunks.
- Support graph facts such as who participated in what, when, and where.
- Let the verifier reason over compact facts plus source evidence.

## 6. Claim Verification Adaptation Of HisGraphRAG

HisGraphRAG uses answer candidate filtering because its task is MCQ QA. Our task has no A/B/C/D answer options, so the equivalent should be claim-focused filtering and reranking.

Claim-verification equivalent:

- Parse the claim into entities, dates, places, organizations, and event keywords.
- Retrieve candidate text chunks with hybrid text RAG.
- Retrieve candidate graph facts using entity and temporal signals.
- Rerank evidence by claim relevance, entity match, and temporal match.
- Ask the verifier to classify `real` or `fake` and cite evidence IDs.

Possible method name:

> Temporal-Entity Hybrid RAG for Vietnamese Historical Claim Verification

High-level pipeline:

1. Parse `key + claim` into entities and time expressions.
2. Retrieve top-k text chunks using BM25 + dense + RRF.
3. Retrieve graph facts using entity, relation, and temporal matching.
4. Fuse text chunks, graph facts, and graph-linked source chunks.
5. Rerank or filter context to keep it compact.
6. Verify the claim using cited evidence.
7. Categorize errors as retrieval miss, wrong entity, wrong time, OCR noise, verifier reasoning error, or bad/ambiguous label.

## 7. Required Experiments

Minimum dataset table:

- Total claims.
- Claims by source, if source metadata is recoverable.
- Real/fake distribution.
- Evidence availability.
- Average claim length.
- Average evidence length.
- Missing or empty evidence count.

Minimum baseline table:

- Majority baseline.
- LLM-only verification.
- Gold-evidence verification, where available.
- BM25-only RAG.
- Dense-only RAG.
- Hybrid BM25 + dense RAG.

Minimum ablation table:

- Query = `claim` only.
- Query = `key + claim`.
- Top-1 evidence.
- Top-3 evidence.
- Top-5 evidence.
- With and without temporal filtering.
- With and without entity-aware reranking.
- Text-only RAG vs graph-only RAG vs hybrid text + graph RAG.

Minimum retrieval analysis:

- Recall@1, Recall@3, Recall@5 where gold evidence exists.
- Manual relevance check for a sample where no gold evidence exists.
- Retrieval error categories: no relevant evidence, wrong time, wrong entity, broad topic match, OCR noise.

Minimum final metrics:

- Accuracy.
- Macro F1.
- Balanced accuracy.
- Real recall.
- Fake recall.
- False real: fake claims predicted as real.
- False fake: real claims predicted as fake.

## 8. Paper Story By Stage

Stage 1 gives the baseline:

> How good is plain hybrid text RAG for Vietnamese historical claim verification?

Stage 2 gives the motivation:

> What kinds of errors does plain text RAG make, and which errors require better entity or temporal reasoning?

Stages 3 to 8 build the graph foundation:

> We clean the corpus, define a historical graph schema, extract entities/events/times, align duplicate entities, build a traceable graph, and index temporal signals.

Stages 9 to 12 define the graph-enhanced method:

> Claims are parsed into entity and temporal signals, graph facts are retrieved and fused with text evidence, and the verifier uses both sources with explicit citations.

Stages 13 to 14 make the paper credible:

> We compare against baselines and ablations, then analyze why the method succeeds or fails.

## 9. What Not To Claim Yet

Avoid these claims until the corresponding stages are complete:

- Do not call the current system GraphRAG before graph construction and graph retrieval exist.
- Do not claim improvement over HisGraphRAG because the task is different.
- Do not claim RAG improves everything unless Stage 13 confirms it across macro F1, recalls, and error types.
- Do not claim the dataset is fully clean until missing evidence, source metadata, duplicates, and generated fake-claim quality are checked.
- Do not claim temporal retrieval helps until an ablation compares with and without temporal filtering.

## 10. Recommended Paper Contribution

The strongest contribution is likely a combination of benchmark and method:

1. A Vietnamese historical claim-verification dataset built from textbook and exam-style sources.
2. A reproducible hybrid text RAG baseline for claim verification.
3. A graph-enhanced retrieval method using entity alignment and temporal signals.
4. An ablation study showing which retrieval components help.
5. An error analysis explaining failure modes in Vietnamese historical verification.

This framing lets the project borrow the useful ideas from HisGraphRAG while staying honest about the different task and current repo direction.
