# BẢNG TỔNG HỢP KẾT QUẢ

Cấu trúc: `balance_dataset_2000/` (2.000 câu cân bằng, mức nền 50%) — `full_dataset_11344/`
(toàn bộ 11.344 câu, mức nền 69%) — `tap_phan_tang_kho_2000/` (mẫu phân tầng thiên nhóm khó).
Mỗi thư mục run chứa `facet_verified.json` (kết quả từng nhận định) và `accuracy_report.md`.

| Thư mục | Cấu hình | Accuracy | Macro F1 | Recall đúng | Recall sai |
|---|---|---:|---:|---:|---:|
| `balance_dataset_2000/bm25/` | BM25 (top-5) | 87.45% | 87.45% | 85.6% | 89.3% |
| `balance_dataset_2000/dense_bgem3/` | Dense BGE-M3 (top-5) | 84.60% | 84.55% | 79.0% | 90.2% |
| `balance_dataset_2000/hybrid/` | Hybrid (BM25+BGE-M3+RRF, top-5) | 87.05% | 87.05% | 87.6% | 86.5% |
| `balance_dataset_2000/facet_graph_rag/` | Facet Graph RAG (đề xuất) | 88.10% | 88.10% | 86.1% | 90.1% |
| `balance_dataset_2000/oracle_500/` | Oracle (bằng chứng vàng) — chẩn đoán | 99.80% | 99.80% | 100.0% | 99.6% |
| `balance_dataset_2000/ablation_baseline/` | Ablation: cấu hình ban đầu | 71.70% | 70.19% | 49.2% | 94.2% |
| `balance_dataset_2000/ablation_4_cai_tien/` | Ablation: +4 cải tiến | 79.83% | 79.69% | 71.7% | 88.0% |
| `full_dataset_11344/facet_graph_rag/` | Facet Graph RAG (đề xuất) — KẾT QUẢ CHÍNH | 81.46% | 79.37% | 80.1% | 82.1% |
| `tap_phan_tang_kho_2000/ablation_cross_encoder/` | Ablation: cross-encoder | 82.15% | 82.14% | 84.3% | 80.0% |
| `tap_phan_tang_kho_2000/ablation_noi_budget/` | Ablation: nới budget 8 đoạn | 82.85% | 82.83% | 86.1% | 79.6% |

Các run trong `balance_dataset_2000/` dùng CÙNG tập nhận định, CÙNG bộ kiểm chứng
(Gemini 2.5 Flash, nhiệt độ 0, smart crop). Oracle là cấu hình chẩn đoán, không phải kết quả hệ thống.
