# FacetGraphRAG Pipeline

## Mục Tiêu

Pipeline này triển khai experiment FacetGraphRAG: tách claim thành facet, match facet vào graph đã build từ corpus, lấy evidence 1-hop, rerank evidence, rồi đưa evidence vào verifier để dự đoán `real/fake`.

## Input Chính

| Thành phần | File |
|---|---|
| Claims sạch | `data/claims/clean_dataset.json` |
| Graph nodes | `data/outputs/graph/graph_nodes.json` |
| Graph edges | `data/outputs/graph/graph_edges.json` |
| Entity aliases | `data/outputs/graph/entity_aliases.json` |
| Temporal index | `data/outputs/graph/temporal_index.json` |
| Config | `configs/facet/facet.yaml` |

## Pipeline

| Bước | Script | Input | Output | Làm gì |
|---|---|---|---|---|
| 1. Facet extraction | `src/facet/extract_claim_facets.py` | claim | `claim_facets.json` | Tách claim thành `person`, `organization`, `event`, `place`, `time`, `concept`, `quantity`, `action`, `result`. Có thể chạy deterministic hoặc OpenAI qua `.env`. |
| 2. Facet matching | `src/facet/match_facets.py` | facets + aliases/graph | `facet_matches.json` | Match facet vào node graph bằng exact alias, normalized alias và year index. |
| 3. Evidence retrieval | `src/facet/retrieve_evidence.py` | facet matches + graph | `facet_evidence.json` | Lấy chunks liên quan từ node mentions, temporal index và quan hệ 1-hop. |
| 4. Reranking | `src/facet/rerank_evidence.py` | evidence candidates | `facet_reranked.json` | Chấm điểm evidence bằng facet coverage, relation score, temporal score và text overlap. |
| 5. EDA | `src/facet/evaluate_facet.py` | reranked evidence | `facet_eda_report.md`, `facet_run_report.json` | Thống kê label, facet distribution, match rate, evidence coverage, chunk/book được dùng nhiều. |
| 6. Verification | `src/facet/verify_facet.py` | `facet_reranked.json` hoặc `hybrid_facet_reranked.json` | `verify/<model>/facet_verified.json` | Đưa claim, facets và top evidence vào OpenAI/Gemini verifier để dự đoán `real/fake`. |
| 7. Accuracy | `src/facet/evaluate_verified.py` | `facet_verified.json` | `facet_accuracy_report.md` | Tính accuracy, precision/recall, confusion matrix và lỗi theo facet. |

## Output

Tất cả output nằm trong:

```text
data/outputs/facet/
```

Các file chính:

| File | Ý nghĩa |
|---|---|
| `claim_facets.json` | Claim đã được tách facet. |
| `facet_matches.json` | Mỗi facet match được node nào trong graph. |
| `facet_evidence.json` | Evidence chunks lấy từ graph/temporal/1-hop. |
| `facet_reranked.json` | Top evidence đã rerank, sẵn sàng đưa vào verifier. |
| `facet_eda_report.md` | Report đọc nhanh về chất lượng facet/retrieval. |
| `facet_run_report.json` | Report dạng JSON để dùng tiếp trong code. |
| `verify/<model>/facet_verified.json` | Kết quả verifier real/fake theo từng model. |
| `facet_accuracy_report.md` | Report accuracy sau verifier. |

## Lệnh Chạy

Chạy deterministic, không tốn API:

```bash
python3 -m src.facet.run_facet_r001 --no-llm
```

Chạy thử 50 claims:

```bash
python3 -m src.facet.run_facet_r001 --limit 50 --no-llm --no-resume
```

Chạy với OpenAI facet extractor, dùng `OPENAI_API_KEY` trong `.env`:

```bash
python3 -m src.facet.run_facet_r001 --limit 50 --use-llm --batch-size 10 --no-resume
```

Nếu bật `--use-llm`, cần cài dependency:

```bash
pip install -r requirements.txt
```

Mặc định pipeline sẽ fail rõ nếu OpenAI call lỗi. Chỉ bật fallback deterministic khi thật sự muốn debug:

```yaml
extractor:
  fallback_on_llm_error: true
```

## EDA Cần Xem

Sau khi chạy, ưu tiên xem:

