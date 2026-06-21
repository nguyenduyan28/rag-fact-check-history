# TODO: From Current RAG Repo To GraphRAG

Use this as the working checklist. Do the stages in order. Do not jump to GraphRAG before the text RAG baseline is measured.

## Stage 1: Text RAG Baseline

- [x] Install dependencies with `pip install -r requirements.txt`.
- [x] Create `.env` from `.env.example` and add `OPENAI_API_KEY`.
- [x] Run hybrid retrieval with `python3 -m src.rag.retrieve --config configs/rag.yaml`.
- [x] Check output exists at `data/outputs/retrieved/hybrid_top5.json`.
- [x] Run verifier with `python3 -m src.rag.verify --config configs/verify.yaml`.
- [x] Check output exists at `data/outputs/verified/hybrid_top5_verified.json`.
- [x] Run evaluation with `python3 -m src.rag.evaluate --config configs/eval.yaml`.
- [x] Save baseline numbers: accuracy, macro F1, real recall, fake recall, false real, false fake.

Goal: know how good plain hybrid text RAG is before GraphRAG.

## Stage 2: Baseline Error Analysis

- [x] Sample fake claims predicted as `real`.
- [x] Sample real claims predicted as `fake`.
- [x] Check whether retrieved chunks actually contain the needed evidence.
- [x] Check if failures are caused by wrong dates.
- [x] Check if failures are caused by wrong people, places, or organizations.
- [x] Check if failures are caused by broad/topically related but non-decisive chunks.
- [x] Check if failures are caused by OCR noise.
- [x] Write short notes in `data/outputs/reports/error_notes.md`.

Goal: identify which failures GraphRAG should fix.

## Stage 3: Corpus Cleaning

- [x] Update `configs/graph.yaml` with Stage 3-12 paths, corpus-cleaning options, and section-aware chunking options.
- [x] Create `src/graph_rag/clean_corpus.py` using `configs/graph.yaml`.
- [x] Normalize Unicode for all corpus pages.
- [x] Normalize whitespace and broken line breaks.
- [x] Remove very short, publication/index, or garbage pages.
- [x] Save cleaned page records to `data/outputs/corpus/pages.json`.
- [x] Detect section boundaries from OCR text with deterministic rules.
- [x] Build section-aware chunks with page-trace metadata.
- [x] Keep metadata for every chunk: `chunk_id`, `chunk_type`, `book`, `chapter`, `section`, `pages`, `source_pages`, `source_files`, `text`.
- [x] Add trace metadata where useful: `char_count`, `year_mentions`, `prev_chunk_id`, `next_chunk_id`, `section_confidence`, `fallback_used`.
- [x] Save section-aware chunks to `data/outputs/corpus/chunks.json`.
- [x] Save cleaning and chunking summary to `data/outputs/reports/corpus_cleaning_report.md`.
- [x] Keep original `.txt` files unchanged.
- [x] Inspect a sample of cleaned chunks from grades 10, 11, and 12.

Goal: have clean, traceable chunks for both RAG and GraphRAG.

## Stage 4: Decide Graph Schema

- [x] Create `docs/graph_schema.md`.
- [x] Keep `docs/graph_schema.md` aligned with `configs/graph.yaml` schema fields.
- [x] Define node types: `DocumentChunk`, `Person`, `Organization`, `Event`, `Place`, `Time`, `Concept`.
- [x] Define edge types: `MENTIONS`, `PARTICIPATED_IN`, `OCCURRED_AT`, `LOCATED_IN`, `RELATED_TO`, `CAUSES`, `RESULTS_IN`, `BEFORE`, `AFTER`, `SUPPORTED_BY`.
- [x] Define required node fields: `id`, `type`, `name`, `aliases`, `description`, `years`, `source_chunks`.
- [x] Define required edge fields: `source`, `target`, `type`, `description`, `source_chunk`, `confidence`.
- [x] Write Stage 4 method/result report at `docs/stage_4/report.md`.

Goal: lock the graph format before extraction starts.

## Stage 5: Entity/Event/Time Extraction

