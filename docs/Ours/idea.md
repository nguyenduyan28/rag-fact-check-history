# Our Project Idea: Vietnamese History Claim Verification

This note summarizes the current pipeline in this repo and turns it into a paper-development idea.

## Main Task

Our project is not exactly multiple-choice question answering. It is better framed as:

> Vietnamese historical claim verification with evidence-grounded LLM and RAG baselines.

The system builds a dataset of Vietnamese history claims labeled `real` or `fake`, then evaluates whether LLMs and RAG-based retrieval can verify those claims using textbook evidence.

## Current Data Sources

The project uses two main source families:

- **Vietnamese history textbooks**
  - History textbooks for grades 10, 11, and 12.
  - OCR/text extraction outputs are stored under `data/4.rag/output/lichsu_{10,11,12}/`.
  - Event/evidence data appears under `data/1.event_evidence/`.

- **Multiple-choice QA datasets**
  - VNHSGE: Vietnamese national high-school history exam style questions.
  - VMLU: Vietnamese multitask QA dataset, filtered to history-related categories.

Current final dataset snapshot:

- `data/final_dataset.json`: 8722 claims.
- Label distribution:
  - fake: 6504
  - real: 2218
- RAG verification output:
  - `data/4.rag/verify_rag.json`: 8722 verified claims.

Important mismatch to check:

- `Repord.md` reports 9185 claims.
- `data/final_dataset.json` currently contains 8722 claims.
- `data/2.claims/VMLU/VMLU_claims.json` exists with 304 claims, but VMLU does not appear clearly in the current final dataset schema.

## Data Construction Pipeline

### 1. Textbook Evidence Pipeline

1. Start from Vietnamese history textbook PDFs.
2. OCR or extract text from page images.
3. Extract historical events and supporting evidence sentences.
4. Store evidence by event/key.
5. Generate **real claims** from each evidence sentence.
6. Generate **fake claims** by modifying real claims.

Fake claim modification types include:

- changing dates or numbers
- replacing people, places, or organizations
- reversing event outcomes
- adding false information
- removing important information

This creates the `v2` subset:

- `data/2.claims/v2/su_kien_viet_nam_real.json`: 593 real claims.
- `data/2.claims/v2/su_kien_viet_nam_fake.json`: 593 fake claims.
- This subset is balanced and has evidence attached.

### 2. QA-to-Claim Pipeline

For VNHSGE and VMLU:

1. Load multiple-choice history questions.
2. Keep the question, choices, correct answer, and explanation if available.
3. Ask an LLM to create:
   - one short `key` describing the historical topic
   - one `real` claim from the correct answer
   - three `fake` claims from the wrong answer options
4. Store one claim per answer option.

Current generated QA-derived subsets:

- `data/2.claims/VNHSGE/VNHSGE_full.json`: 7999 claims.
- `data/2.claims/VMLU/VMLU_claims.json`: 304 claims.

Key issue:

- VNHSGE naturally creates a 1-real / 3-fake ratio from each 4-choice question, so it strongly increases fake-label imbalance.

### 3. Merge Pipeline

The intended merged schema is:

```json
{
  "ID": "...",
  "key": "...",
  "claim": "...",
  "relevant": "...",
  "label": "real|fake",
  "source": "v2|vnhsge|vmlu"
}
```

But the current `data/final_dataset.json` does not include a `source` field. This makes source-specific analysis harder and can hide whether results are coming from textbook-generated claims or QA-generated claims.

## Verification Pipeline

### Blind LLM Verification

The blind verification task gives the model:

- `key`
- `relevant`
- `claim`

The model does not see the gold label. It predicts `real` or `fake` and gives short reasoning.

Reported blind evaluation:

- Total evaluated records: 9185 in `Repord.md`.
- Accuracy: 84.81%.
- Precision: 77.57%.
- Recall: 64.50%.
- F1: 70.44%.
- Real-claim accuracy: 64.50%.
- Fake-claim accuracy: 92.73%.

Interpretation:

- The model is much better at detecting fake claims than confirming real claims.
- This may come from dataset imbalance, fake-claim style artifacts, or insufficient evidence.

### RAG Verification

The RAG stage uses hybrid retrieval:

- Corpus: OCR/text chunks from grades 10, 11, and 12 history textbooks.
- Query: `key + claim`.
- Sparse retrieval: BM25.
- Dense retrieval: BAAI/bge-m3.
- Fusion: Reciprocal Rank Fusion.
- Final retrieved documents: top 5.

Configuration from `4.rag/src/rag.yaml`:

- BM25 top-k: 10.
- Dense top-k: 10.
- RRF k: 60.
- Final top-k: 5.
- Device: CUDA.