| Metric | Ý nghĩa |
|---|---|
| Rows with top evidence | Bao nhiêu claim lấy được evidence. |
| Facet values | Mỗi loại facet sinh ra bao nhiêu giá trị. |
| Facet match rate | Facet match được vào graph bao nhiêu phần trăm. |
| Evidence books | Evidence đến từ sách lớp nào. |
| Top reused chunks | Chunk nào bị dùng quá nhiều, có thể là evidence quá chung. |

Nếu `time`, `place`, `person`, `organization`, `event` match thấp thì cần cải thiện alias/LLM extraction trước khi nối verifier.

## Verifier Theo Model

Verifier hỗ trợ `--provider openai` và `--provider gemini`. Output nên để riêng theo model để so sánh công bằng và không ghi đè kết quả.

Chạy thử GPT-4o-mini trên R001 graph-only:

```bash
python3 -m src.facet.verify_facet \
  --provider openai --model gpt-4o-mini \
  --output-dir data/outputs/facet/verify/gpt-4o-mini \
  --limit 500 --balanced --workers 2 --batch-size 5

python3 -m src.facet.evaluate_verified \
  --input-path data/outputs/facet/verify/gpt-4o-mini/facet_verified.json \
  --output-report data/outputs/facet/verify/gpt-4o-mini/accuracy_report.md
```

Chạy thử Gemini 2.5 Flash trên R001 graph-only:

```bash
python3 -m src.facet.verify_facet \
  --provider gemini --model gemini-2.5-flash \
  --output-dir data/outputs/facet/verify/gemini-2.5-flash \
  --limit 500 --balanced --workers 2 --batch-size 5

python3 -m src.facet.evaluate_verified \
  --input-path data/outputs/facet/verify/gemini-2.5-flash/facet_verified.json \
  --output-report data/outputs/facet/verify/gemini-2.5-flash/accuracy_report.md
```

OpenAI đọc `OPENAI_API_KEY`. Gemini đọc `GEMINI_API_KEY`/`GOOGLE_API_KEY`, hoặc dùng Vertex AI nếu có `GOOGLE_CLOUD_PROJECT`/`VERTEX_PROJECT_ID`/`PROJECT_ID` trong `.env`. Verifier có resume/checkpoint, nên nếu dừng giữa chừng chỉ cần chạy lại cùng lệnh, không thêm `--no-resume`.

## Hybrid Text + FacetGraph

Fuse text retrieval cũ với facet/graph evidence:

```bash
python3 -m src.facet.fuse_hybrid_facet
```

Chạy sample verifier cho bản hybrid fused:

```bash
python3 -m src.facet.verify_facet \
  --provider openai --model gpt-4o-mini \
  --input-path data/outputs/facet/hybrid_facet_reranked.json \
  --output-dir data/outputs/facet/verify/hybrid-gpt-4o-mini \
  --limit 500 --balanced --workers 2 --batch-size 5

python3 -m src.facet.evaluate_verified \
  --input-path data/outputs/facet/verify/hybrid-gpt-4o-mini/facet_verified.json \
  --output-report data/outputs/facet/verify/hybrid-gpt-4o-mini/accuracy_report.md
```

Chạy full hybrid:

```bash
python3 -m src.facet.verify_facet \
  --provider openai --model gpt-4o-mini \
  --input-path data/outputs/facet/hybrid_facet_reranked.json \
  --output-dir data/outputs/facet/verify/hybrid-gpt-4o-mini \
  --workers 2 --batch-size 5

python3 -m src.facet.evaluate_verified \
  --input-path data/outputs/facet/verify/hybrid-gpt-4o-mini/facet_verified.json \
  --output-report data/outputs/facet/verify/hybrid-gpt-4o-mini/accuracy_report.md
```

Chạy full hybrid bằng Gemini 2.5 Flash:

```bash
python3 -m src.facet.verify_facet \
  --provider gemini --model gemini-2.5-flash \
  --input-path data/outputs/facet/hybrid_facet_reranked.json \
  --output-dir data/outputs/facet/verify/hybrid-gemini-2.5-flash \
  --workers 2 --batch-size 5

python3 -m src.facet.evaluate_verified \
  --input-path data/outputs/facet/verify/hybrid-gemini-2.5-flash/facet_verified.json \
  --output-report data/outputs/facet/verify/hybrid-gemini-2.5-flash/accuracy_report.md
```
