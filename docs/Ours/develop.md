# Development Roadmap For Our Paper

Goal:

> Turn the current Vietnamese history claim-verification pipeline into a stronger, reproducible paper with clearer data, stronger baselines, retrieval analysis, and optional trainable components.

## Priority Improvement Table

| Priority | Area | What To Improve | Why It Matters | Concrete Action | Related Files | Paper Value |
|---:|---|---|---|---|---|---|
| 1 | Reproducibility | Fix missing configs and absolute paths | A paper experiment must be rerunnable | Replace `/home/khoa/Documents/GitHub/...` paths with repo-relative paths; restore or document `3.Verify/config.py`; make one command for each stage | `1.Prepare_Dataset/*.py`, `2.Claim/*.py`, `3.Verify/pipeline.py`, `4.rag/src/*.yaml` | Very high |
| 2 | Dataset versioning | Freeze one final dataset version | Current reports mention 9185 records, but current final file has 8722 | Create `data/releases/v1/` with dataset, stats, generation config, and checksum | `data/final_dataset.json`, `Repord.md` | Very high |
| 3 | Schema | Add missing metadata columns | Need source-specific and error-specific analysis | Add `source`, `origin_id`, `origin_type`, `fake_type`, `evidence_type`, `generation_model` | `data/final_dataset.json`, claim generation scripts | Very high |
| 4 | Data balance | Build balanced evaluation splits | Current data is fake-heavy, so accuracy is misleading | Create balanced test set and source-stratified test set; report macro F1 and balanced accuracy | `3.Verify/metrics.py`, new split script | Very high |
| 5 | Data leakage | Group split by event/question/key | Random claim split can leak same evidence across train/test | Split by `key`, original question ID, or event ID | new split script | Very high |
| 6 | Evidence quality | Separate gold, empty, retrieved, noisy evidence | Claims from different sources do not have equal evidence quality | Add `evidence_type`; report results by evidence type | `2.Claim`, `4.rag/src/rag.py` | High |
| 7 | Fake claim quality | Validate fake claims | LLM-generated fake claims may be artificial or too easy | Human review sample; check if fake is really false; classify fake type | `2.Claim/fake/generator.py`, review script | High |
| 8 | OCR cleaning | Reduce noisy textbook chunks | OCR noise can break retrieval and verification | Remove map/table noise; normalize Unicode; drop pages with mostly garbage text; keep page metadata | `data/4.rag/output/`, new cleaning script | High |
| 9 | Vietnamese retrieval | Improve BM25 tokenization | `text.split()` is weak for Vietnamese | Try VnCoreNLP, underthesea, pyvi, or syllable + phrase normalization | `4.rag/src/rag.py` | High |
| 10 | RAG context | Use top-k evidence, not only top-1 | Current verifier ignores 4 of 5 retrieved passages | Compare top-1, top-3, top-5; concatenate or rerank before verification | `4.rag/src/verify_rag.py` | Very high |
| 11 | Retrieval metrics | Evaluate retrieval directly | Need know whether error is retrieval or verifier | Compute Recall@k/Hit@k using gold evidence when available; human judge top-k relevance for sample | new retrieval eval script | Very high |
| 12 | Baselines | Add proper baselines | Paper needs fair comparison | Majority baseline, LLM-only, gold evidence, BM25, dense, hybrid RRF | `3.Verify`, `4.rag/src` | Very high |
| 13 | Ablation | Show what helps | Strong papers need component analysis | Compare query styles, top-k, rerank, temporal filter, entity filter | new experiment config | Very high |
| 14 | Prompting | Make verifier output evidence decision | Current RAG prompt only outputs label | Ask model to quote/cite evidence sentence, contradiction type, final label | `4.rag/src/verify_rag.py`, `3.Verify/methods/llm_judge.py` | High |
| 15 | Error analysis | Analyze failure types | This can become a main paper contribution | Categorize false real/false fake by source, fake type, OCR quality, retrieval hit/miss | new analysis notebook/script | Very high |

## Training Ideas

Training is possible, but it should come after the dataset and evaluation are cleaned. The safest path is to train small components first, not the full LLM.

| Priority | Trainable Component | Training Data | Objective | How To Build | Expected Benefit | Risk |
|---:|---|---|---|---|---|---|
| 1 | Cross-encoder reranker | Claim + retrieved chunk pairs | Relevant / not relevant | Use gold evidence as positive; use retrieved wrong chunks as hard negatives | Better top-k evidence before LLM verification | Needs labeled relevance data |
| 2 | Evidence verifier classifier | Claim + evidence + label | Predict `real/fake` | Fine-tune PhoBERT, XLM-R, viDeBERTa, or mDeBERTa | Cheap, reproducible baseline without API cost | May learn fake-generation artifacts |
| 3 | NLI-style verifier | Evidence premise + claim hypothesis | Entailment / contradiction / unknown | Convert real to entailment, fake to contradiction; add hard unknown cases | More explainable than binary classifier | Needs neutral/unknown labels |
| 4 | Dense retriever fine-tuning | Query + positive evidence + hard negatives | Contrastive retrieval | Fine-tune BGE-M3 or multilingual sentence transformer | Better Vietnamese history retrieval | More expensive and needs careful negatives |
| 5 | Fake-type classifier | Fake claim + original real claim | Predict fake manipulation type | Use `changes.type` from fake generation | Better error analysis and dataset control | Only applies to generated fake claims |
| 6 | LLM LoRA verifier | Claim + evidence + label/reasoning | Instruction tuning | Use Qwen/Llama/Vistral-style Vietnamese-capable model | Local verifier for paper experiments | Highest cost, leakage risk, harder to justify |