- [x] Write an extraction prompt for one textbook chunk.
- [x] Extract people, organizations, events, places, concepts, and time expressions.
- [x] Extract relations between them.
- [x] Force valid JSON output.
- [x] Add retry logic for invalid JSON.
- [x] Add checkpointing so extraction can resume.
- [x] Run extraction on a small sample first.
- [x] Manually inspect sample extraction quality.
- [x] Run extraction on all 540 cleaned chunks.
- [x] Save raw output to `data/outputs/graph/extracted_chunks.json`.
- [x] Save failures to `data/outputs/graph/extraction_errors.json`.
- [x] Clean raw extraction output into `data/outputs/graph/extracted_chunks_cleaned.json`.
- [x] Save cleanup summary to `data/outputs/reports/extraction_cleanup_report.md`.
- [x] Write Stage 5 method/result report at `docs/stage_5/report.md`.

Goal: convert textbook chunks into structured historical facts.

## Stage 6: Entity Alignment

- [x] Collect all extracted entities into `entities_raw.json`.
- [x] Normalize names: lowercase, Unicode NFC, punctuation cleanup.
- [x] Add manual alias seed groups for common names.
- [x] Review obvious aliases like `Mỹ`, `Mĩ`, `Hoa Kỳ` in Gemini candidate groups.
- [x] Review obvious aliases like `Liên Xô`, `Liên bang Xô viết` in Gemini candidate groups.
- [x] Review aliases like `Nguyễn Ái Quốc`, `Hồ Chí Minh` when context supports merging.
- [x] Use Gemini review for 300 prioritized uncertain duplicate candidate groups.
- [x] Save aligned entities to `data/outputs/graph/entities_aligned.json`.
- [x] Save alias map to `data/outputs/graph/entity_aliases.json`.
- [x] Save Gemini decisions to `data/outputs/graph/entity_alignment_decisions.json`.
- [x] Save alignment report to `data/outputs/reports/entity_alignment_report.md`.

Goal: avoid duplicated graph nodes for the same historical entity.

## Stage 7: Build Graph

- [x] Build `DocumentChunk` nodes from cleaned corpus chunks.
- [x] Build entity/event/time/place/concept nodes from aligned extraction output.
- [x] Build edges from extracted relations.
- [x] Add `MENTIONS` edges from chunks to entities/events.
- [x] Add `source_chunk` to every edge.
- [x] Add year metadata to event/time nodes.
- [x] Save nodes to `data/outputs/graph/graph_nodes.json`.
- [x] Save edges to `data/outputs/graph/graph_edges.json`.
- [x] Save combined graph to `data/outputs/graph/history_graph.json`.
- [x] Start with JSON or NetworkX, not Neo4j.
- [x] Save graph build report to `data/outputs/reports/graph_build_report.md`.
- [x] Write Stage 7 report at `docs/stage_7/report.md`.

Goal: create a debuggable graph before adding graph retrieval.

## Stage 8: Temporal Index

- [x] Extract years from every graph node description.
- [x] Extract years from every graph edge description.
- [x] Extract years from every chunk text.
- [x] Store node-to-year mappings.
- [x] Store chunk-to-year mappings.
- [x] Store reverse year-to-node, year-to-edge, and year-to-chunk mappings.
- [x] Save to `data/outputs/graph/temporal_index.json`.
- [x] Save temporal index report to `data/outputs/reports/temporal_index_report.md`.
- [x] Write Stage 8 report at `docs/stage_8/report.md`.

Goal: support history-specific retrieval by time.

## Stage 9: Claim Parser

- [x] Create `src/graph_rag/parse_claims.py`.
- [x] Add hybrid deterministic + Gemini claim parsing.
- [x] Extract years from `key + claim`.
- [x] Extract entity candidates from `key + claim` using alias matching.
- [x] Normalize claim entities using the alias map.
- [x] Extract LLM entity mentions, event mentions, relation hints, claim focus, and keywords.
- [x] Run a 5-claim smoke test.
- [x] Save smoke-test parsed claims to `data/outputs/claims/parsed_claims.json`.
- [x] Save smoke-test failures to `data/outputs/claims/claim_parse_errors.json`.
- [x] Save smoke-test report to `data/outputs/reports/claim_parser_report.md`.
- [x] Write Stage 9 report at `docs/stage_9/report.md`.
- [ ] Run parser on all 11491 claims.

Goal: turn each claim into graph retrieval signals.

## Stage 10: Graph-Only Retrieval

