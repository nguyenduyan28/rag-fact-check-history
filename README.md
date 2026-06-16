# Vietnamese History RAG

Clean repo for Vietnamese historical claim verification with RAG and future GraphRAG experiments.

## Current Task

Given a Vietnamese history claim, retrieve textbook evidence from grades 10, 11, and 12, then classify the claim as `real` or `fake`.

Input claim schema:

```json
{
  "ID": "...",
  "key": "topic summary",
  "claim": "claim to verify",
  "relevant": "gold/source evidence when available",
  "label": "real|fake"
}
```

## Data Included

```text
data/claims/final_dataset.json
data/corpus/lichsu_10/*.txt
data/corpus/lichsu_11/*.txt
data/corpus/lichsu_12/*.txt
```

Corpus size at migration time:

```text
lichsu_10: 206 chunks
lichsu_11: 159 chunks
lichsu_12: 226 chunks
claims: 8722
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill `OPENAI_API_KEY` in `.env` if running LLM verification.

## Run Hybrid RAG

Retrieve evidence:

```bash
python -m src.rag.retrieve --config configs/rag.yaml
```

Verify with top-k retrieved evidence:

```bash
python -m src.rag.verify --config configs/verify.yaml
```

Evaluate predictions:

```bash
python -m src.rag.evaluate --config configs/eval.yaml
```

## Method Roadmap

1. Hybrid text RAG baseline: BM25 + BGE-M3 + RRF.
2. Multi-evidence verifier: use top-3/top-5 evidence, not top-1 only.
3. Temporal/entity-aware reranking: score retrieved chunks by year and entity overlap.
4. GraphRAG: extract entities/events/relations, build graph, combine graph and text evidence.

## Why This Repo Exists

The original project contains dataset generation, blind LLM evaluation, OCR, RAG, reports, and exploratory files. This repo keeps only the data and code needed for RAG/GraphRAG experiments.
