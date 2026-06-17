# Stage 3 Plan: Section-Aware Corpus Chunking

## Goal

Build a cleaner and more semantically coherent corpus for the new RAG and future GraphRAG pipeline.

Stage 1 already used raw page-level textbook chunks. Stage 3 should therefore improve the evidence layer by creating section-aware historical chunks while preserving page-level traceability for citation and audit.

Stage 3 does not build the graph yet. It prepares cleaner retrieval and extraction units for later stages.

## Method Name

Use this method name in project notes or the paper draft:

```text
Rule-based section-aware historical chunking with page-trace metadata
```

Short description:

```text
We clean OCR textbook pages, detect textbook section boundaries with deterministic rules, merge page text into section-aware chunks, and preserve source page metadata for citation and audit.
```

## Motivation

Page-level chunks are useful for baseline RAG, but they are not a strong new method because the Stage 1 baseline already retrieves from OCR pages.

Problems with page-level chunks:

1. One page can contain multiple unrelated historical events or sections.
2. One textbook section can span multiple pages.
3. Retrieval can return broad but non-decisive evidence.
4. Graph extraction from broad pages can create noisy entities and relations.
5. The new RAG method needs better evidence units than the baseline.

Section-aware chunks should help because they better follow textbook structure and historical topic boundaries.

## HisGraphRAG Reference

HisGraphRAG Section 3.1, `Doc Chunking`, argues that fixed token or character chunks fail to preserve semantic and topical coherence in historical textbooks.

Their chunking method treats textbook sections as primary chunks and optionally prepends previous-section context:

```text
x_ij = S_i,j-k || S_ij
```

where:

```text
S_ij     = current section
S_i,j-k = previous section context
||       = concatenation
```

If a section chunk exceeds a token threshold `T_max`, HisGraphRAG recursively splits it into smaller chunks.

Our method adapts the same core idea, but starts from the current OCR `.txt` pages instead of reprocessing PDFs with VLM/document vision.

## Current Corpus Reality

Current input corpus:

```text
data/corpus/lichsu_10/*.txt
data/corpus/lichsu_11/*.txt
data/corpus/lichsu_12/*.txt
```

Current corpus size:

```text
lichsu_10: 206 txt files
lichsu_11: 159 txt files
lichsu_12: 226 txt files
total: 591 txt files
```

The OCR text already contains useful structure such as:

```text
Bài 23
PHONG TRÀO YẾU NƯỚC VÀ CÁCH MẠNG Ở VIỆT NAM
Phan Bội Châu và xu hướng bạo động
Câu hỏi và bài tập
```

Because the OCR text often preserves headings, the best current approach is deterministic section detection from existing `.txt` files, not full OCR/VLM reprocessing.

## Why Rule-Based From Current TXT Instead Of Redoing OCR

Use rule-based section detachment from current `.txt` now.

Reasons:

1. The repository already has 591 OCR page files.
2. Many headings and lesson boundaries are visible in the OCR text.
3. Rule-based chunking is cheaper, reproducible, and easy to audit.
4. Redoing OCR or using VLM can introduce non-determinism and hallucinated descriptions.
5. The paper needs a clear, rerunnable preprocessing method.
6. Page-trace metadata can preserve exact citation even after section merging.

Use OCR/VLM reprocessing later only if rule-based section detection fails on too many pages or figures/tables become essential evidence.

## Main Pipeline

Stage 3 should run this pipeline:

1. Load `configs/graph.yaml`.
2. Read every `.txt` file under `data/corpus`.
3. Parse page metadata from file paths.
4. Normalize Unicode and whitespace.
5. Save cleaned page-level records to `pages.json`.
6. Detect headings and section boundaries using rules.
7. Merge consecutive page text into section-aware chunks.
8. Add previous-section overlap when configured.
9. Split oversized chunks when configured.
10. Preserve source page traces in every section chunk.
11. Fall back to page chunks when section detection is uncertain.
12. Save final retrieval chunks to `chunks.json`.
13. Save a cleaning and chunking report.
14. Inspect samples from `lichsu_10`, `lichsu_11`, and `lichsu_12`.

