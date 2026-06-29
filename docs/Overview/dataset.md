# Dataset

## Files

| File | Vai trò |
|---|---|
| [`data/claims/final_dataset.json`](../../data/claims/final_dataset.json) | Dataset gốc |
| [`data/claims/clean_dataset.json`](../../data/claims/clean_dataset.json) | Dataset sau khi bỏ claim lặp và claim conflict nhãn |
| [`data/claims/clean_dataset_report.json`](../../data/claims/clean_dataset_report.json) | Report thống kê sau khi clean |

## Thống kê sau clean

| Nhãn | Số mẫu | Tỷ lệ |
|---|---:|---:|
| `fake` | 7.830 | 69,02% |
| `real` | 3.514 | 30,98% |
| **Tổng** | **11.344** | **100%** |

| Chỉ số | Giá trị |
|---|---:|
| Unique keys | 2.051 |
| Trung bình claims/key | 5,53 |
| Trung bình real claims/key | 1,71 |
| Trung bình fake claims/key | 3,82 |
| Keys có cả `real` và `fake` | 1.543 |
| Keys không có `real` claims | 488 |
| Keys không có `fake` claims | 20 |

## Cleaning

Script xử lý: [`src/dataset/clean_dataset.py`](../../src/dataset/clean_dataset.py)

Config input/output: [`configs/dataset.yaml`](../../configs/dataset.yaml)

Kết quả clean:

| Chỉ số | Giá trị |
|---|---:|
| Số mẫu gốc | 11.491 |
| Số mẫu sau clean | 11.344 |
| Số mẫu bị loại | 147 |
| Claim lặp bị loại | 141 |
| Claim conflict nhãn bị loại | 3 nhóm |
| Unique keys trước clean | 2.060 |
| Unique keys sau clean | 2.051 |

Lệnh chạy:

```bash
python3 src/dataset/clean_dataset.py
```

## Schema record

Mỗi record có dạng:

```json
{
  "ID": "1_fake",
  "key": "Mệnh đề/sự kiện gốc dùng làm cơ sở",
  "claim": "Claim cần kiểm chứng",
  "relevant": "Bằng chứng hoặc đoạn thông tin liên quan",
  "label": "fake"
}
```

Ý nghĩa các trường:

| Trường | Mô tả |
|---|---|
| `ID` | Mã định danh duy nhất của mẫu |
| `key` | Sự kiện hoặc tri thức gốc |
| `claim` | Phát biểu cần kiểm chứng |
| `relevant` | Bằng chứng/ngữ cảnh hỗ trợ việc kiểm chứng |
| `label` | Nhãn kết luận: `real` hoặc `fake` |