- [ ] Match claim entities to graph nodes.
- [ ] Match claim years to graph temporal index.
- [ ] Score candidate graph nodes by entity match, year match, and semantic similarity.
- [ ] Expand 1-hop neighbors from matched nodes.
- [ ] Collect graph facts and linked source chunks.
- [ ] Save output to `data/outputs/retrieved/graph_topk.json`.
- [ ] Inspect 20 random graph retrieval results manually.

Goal: retrieve structured graph evidence for each claim.

## Stage 11: Hybrid Text + Graph Retrieval

- [ ] Load text RAG top-k results.
- [ ] Load graph retrieval top-k results.
- [ ] Fuse context into three groups: text chunks, graph facts, graph-linked chunks.
- [ ] Keep context compact: top 3 text chunks, top 5 graph facts, top 3 linked chunks.
- [ ] Save output to `data/outputs/retrieved/graph_hybrid_topk.json`.

Goal: build the actual GraphRAG retrieval context.

## Stage 12: GraphRAG Verification

- [ ] Write verifier prompt using text evidence plus graph facts.
- [ ] Require JSON output with `label`, `evidence_ids`, and `reasoning`.
- [ ] Make the verifier cite text evidence IDs and graph fact IDs.
- [ ] Run on a small smoke test first.
- [ ] Run on the full dataset.
- [ ] Save output to `data/outputs/verified/graph_hybrid_verified.json`.

Goal: classify claims using both text and graph evidence.

## Stage 13: Evaluation And Ablation

- [ ] Evaluate majority baseline.
- [ ] Evaluate BM25-only RAG.
- [ ] Evaluate dense-only RAG.
- [ ] Evaluate hybrid text RAG.
- [ ] Evaluate hybrid text RAG with top-1 evidence.
- [ ] Evaluate hybrid text RAG with top-3 evidence.
- [ ] Evaluate hybrid text RAG with top-5 evidence.
- [ ] Evaluate graph-only RAG.
- [ ] Evaluate hybrid Text + Graph RAG.
- [ ] Evaluate hybrid Text + Graph + Temporal RAG.
- [ ] Report accuracy, macro F1, balanced accuracy, real recall, fake recall.

Goal: prove whether GraphRAG improves over text RAG.

## Stage 14: Final Error Analysis

- [ ] Categorize retrieval miss errors.
- [ ] Categorize wrong entity match errors.
- [ ] Categorize wrong temporal match errors.
- [ ] Categorize OCR noise errors.
- [ ] Categorize verifier reasoning errors.
- [ ] Categorize ambiguous/bad-label examples.
- [ ] Write `data/outputs/reports/graph_error_analysis.md`.

Goal: explain when GraphRAG helps and when it fails.

## Stage 15: Optional Production Upgrade

- [ ] Move graph from JSON/NetworkX to Neo4j only if JSON graph becomes hard to query.
- [ ] Add Vietnamese word segmentation for BM25.
- [ ] Add a cross-encoder reranker.
- [ ] Add human relevance labels for retrieval evaluation.
- [ ] Add source/grade metadata to claims if recoverable.

Goal: improve scalability and paper strength after the core method works.

## Current Recommended Next Action

- [x] Update `configs/graph.yaml` for Stage 3-12 outputs.
- [x] Run Stage 3 corpus cleaning.
- [x] Inspect `data/outputs/corpus/pages.json`, `data/outputs/corpus/chunks.json`, and `data/outputs/reports/corpus_cleaning_report.md`.
- [x] Create `docs/graph_schema.md` for Stage 4.
- [x] Run Stage 5 entity/event/time/relation extraction on cleaned chunks.
- [x] Clean extraction output before graph construction.
- [x] Start Stage 6 entity alignment using `data/outputs/graph/extracted_chunks_cleaned.json`.
- [x] Complete Stage 6 entity alignment with 300 Gemini-reviewed candidate groups and 0 errors.
- [x] Complete Stage 7 graph building from `entities_aligned.json`, `entity_aliases.json`, and `extracted_chunks_cleaned.json`.
- [x] Complete Stage 8 temporal indexing from graph nodes, graph edges, and cleaned chunks.
- [x] Implement and smoke-test Stage 9 claim parser using `key + claim`, `entity_aliases.json`, and Gemini.
- [ ] Run Stage 9 parser on all 11491 claims.
