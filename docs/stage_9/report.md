# Stage 9 Report: Claim Parser

## Summary

Stage 9 implementation is complete and smoke-tested.

This stage parses claim text into graph retrieval signals using a hybrid method: deterministic years and alias matching plus Gemini structured claim parsing.

Current run status:

| Artifact | Count / Purpose |
|---|---|
| `data/claims/final_dataset.json` | 11491 input claims |
| `src/graph_rag/parse_claims.py` | Hybrid claim parser implementation |
| `data/outputs/claims/parsed_claims.json` | 5 parsed smoke-test claims |
| `data/outputs/claims/claim_parse_errors.json` | 0 smoke-test errors |
| `data/outputs/reports/claim_parser_report.md` | Smoke-test parser report |

The full dataset run is intentionally not launched automatically because it requires 11491 Gemini calls.

## Problem

Graph retrieval cannot use raw claim text alone. It needs structured signals:

1. Years and dates for temporal retrieval.
2. Entity mentions for graph node matching.
3. Event phrases for graph fact retrieval.
4. Relation hints for selecting useful graph neighborhoods.
5. Claim focus signals such as time, place, actor, event, cause, result, number, or sequence.

Stage 9 converts each `key + claim` into those retrieval signals.

## Method

Method name:

```text
Hybrid deterministic and Gemini claim parsing for graph retrieval signals
```

The parser has two parts:

1. Deterministic parser for stable signals.
2. Gemini parser for semantic structure.

This is better than LLM-only parsing because canonical graph IDs should come from the alias map, not from model guesses.

It is better than rules-only parsing because Vietnamese historical claims contain event roles, relation intent, and implicit focus that are hard to capture with string rules alone.

## Implementation

Implementation file:

```text
src/graph_rag/parse_claims.py
```

Config block:

```yaml
claim_parsing:
  provider: gemini_vertex
  model: gemini-2.5-flash
  temperature: 0.0
  max_output_tokens: 2048
  thinking_budget: 0
  workers: 4
  checkpoint_every: 50
  retry_attempts: 2
  query_fields:
    - key
    - claim
  max_alias_matches: 30
  min_alias_chars: 4
  max_llm_mentions: 20
  max_llm_relations: 12
```

## Deterministic Parsing

The deterministic part does three things:

1. Builds query text from `key + claim`.
2. Extracts four-digit years with the shared `extract_years()` rule.
3. Matches normalized aliases from `entity_aliases.json` against the query.

Alias matching is conservative:

1. Aliases shorter than `min_alias_chars` are skipped.
2. Longer aliases are matched first.
3. Exact normalized phrase matching is used.
4. Matches are mapped to canonical entity IDs from Stage 6.

This produces fields such as:

```json
{
  "years": [1910, 1919, 1929, 1933, 1955],
  "alias_matches": [
    {
      "entity_id": "ent_001226",
      "canonical_name": "Pháp",
      "canonical_type": "Organization",
      "matched_alias": "thực dân Pháp"
    }
  ]
}
```

## Gemini Parsing

Gemini receives the claim, rule-extracted years, and deterministic alias matches. It must return JSON only.

Gemini extracts:

1. `time_expressions`
2. `entity_mentions`
3. `event_mentions`
4. `relation_hints`
5. `claim_focus`
6. `keywords`

The parser uses Gemini response schema constraints:

```text
response_mime_type = application/json
response_schema = claim parser schema
thinking_budget = 0
```

Gemini is not asked to verify the claim. It only parses retrieval signals.

## Commands

Smoke test:

```bash
python3 -m src.graph_rag.parse_claims --config configs/graph.yaml --limit 5 --workers 1 --checkpoint-every 1 --no-resume
```

Full run:

```bash
python3 -m src.graph_rag.parse_claims --config configs/graph.yaml --workers 4 --checkpoint-every 50
```

Retry only errors:

```bash
python3 -m src.graph_rag.parse_claims --config configs/graph.yaml --retry-errors --workers 4 --checkpoint-every 50
```

Deterministic-only mode:

```bash
python3 -m src.graph_rag.parse_claims --config configs/graph.yaml --no-llm
```

## Smoke-Test Result

Smoke-test command completed successfully on 5 claims.

| Metric | Count |
|---|---:|
| Parsed claims | 5 |
| Parse errors | 0 |
| Claims with years | 5 |
| Claims with alias matches | 5 |
| Claims with LLM entity mentions | 5 |
| Claims with LLM event mentions | 5 |

Alias match type counts in smoke test:

| Type | Matches |
|---|---:|
| Time | 15 |
| Place | 11 |
| Event | 6 |
| Organization | 6 |
| Concept | 5 |

Claim focus counts in smoke test:

| Focus | Count |
|---|---:|
| time | 4 |
| place | 3 |
| actor | 3 |
| event | 3 |
| number | 2 |
| concept | 2 |
| object | 1 |
| cause | 1 |
| result | 1 |

## Quality Notes

Strengths:

1. The parser combines exact canonical entity matching with semantic claim parsing.
2. The smoke test returned structured years, aliases, entities, events, relations, and focus labels.
3. Errors are checkpointed separately and resumable.
4. Full parsing can resume from existing smoke-test rows.

Limitations:

1. The full 11491-claim run has not been executed yet.
2. Alias matching can still match broad concepts if they appear literally in the claim.
3. Gemini parsing quality should be sampled after a larger run.
4. Stage 10 retrieval should treat parsed signals as retrieval hints, not as truth labels.

## Conclusion

Stage 9 is implemented and smoke-tested. The next operational step is to run the parser over all 11491 claims when API cost and runtime are acceptable.
