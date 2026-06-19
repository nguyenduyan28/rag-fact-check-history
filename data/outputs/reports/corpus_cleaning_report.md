# Corpus Cleaning And Chunking Report

## Summary

- Total raw files: 591
- Cleaned pages: 571
- Output chunks: 540
- Section-aware chunks: 540
- Page fallback chunks: 0
- Filtered pages: 20
- Exercise blocks filtered: 159
- Oversized sections split: 131

## By Book

| Book | Cleaned Pages | Section Chunks | Fallback Chunks |
|---|---:|---:|---:|
| lichsu_10 | 199 | 152 | 0 |
| lichsu_11 | 153 | 113 | 0 |
| lichsu_12 | 219 | 275 | 0 |

## Config

- Unicode form: NFC
- Normalize whitespace: True
- Page min chars: 80
- Chunking method: section_aware_rule_based
- Chunk min chars: 120
- Chunk max chars: 2200
- Previous-section overlap: 1

## Heading Detection

| Heading Type | Count |
|---|---:|
| lesson | 54 |
| lesson_marker | 33 |
| major_section | 56 |
| numbered_section | 135 |
| uppercase_heading | 441 |

## Filter Reasons

| Reason | Count |
|---|---:|
| publication_or_index_page | 10 |
| too_short | 10 |

## Fallback Reasons

| Reason | Count |
|---|---:|

## Sample Chunks

### lichsu_10

- Chunk ID: `lichsu_10_s9_001`
- Type: `section`
- Pages: [4]
- Years: []
- Preview: VÀ BÂY NGƯỜI NGUYÊN THUÝ Lịch sử loài người cho ta biết những sự việc diễn ra trong đời sống còn người kể từ khi xuất hiện trên Trái Đất. Khoa học, đặc biệt là Khảo cổ học và Cổ sinh học, đã tìm được nhiều bằng cứ nói lên sự phát triển lâu dài từ động vật cấp thấp lên động vật cấp cao đủnh cao của q

### lichsu_11

- Chunk ID: `lichsu_11_s6_001`
- Type: `section`
- Pages: [4, 5, 6]
- Years: [1868]
- Preview: Bài NHẬT BẢN Cuộc Duy tân Minh Trị năm 1868 có ý nghĩa như một cuộc cách mạng tư sản, đã đưa Nhật Bản phát triển theo con đường của các nước phương Tây và trở thành một nước đế quốc duy nhất ở châu Á. 1 Nhật Bản từ đầu thế kỉ XIX đến trước năm 1868 Đên giữa thế kỉ XIX, sau hơn 200 năm thống trị, chế

### lichsu_12

- Chunk ID: `lichsu_12_s13_bai1_sec3_001`
- Type: `section`
- Pages: [4]
- Years: [1949]
- Preview: SAU CHIẾN TRANH THẾ GIỚI THỨ HAI (1949) Chiến tranh thế giới thứ hai kết thúc đã mở ra một giai đoạn phát triển mới của tinh hình thế giới Một trật tư thế giới mới được hình thành với đặc trưng lớn là thế giới chia thành hai phe ? tư bản chủ nghĩa và xã hòi chủ nghia, do hai siêu cường Mĩ và Liên Xô
