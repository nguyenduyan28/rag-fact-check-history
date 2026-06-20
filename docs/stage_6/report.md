# Stage 6 Report: Entity Alignment

## Summary

Stage 6 is implemented, but the Gemini review run is not complete yet because Vertex AI Application Default Credentials are missing in the current environment.

This stage converts cleaned per-chunk entity mentions from Stage 5 into canonical graph entities and alias mappings for Stage 7 graph construction.

Main artifacts:

| Artifact | Count / Purpose |
|---|---|
| `data/outputs/graph/extracted_chunks_cleaned.json` | Input from Stage 5, 540 cleaned extraction records |
| `data/outputs/graph/entities_raw.json` | 5866 raw entity mentions collected from cleaned extractions |
| `data/outputs/graph/entities_aligned.json` | 3742 deterministic exact-normalized aligned entities |
| `data/outputs/graph/entity_aliases.json` | Alias and mention-to-entity mapping |
| `data/outputs/graph/entity_alignment_decisions.json` | Gemini merge decisions; currently 0 successful decisions |
| `data/outputs/graph/entity_alignment_errors.json` | Gemini review errors; currently 150 credential errors |
| `data/outputs/reports/entity_alignment_report.md` | Alignment run statistics |

## Problem

Stage 5 extracts useful entities, but each chunk has local entity IDs only. The same historical entity can appear many times with different spellings, aliases, or extraction types.

Examples:

```text
Mỹ / Mĩ / Hoa Kỳ
Liên Xô / Liên bang Xô viết
Nguyễn Ái Quốc / Hồ Chí Minh / Nguyễn Tất Thành
An Nam / Việt Nam / Đại Việt
```

If these variants are not aligned before graph construction, Stage 7 will create duplicate nodes. That would weaken graph traversal and retrieval because evidence mentioning one alias may not connect to claims mentioning another alias.

## Method

Method name:

```text
Deterministic entity normalization with targeted Gemini alias review
```

The implemented method has three parts:

1. Collect raw entity mentions from cleaned Stage 5 output.
2. Deterministically normalize and collapse exact duplicate `(type, normalized_name)` entities.
3. Generate a small set of high-value candidate groups for Gemini alias review.

The Gemini review is intentionally not open-ended. Gemini only reviews candidate groups produced by local code. This avoids sending every entity pair to the model and prevents unbounded alias guessing.

## Code Method: `align_entities.py`

Implementation file:

```text
src/graph_rag/align_entities.py
```

Primary command:

```bash
python3 -m src.graph_rag.align_entities --config configs/graph.yaml
```

Deterministic fallback command:

```bash
python3 -m src.graph_rag.align_entities --config configs/graph.yaml --no-gemini
```

Fresh Gemini rerun command:

```bash
python3 -m src.graph_rag.align_entities --config configs/graph.yaml --no-resume
```

Retry only failed Gemini groups after credentials are fixed:

```bash
python3 -m src.graph_rag.align_entities --config configs/graph.yaml --retry-errors
```

## Raw Entity Collection

The script reads:

```text
data/outputs/graph/extracted_chunks_cleaned.json
```

For every entity mention, it preserves:

```text
mention_id, chunk_id, book, chapter, section, pages, source_pages, source_files,
local_id, type, name, normalized_name, folded_name, aliases, description,
years, evidence_text, confidence
```

Current raw collection result:

| Metric | Count |
|---|---:|
| Raw entity mentions | 5866 |
| Unique normalized `(type, name)` representatives | 3742 |
| Exact normalized mentions collapsed | 2124 |

## Deterministic Normalization

The deterministic stage applies:

1. Unicode NFC normalization.
2. Lowercasing for comparison keys.
3. Punctuation cleanup.
4. Whitespace normalization.
5. Vietnamese accent folding for candidate discovery.
6. Exact `(type, normalized_name)` grouping.

This step is safe and does not require Gemini.

It produced:

```text
3742 aligned entities
3742 alias rows
5866 mention mappings
```

## Gemini Candidate Generation

The first Gemini design generated too many candidate groups:

```text
1213 candidate groups
```

That made a 4-worker run take more than two hours because each group is one Gemini request.

The optimized design now generates:

```text
150 candidate groups
```

Candidate group sources:

| Source | Count |
|---|---:|
| Seed alias groups | 7 |
| Folded-name groups | 60 |
| High-similarity groups | 83 |

The broad country-state sliding window is disabled by default because it created many loosely related groups.

## Seed Alias Groups

The configured seed groups are high-value aliases that Gemini should review first:

```yaml
seed_alias_groups:
  - [Mỹ, Mĩ, Hoa Kỳ, Hoa Kì, Hợp chúng quốc Hoa Kỳ]
  - [Liên Xô, Liên bang Xô viết, Liên bang Xô Viết]
  - [Nguyễn Ái Quốc, Hồ Chí Minh, Nguyễn Tất Thành]
  - [An Nam, Việt Nam, Đại Việt, Đại Cồ Việt]
  - [Pháp, thực dân Pháp, đế quốc Pháp]
  - [Nhật, Nhật Bản, phát xít Nhật]
  - [Việt Minh, Mặt trận Việt Minh, Mặt trận Việt Nam độc lập đồng minh]
```

These are not blindly merged by rules. They are candidate groups for Gemini review, because some are context-dependent.

For example:

1. `Nguyễn Ái Quốc`, `Hồ Chí Minh`, and `Nguyễn Tất Thành` can refer to the same person.
2. `An Nam`, `Việt Nam`, `Đại Việt`, and `Đại Cồ Việt` can refer to related historical names but should not always become one node.
3. `Pháp`, `thực dân Pháp`, and `đế quốc Pháp` can be close in retrieval context but may represent a country, colonial force, or imperial actor.

## Gemini Config

Configured in `configs/graph.yaml`:

```yaml
entity_alignment:
  provider: gemini_vertex
  model: gemini-2.5-flash
  location_env: GOOGLE_CLOUD_LOCATION
  default_location: us-central1
  temperature: 0.0
  max_output_tokens: 2048
  thinking_budget: 0
  workers: 4
  checkpoint_every: 10
  retry_attempts: 2
  min_merge_confidence: 0.8
  max_group_entities: 12
  max_contexts_per_entity: 2
  max_candidate_groups: 150
  enable_similarity_blocks: true
  similarity_threshold: 0.9
  enable_country_state_windows: false
```

The optimized runtime target is minutes instead of hours:

```text
150 groups / 4 workers = about 38 Gemini requests per worker
```

## Gemini Prompt Behavior

Gemini receives one candidate group at a time and must return JSON only.

The prompt tells Gemini to:

1. Merge only names that refer to the same historical entity.
2. Not merge entities only because they are historically related.
3. Avoid cross-type merges except clear extraction-type mistakes, such as a country extracted as both `Place` and `Organization`.
4. Keep `Event` separate from `Organization`, `Place`, and `Person`.
5. Mark uncertain cases as `review_required=true`.
6. Use `confidence >= 0.80` for accepted merges.
7. Preserve original names as aliases.

Expected Gemini output shape:

```json
{
  "aligned_entities": [
    {
      "canonical_name": "Hoa Kỳ",
      "canonical_type": "Place",
      "observed_types": ["Place", "Organization"],
      "aliases": ["Mĩ", "Hoa Kỳ"],
      "member_entity_ids": ["u001748", "u002589"],
      "confidence": 0.9,
      "review_required": false,
      "reason": "Các tên trong input đều chỉ Hoa Kỳ/Mĩ trong ngữ cảnh quốc gia hoặc lực lượng nhà nước."
    }
  ],
  "unmerged_entities": []
}
```

## Validation

Local validation is applied after Gemini returns JSON.

Validation checks:

| Check | Behavior |
|---|---|
| Invalid JSON | Retry, then save group to `entity_alignment_errors.json` |
| Unknown member ID | Drop that member from the merge |
| Fewer than 2 valid members | Drop the merge |
| Empty canonical name | Drop the merge |
| Invalid canonical type | Drop the merge |
| Confidence below `0.8` | Reject merge |
| `review_required=true` | Reject merge for automatic alignment |

This means Gemini can suggest uncertain aliases, but only high-confidence non-review merges are applied automatically.

## Current Result

Current deterministic result:

| Metric | Count |
|---|---:|
| Raw entity mentions | 5866 |
| Unique normalized representatives | 3742 |
| Candidate groups generated | 150 |
| Final aligned entities | 3742 |
| Alias rows | 3742 |
| Mention mappings | 5866 |

Current Gemini result:

| Metric | Count |
|---|---:|
| Gemini decisions | 0 |
| Gemini errors | 150 |
| Accepted Gemini merge decisions | 0 |

Reason for Gemini errors:

```text
Your default credentials were not found. To set up Application Default Credentials,
see https://cloud.google.com/docs/authentication/external/set-up-adc for more information.
```

So the code path is implemented, but the environment needs Vertex AI ADC authentication before Gemini alias review can complete.

## Required Environment

Stage 6 Gemini review uses Vertex AI through `google-genai`.

Required environment:

```text
GOOGLE_CLOUD_PROJECT
GOOGLE_CLOUD_LOCATION
Application Default Credentials for Vertex AI
```

The environment must have valid ADC, for example through a configured service account or local Google Cloud auth setup.

## Quality Assessment

Strengths:

1. Deterministic exact-normalized alignment is complete and reproducible.
2. Raw mention-to-entity mappings are saved for graph construction.
3. Gemini candidate generation is now bounded and focused.
4. The prompt is conservative and rejects uncertain merges automatically.
5. Stage 7 can already use deterministic aligned entities if needed.

Weaknesses:

1. Cross-alias merges like `Mĩ`/`Hoa Kỳ` are not completed until Gemini review succeeds.
2. The current Gemini run failed due to missing ADC credentials.
3. Seed aliases are candidates, not final merges.
4. Ambiguous historical names may still require human review after Gemini.

## Conclusion

Stage 6 implementation is ready and deterministic outputs exist. The remaining work is operational: configure Vertex AI Application Default Credentials and rerun Gemini alias review.

Recommended next command after credentials are fixed:

```bash
python3 -m src.graph_rag.align_entities --config configs/graph.yaml --retry-errors
```

After successful Gemini review, re-check:

```text
data/outputs/graph/entities_aligned.json
data/outputs/graph/entity_aliases.json
data/outputs/graph/entity_alignment_decisions.json
data/outputs/graph/entity_alignment_errors.json
data/outputs/reports/entity_alignment_report.md
```

Next stage after successful alias review:

```text
Stage 7: Build Graph
```
