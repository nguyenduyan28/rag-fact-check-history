# Hệ thống phát hiện tin giả về lịch sử Việt Nam dựa trên tài liệu Trung học phổ thông

Mã nguồn kèm khóa luận tốt nghiệp — Trường Đại học Khoa học Tự nhiên, ĐHQG-HCM.
Sinh viên: Nguyễn Duy Ân (22127006), Đỗ Lê Khoa (22127195).

Hệ thống đề xuất **Facet Graph RAG**: truy xuất Hybrid (BM25 + BGE-M3 + RRF) kết hợp kênh
bằng chứng đồ thị tri thức qua phân rã nhận định thành 9 loại khía cạnh; kiểm chứng bằng
LLM và sinh lời giải thích chỉ đích danh khía cạnh sai lệch.

## 1. Cấu trúc thư mục

```
FINAL/
├── src/                          # Mã nguồn (dataset / graph_rag / rag / facet / experiments / common)
├── configs/                      # Cấu hình YAML (facet/facet_full.yaml = cấu hình chính thức)
├── data/                         # Dữ liệu đủ để chạy lại hệ thống
│   ├── claims/clean_dataset.json           # 11.344 nhận định (nhãn + bằng chứng tham chiếu)
│   └── outputs/
│       ├── corpus/chunks.json              # 540 đoạn văn SGK Lịch sử 10-12 (đã làm sạch)
│       ├── graph/                          # Đồ thị tri thức + bí danh + chỉ mục thời gian
│       └── facet/full-opt2/claim_facets.json  # Khía cạnh đã phân rã sẵn (tiết kiệm API khi tái lập)
├── ket_qua/                      # Kết quả thí nghiệm, chia theo tập dữ liệu
│   ├── KET_QUA.md                          # BẢNG TỔNG HỢP (đọc file này trước)
│   ├── balance_dataset_2000/               # 2.000 câu cân bằng (nền 50%): bm25 / dense_bgem3 /
│   │                                       #   hybrid / facet_graph_rag / oracle_500 / 2 ablation
│   ├── full_dataset_11344/facet_graph_rag/ # KẾT QUẢ CHÍNH: 81,46% acc / 79,37% macro F1
│   └── tap_phan_tang_kho_2000/             # 2 ablation trên mẫu phân tầng khó
├── requirements.txt
└── README.md
```

Mỗi thư mục run trong `ket_qua/` chứa `facet_verified.json` (kết quả từng nhận định, gồm
nhãn dự đoán, bằng chứng trích dẫn, khía cạnh sai, lời giải thích) và `accuracy_report.md`.

## 2. Cài đặt

Yêu cầu: Python 3.10+; GPU khuyến nghị cho bước mã hóa BGE-M3 (không bắt buộc).

```bash
cd FINAL
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Tạo file `.env` tại thư mục `FINAL/`:

```
OPENAI_API_KEY=...      # bước phân rã khía cạnh (GPT-4o-mini) — chỉ cần khi chạy lại từ đầu
GEMINI_API_KEY=...      # bộ kiểm chứng (Gemini 2.5 Flash)
```

## 3. Chạy thử nhanh (5 phút, ~20 yêu cầu API)

Kiểm chứng lại 20 nhận định của cấu hình oracle (input kèm sẵn) và tính kết quả:

```bash
python3 -m src.facet.verify_facet --config configs/facet/facet_full.yaml \
  --provider gemini --model gemini-2.5-flash \
  --input-path ket_qua/balance_dataset_2000/oracle_500/verify_input.json \
  --output-dir /tmp/test_oracle --limit 20 --balanced --workers 2 --batch-size 1

python3 -m src.facet.evaluate_verified --config configs/facet/facet_full.yaml \
  --input-path /tmp/test_oracle/facet_verified.json \
  --output-report /tmp/test_oracle/accuracy_report.md