Best first training experiment:

> Train a **cross-encoder reranker** for claim-evidence relevance, then keep GPT-4o-mini or another LLM as the final verifier.

Why this is good:

- It improves the weakest current RAG step.
- It is easier to evaluate with Recall@k/MRR.
- It avoids overclaiming that a trained classifier understands history.
- It connects well with HisGraphRAG's reranking idea.

## Suggested New Method

Name idea:

> Temporal-Entity Hybrid RAG for Vietnamese Historical Claim Verification

Pipeline:

| Step | Module | Description |
|---:|---|---|
| 1 | Claim parser | Extract entities, dates, periods, and event keywords from the claim |
| 2 | Hybrid retriever | Retrieve top 20 chunks using BM25 + dense retrieval |
| 3 | Entity/time scorer | Add score for entity overlap and temporal overlap |
| 4 | Reranker | Rerank top 20 into top 3 or top 5 |
| 5 | Evidence verifier | Verify claim using selected evidence and output label + evidence citation |
| 6 | Error analyzer | Classify error as retrieval miss, weak evidence, verifier mistake, or data-label problem |

This gives a clearer method contribution than the current plain RAG pipeline.

## Minimum Experiment Tables For The Paper

| Table | What To Report | Why |
|---|---|---|
| Dataset statistics | claims by source, real/fake counts, evidence availability, claim length, evidence length | Shows dataset quality |
| Blind verification | LLM-only, LLM with provided evidence, per-source metrics | Shows whether LLM can judge claims |
| RAG baselines | BM25, dense, hybrid RRF | Shows retrieval method effect |
| RAG ablation | top-1/top-3/top-5, claim-only vs key+claim, with/without rerank | Shows which design matters |
| Retrieval evaluation | Recall@1, Recall@3, Recall@5, MRR, human relevance sample | Separates retrieval from verification |
| Error analysis | false real, false fake, by source, fake type, OCR noise, retrieval hit/miss | Makes paper stronger |
| Training result | no-reranker vs trained reranker, or zero-shot verifier vs trained verifier | Shows development beyond prompting |

## Recommended Development Order

| Stage | Work | Output |
|---:|---|---|
| 1 | Clean reproducibility and paths | Repo can rerun from commands |
| 2 | Freeze dataset v1 | Stable dataset for paper tables |
| 3 | Add metadata fields | Source/fake/evidence analysis possible |
| 4 | Recompute EDA | Correct dataset statistics |
| 5 | Build baseline experiments | Majority, LLM-only, gold evidence, BM25, dense, hybrid |
| 6 | Fix RAG verifier to use top-k | Better RAG baseline |
| 7 | Add retrieval metrics | Know if retrieval works |
| 8 | Add reranker or temporal/entity scoring | New method contribution |
| 9 | Optional training | Cross-encoder reranker or verifier classifier |
| 10 | Final error analysis | Paper discussion and limitations |

## Concrete Short-Term TODO

| TODO | Expected File |
|---|---|
| Add `source` to every row in final dataset | new script under `data/` or `2.Claim/` |
| Add `fake_type` from `changes.type` | `2.Claim/fake/generator.py` output or postprocess script |
| Fix `verify_rag.py` to use top 3 or top 5 evidence | `4.rag/src/verify_rag.py` |
| Add BM25-only and dense-only switches | `4.rag/src/rag.py`, `rag.yaml` |
| Add retrieval evaluation script | `4.rag/src/eval_retrieval.py` |
| Add source-specific metrics | `3.Verify/metrics.py`, `4.rag/src/eda.py` |
| Create paper dataset release folder | `data/releases/v1/` |

## What Not To Claim Yet

| Claim To Avoid | Why |
|---|---|
| "Our method is GraphRAG" | Current method has no graph construction or graph traversal |
| "Our accuracy is better than HisGraphRAG" | Different task: binary claim verification vs MCQ QA |
| "RAG improves everything" | Current RAG accuracy is lower than blind LLM overall |
| "The dataset is fully verified" | Generated fake claims and evidence quality still need human validation |
| "The model understands Vietnamese history" | It may exploit artifacts, label imbalance, or generated fake style |

## Best Paper Direction

The strongest direction is:

> Build and analyze a Vietnamese historical claim-verification benchmark, then propose a hybrid retrieval + temporal/entity reranking method for evidence-grounded verification.

This lets the paper contribute both:

- a dataset/benchmark, and
- a practical retrieval improvement inspired by the weaknesses of plain RAG and HisGraphRAG.