## Expected Command

Implementation file:

```text
src/graph_rag/clean_corpus.py
```

Expected command:

```bash
python3 -m src.graph_rag.clean_corpus --config configs/graph.yaml
```

## Outputs

Stage 3 should create:

```text
data/outputs/corpus/pages.json
data/outputs/corpus/chunks.json
data/outputs/reports/corpus_cleaning_report.md
```

Purpose of each artifact:

| Artifact | Purpose |
|---|---|
| `pages.json` | Cleaned page-level OCR records for traceability and audit |
| `chunks.json` | Section-aware chunks for new RAG and future GraphRAG |
| `corpus_cleaning_report.md` | Cleaning, chunking, filtering, fallback, and sample report |

The script must not modify files under `data/corpus/`.

## Config Changes Needed

Update `configs/graph.yaml` so Stage 3 has both page and section chunk outputs:

```yaml
paths:
  corpus_dir: data/corpus
  cleaned_pages: data/outputs/corpus/pages.json
  cleaned_chunks: data/outputs/corpus/chunks.json
  corpus_report: data/outputs/reports/corpus_cleaning_report.md

corpus_cleaning:
  unicode_form: NFC
  normalize_whitespace: true
  min_chars: 80
  keep_original_txt: true

chunking:
  method: section_aware_rule_based
  max_chars: 3500
  min_chars: 120
  overlap_prev_sections: 1
  split_overlap_chars: 300
  keep_page_trace: true
  fallback_to_page_chunks: true
  filter_exercise_blocks: true
```

Keep existing Stage 4-12 path keys in the same config.

## Page Metadata Parsing

From this file:

```text
data/corpus/lichsu_11/lichsu_11.pdf_141.jpg.txt
```

Parse:

```json
{
  "page_id": "lichsu_11_p141",
  "book": "lichsu_11",
  "page": 141,
  "source": "data/corpus/lichsu_11/lichsu_11.pdf_141.jpg.txt"
}
```

The page number should be extracted from:

```text
*.pdf_<page>.jpg.txt
```

If a file does not match the expected pattern, skip it and record the reason in the report.

## Text Cleaning Rules

Use conservative cleaning:

1. Normalize Unicode using the configured form, currently `NFC`.
2. Normalize repeated whitespace and broken line breaks.
3. Trim leading and trailing whitespace.
4. Keep Vietnamese accents and original wording.
5. Do not manually rewrite OCR mistakes.
6. Do not remove historical content aggressively.

The goal is to reduce formatting noise without changing source meaning.

## Page Record Schema

Each record in `pages.json` should look like:

```json
{
  "page_id": "lichsu_11_p141",
  "book": "lichsu_11",
  "page": 141,
  "source": "data/corpus/lichsu_11/lichsu_11.pdf_141.jpg.txt",
  "text": "Cleaned page text...",
  "char_count": 1800,
  "year_mentions": [1908, 1911, 1912, 1913]
}
```

`pages.json` is not the main retrieval corpus. It is the traceable source layer used to build and audit section chunks.

## Heading Detection Rules

Detect lesson starts:

```text
Bài 23
Bài 23:
BÀI 23
```

Detect major section headings:

```text
I.
II.
III.
I -
II -
III -
```

Detect numbered section headings:

```text
1.
2.
3.
1 -
2 -
3 -
```

Detect uppercase historical titles:

```text
PHONG TRÀO YẾU NƯỚC VÀ CÁCH MẠNG Ở VIỆT NAM
CHIẾN TRANH THẾ GIỚI THỨ HAI
VIỆT NAM TỪ NĂM 1858 ĐẾN CUỐI THẾ KỈ XIX
```

Detect exercise or question blocks:

```text
Câu hỏi
Câu hỏi và bài tập
Bài tập
Hãy nêu
Dựa vào
```

Exercise blocks should either be filtered out or marked as `exercise` chunks depending on confidence and usefulness.