cat /tmp/test_oracle/accuracy_report.md
```

Kỳ vọng: độ chính xác xấp xỉ 100% (oracle được cấp bằng chứng vàng — cấu hình chẩn đoán).

## 4. Tái lập toàn bộ hệ thống đề xuất (Facet Graph RAG)

Chạy tuần tự từ thư mục `FINAL/` (mọi đường dẫn trong configs đã khớp sẵn):

```bash
# B1 — Truy xuất văn bản Hybrid (cục bộ, tải BGE-M3 ~2.3GB lần đầu, không tốn API):
python3 -m src.rag.retrieve --config configs/rag_nokey.yaml

# B2 — Khớp khía cạnh vào đồ thị -> thu bằng chứng -> xếp hạng (cục bộ, tất định;
#      dùng khía cạnh đã phân rã sẵn trong data/outputs/facet/full-opt2/claim_facets.json):
python3 -m src.facet.match_facets     --config configs/facet/facet_full.yaml
python3 -m src.facet.retrieve_evidence --config configs/facet/facet_full.yaml
python3 -m src.facet.rerank_evidence  --config configs/facet/facet_full.yaml

# B3 — Hợp nhất 5 văn bản + 3 đồ thị (cục bộ):
python3 -m src.facet.fuse_hybrid_facet --config configs/facet/facet_full.yaml

# B4 — Kiểm chứng 11.344 nhận định (~11.344 yêu cầu Gemini; có checkpoint,
#      dừng giữa chừng chạy lại đúng lệnh là tiếp tục):
python3 -m src.facet.verify_facet --config configs/facet/facet_full.yaml \
  --provider gemini --model gemini-2.5-flash \
  --input-path data/outputs/facet/full-opt2/hybrid_facet_reranked.json \
  --output-dir data/outputs/facet/full-opt2/verify/gemini-2.5-flash \
  --workers 2 --batch-size 1

# B5 — Tính kết quả:
python3 -m src.facet.evaluate_verified --config configs/facet/facet_full.yaml \
  --input-path data/outputs/facet/full-opt2/verify/gemini-2.5-flash/facet_verified.json \
  --output-report accuracy_report.md
```

Muốn phân rã khía cạnh lại từ đầu (thay vì dùng file kèm sẵn): chạy
`python3 -m src.facet.run_facet_r001 --config configs/facet/facet_full.yaml --limit 11344 --use-llm --workers 2 --batch-size 10`
trước B2 (tốn ~1.135 yêu cầu GPT-4o-mini).

Các phương pháp đối sánh (BM25 / Dense / Hybrid thuần văn bản): dựng input bằng
`python3 -m src.experiments.build_eval_inputs` từ kết quả B1, rồi kiểm chứng bằng đúng
lệnh B4 (đổi `--input-path`) — bảo đảm mọi hệ được chấm trong cùng điều kiện.

## 5. Kết quả chính

Xem bảng đầy đủ tại `ket_qua/KET_QUA.md`. Tóm tắt:

| Cấu hình | Tập đánh giá | Accuracy | Macro F1 |
|---|---|---:|---:|
| Dense (BGE-M3) | 2.000 cân bằng | 84,60% | 84,55% |
| BM25 | 2.000 cân bằng | 87,45% | 87,45% |
| Facet Graph RAG (đề xuất) | 2.000 cân bằng | 88,10% | 88,10% |
| Hybrid (BM25+BGE-M3+RRF) | 2.000 cân bằng | 87,05% | 87,05% |
| **Facet Graph RAG (đề xuất)** | **11.344 toàn bộ** | **81,46%** | **79,37%** |
| Oracle (chẩn đoán) | 500 cân bằng | 99,80% | — |

## 6. Ghi chú

- Toàn bộ tầng truy xuất (BM25, vec-tơ, khớp khía cạnh, đồ thị, xếp hạng) tất định,
  chạy cục bộ, tái lập được; chỉ hai bước gọi API: phân rã khía cạnh và kiểm chứng.
- Nguyên tắc đánh giá: các trường sinh dữ liệu (tri thức gốc, bằng chứng vàng, nhãn)
  không bao giờ xuất hiện trong truy vấn truy xuất hay prompt của mô hình.
- Kho OCR gốc của sách giáo khoa không kèm theo (bản quyền); `chunks.json` là bản
  đã làm sạch đủ để tái lập mọi bước phía sau.