The re-verification stage currently sends only the **top-1 retrieved document** to GPT-4o-mini and asks it to output `real` or `fake`.

Reported RAG verification result:

- Total valid samples: 8722.
- Overall accuracy: 75.80%.
- Real precision: 0.51.
- Real recall: 0.84.
- Fake precision: 0.93.
- Fake recall: 0.73.

Interpretation:

- RAG improves real-claim recall compared with blind verification, but creates many fake -> real errors.
- Using only top-1 evidence may be too brittle.
- Retrieval may find related but not decisive context, which makes the verifier over-trust weak evidence.

## Main Method

The current main method can be described as:

> A Vietnamese history claim-verification pipeline that constructs evidence-linked real/fake claims from textbooks and QA datasets, then benchmarks blind LLM verification and hybrid BM25+dense RAG verification.

Core components:

- **Claim construction**
  - Convert events and QA options into declarative claims.
  - Label claims as real/fake according to source evidence or correct/wrong options.

- **Evidence grounding**
  - Keep textbook evidence for generated claims when available.
  - Retrieve supporting textbook passages for claims using hybrid retrieval.

- **Blind LLM judging**
  - Measure whether an LLM can verify claims from provided evidence.

- **RAG-based judging**
  - Retrieve evidence from textbook chunks.
  - Ask an LLM to verify the claim using retrieved context.

- **Dataset and evaluation analysis**
  - Measure label distribution, evidence length, claims per key, duplicate claims, empty evidence, accuracy, precision, recall, F1, and confusion matrix.

## Strong Paper Framing

A good paper direction:

> We introduce a Vietnamese historical claim verification dataset and benchmark, built from textbooks and exam-style QA data, and analyze how blind LLM judging and hybrid retrieval-augmented judging behave under evidence quality, label imbalance, and generated-fake-claim noise.

Possible paper contributions:

- A Vietnamese history claim-verification dataset.
- A pipeline for transforming textbook evidence and MCQ questions into real/fake claims.
- A hybrid BM25 + dense retrieval baseline for evidence retrieval.
- A blind LLM verification baseline.
- A RAG verification baseline.
- Error analysis of evidence quality, label imbalance, and generated fake-claim artifacts.

## Main Weaknesses To Fix Before Paper

1. **The task definition is not yet clean**
   - Textbook evidence claims, VNHSGE claims, and VMLU claims are mixed.
   - They have different generation logic and evidence quality.
   - The paper must clearly separate subsets and report per-subset results.

2. **Label imbalance is severe**
   - The final dataset has about 74.6% fake claims.
   - Accuracy alone is misleading.
   - Macro F1, per-label recall, balanced accuracy, and source-specific results are necessary.

3. **Generated fake claims may contain artifacts**
   - Fake claims are created by an LLM using predictable transformations.
   - Models may learn fake style rather than historical truth.
   - Need human validation or artifact analysis.

4. **Evidence quality is inconsistent**
   - Many VNHSGE rows may have empty or weak `relevant`.
   - The current `relevant_units` metric under-counts quote-style evidence.
   - The paper needs cleaner evidence statistics.

5. **RAG uses only top-1 evidence for final verification**
   - Retrieval stores top 5, but verifier only uses `item["relevant"][0]`.
   - This wastes retrieval output and makes RAG sensitive to the first result.
   - Reranking or multi-document verification should be added.

6. **No retrieval evaluation yet**
   - Current RAG evaluation measures final classification only.
   - It does not measure whether retrieved evidence is actually correct.
   - Add Recall@k, MRR, hit rate, or human evidence relevance checks.

7. **No ablation study yet**
   - Need compare:
     - LLM-only
     - gold evidence
     - BM25 only
     - dense only
     - BM25 + dense RRF
     - top-1 vs top-3 vs top-5 context
     - with vs without key in query

8. **Reproducibility problems exist**
   - Some scripts use absolute paths under `/home/khoa/Documents/GitHub/...`.
   - `4.rag/src/rag.yaml` points to `data/4.rag/final_dataset.json`, but that file is currently missing.
   - `3.Verify/pipeline.py` imports `config`, but `3.Verify/config.py` is not present in the repo.
   - Some reports mention 9185 records while current final files contain 8722.

9. **Vietnamese BM25 tokenization is too simple**
   - Current BM25 uses `text.split()`.
   - Vietnamese tokenization needs word segmentation or at least normalized syllable-aware preprocessing.
   - This can hurt keyword retrieval.

10. **Train/test leakage risk**
   - Multiple claims can share the same `key`, event, evidence sentence, or original question.
   - Splits should be grouped by key/question/event, not random claim rows.