## Chunk Construction Rules

Build chunks from detected sections:

1. Sort cleaned pages by `book`, then `page`.
2. Process each book independently.
3. Start a new lesson block when a `Bài <number>` heading is detected.
4. Start a new section block when a major or numbered section heading is detected.
5. Append continuation text from later pages until the next section or lesson boundary.
6. Preserve all source pages used by the chunk.
7. Add previous-section overlap when `overlap_prev_sections > 0`.
8. If a chunk exceeds `chunking.max_chars`, split it with `split_overlap_chars` overlap.
9. If no reliable section boundary is found, fall back to page-level chunking for that region.

This adapts the HisGraphRAG idea:

```text
section chunk = previous section overlap + current detected section
```

## Section Chunk Schema

Each section-aware chunk in `chunks.json` should look like:

```json
{
  "chunk_id": "lichsu_11_bai23_sec1_001",
  "chunk_type": "section",
  "chunking_method": "section_aware_rule_based",
  "book": "lichsu_11",
  "chapter": "Bài 23",
  "section": "Phan Bội Châu và xu hướng bạo động",
  "pages": [140, 141],
  "source_pages": ["lichsu_11_p140", "lichsu_11_p141"],
  "source_files": [
    "data/corpus/lichsu_11/lichsu_11.pdf_140.jpg.txt",
    "data/corpus/lichsu_11/lichsu_11.pdf_141.jpg.txt"
  ],
  "text": "Cleaned section-aware text...",
  "char_count": 3200,
  "year_mentions": [1904, 1908, 1911, 1912],
  "prev_chunk_id": "lichsu_11_bai22_sec3_001",
  "next_chunk_id": "lichsu_11_bai23_sec2_001",
  "section_confidence": "high",
  "fallback_used": false
}
```

Required fields:

```text
chunk_id
chunk_type
chunking_method
book
chapter
section
pages
source_pages
source_files
text
char_count
year_mentions
prev_chunk_id
next_chunk_id
section_confidence
fallback_used
```

## Fallback Chunk Schema

If section detection is unreliable, create a page fallback chunk:

```json
{
  "chunk_id": "lichsu_11_p141",
  "chunk_type": "page_fallback",
  "chunking_method": "page_fallback",
  "book": "lichsu_11",
  "chapter": null,
  "section": null,
  "pages": [141],
  "source_pages": ["lichsu_11_p141"],
  "source_files": ["data/corpus/lichsu_11/lichsu_11.pdf_141.jpg.txt"],
  "text": "Cleaned page text...",
  "char_count": 1800,
  "year_mentions": [1908, 1911, 1912, 1913],
  "prev_chunk_id": null,
  "next_chunk_id": null,
  "section_confidence": "low",
  "fallback_used": true
}
```

Fallback is important because bad section splitting is worse than conservative page chunks.

## Chunk IDs

Suggested ID formats:

```text
section chunk:  {book}_bai{lesson}_sec{section}_{part}
fallback chunk: {book}_p{page}
```

Examples:

```text
lichsu_11_bai23_sec1_001
lichsu_11_bai23_sec2_001
lichsu_11_p141
```

IDs must be stable across reruns because later graph nodes and edges will cite these chunks.

## Year Extraction

Extract four-digit years from cleaned text using `src/common/normalize.py` where possible.

Expected examples:

```text
1858, 1904, 1930, 1945, 1975, 2000
```

Save sorted unique integers:

```json
"year_mentions": [1904, 1908, 1911, 1912]
```

## Cleaning And Chunking Report

Write `data/outputs/reports/corpus_cleaning_report.md` with:

1. Total raw files.
2. Total cleaned pages.
3. Total output chunks.
4. Section-aware chunk count.
5. Page fallback chunk count.
6. Filtered page count.
7. Counts by book.
8. Chunking config used.
9. Heading detection counts.
10. Exercise/question block counts.
11. Oversized split counts.
12. Fallback reasons and examples.
13. Kept section chunk samples from each book.

Example outline:

```md
# Corpus Cleaning And Chunking Report

## Summary

- Total raw files: 591
- Cleaned pages: ...
- Output chunks: ...
- Section-aware chunks: ...
- Page fallback chunks: ...
- Filtered pages: ...

## By Book

| Book | Raw Pages | Cleaned Pages | Section Chunks | Fallback Chunks |
|---|---:|---:|---:|---:|

## Config

## Heading Detection

## Fallback Reasons

## Samples
```

## Validation Checklist

After implementation, run:

```bash
python3 -m src.graph_rag.clean_corpus --config configs/graph.yaml
```

Then verify:

1. `data/outputs/corpus/pages.json` exists.
2. `data/outputs/corpus/chunks.json` exists.
3. `data/outputs/reports/corpus_cleaning_report.md` exists.
4. Both JSON files are valid.
5. Every page record has required page fields.
6. Every chunk has required chunk fields.
7. `chunk_id` values are unique.
8. `source_files` point to existing files.
9. `source_pages` point to records in `pages.json`.
10. `year_mentions` values are sorted integers.
11. `prev_chunk_id` and `next_chunk_id` point to existing chunks or are `null`.
12. Original `data/corpus/*.txt` files are unchanged.

## Manual Inspection Checklist

Inspect samples from:

```text
lichsu_10
lichsu_11
lichsu_12
```

Check whether:

1. Section chunks are more coherent than raw pages.
2. Multi-page sections are merged correctly.
3. Pages with multiple sections are split correctly.
4. Exercise/question sections are filtered or marked correctly.
5. Page trace metadata matches original source files.
6. Fallback chunks are reasonable and not overused.
7. OCR mistakes are preserved rather than silently rewritten.

## Success Criteria

Stage 3 is successful when:

1. The output chunks are not just page chunks.
2. Most chunks follow textbook lesson or section boundaries.
3. Every chunk can cite original page numbers and source files.
4. The method is deterministic and rerunnable.
5. The report explains how many chunks were section-aware vs fallback.
6. The output can be used by retrieval and later graph extraction.

## Out Of Scope For Stage 3

Do not implement these in Stage 3:

1. Entity extraction.
2. Event extraction.
3. Relation extraction.
4. Graph nodes or graph edges.
5. Graph retrieval.
6. Claim parsing.
7. LLM-based extraction.
8. Full PDF/VLM reprocessing.
9. Manual OCR correction.

These belong to later stages or optional upgrades.

## TODO.md Updates After Completion

After implementation and validation, update Stage 3 TODOs to reflect the new section-aware method:

```md
- [x] Update `configs/graph.yaml` with Stage 3-12 paths and corpus-cleaning options.
- [x] Create `src/graph_rag/clean_corpus.py` using `configs/graph.yaml`.
- [x] Normalize Unicode for all corpus pages.
- [x] Normalize whitespace and broken line breaks.
- [x] Save cleaned page records to `data/outputs/corpus/pages.json`.
- [x] Detect section boundaries from OCR text.
- [x] Build section-aware chunks with page-trace metadata.
- [x] Add trace metadata: `char_count`, `year_mentions`, `prev_chunk_id`, `next_chunk_id`.
- [x] Save section-aware chunks to `data/outputs/corpus/chunks.json`.
- [x] Save cleaning and chunking summary to `data/outputs/reports/corpus_cleaning_report.md`.
- [x] Keep original `.txt` files unchanged.
- [x] Inspect samples from grades 10, 11, and 12.
```

## Next Step

After this plan is accepted:

1. Update `configs/graph.yaml` with `cleaned_pages` and `chunking` settings.
2. Implement `src/graph_rag/clean_corpus.py`.
3. Run the Stage 3 command.
4. Inspect `pages.json`, `chunks.json`, and the report.
5. Update `TODO.md` only after validation passes.

Once Stage 3 is complete, move to Stage 4: define `docs/graph_schema.md` and keep it aligned with `configs/graph.yaml`.
