# Pipeline Tổng Quan

File này mô tả 4 pipeline chính:

```text
Pipeline tạo dataset
Pipeline tạo graph
Pipeline tạo facet
Pipeline inference
```

Mục tiêu cuối cùng:

```text
Claim lịch sử tiếng Việt
---> retrieval evidence từ SGK Lịch sử 10, 11, 12
---> verifier GPT/Gemini
---> dự đoán real/fake
```

---

# 1. Pipeline Tạo Dataset

## 1.1 Flow

```text
Raw generated claims
---> final_dataset.json
---> clean_dataset.py
---> remove duplicate claims
---> remove conflicting labels
---> validate required fields
---> clean_dataset.json
---> clean_dataset_report.json
```

## 1.2 Input

```text
data/claims/final_dataset.json
```

Mỗi row có dạng:

```json
{
  "ID": "1_fake",
  "key": "sự kiện hoặc tri thức gốc",
  "claim": "claim cần kiểm chứng",
  "relevant": "bằng chứng/ngữ cảnh liên quan",
  "label": "real|fake"
}
```

## 1.3 Xử Lý

Script:

```text
src/dataset/clean_dataset.py
```

Config:

```text
configs/dataset.yaml
```

Logic clean:

```text
final_dataset.json
---> kiểm tra required fields: ID, key, claim, relevant, label
---> group theo claim
---> nếu claim lặp cùng label: giữ 1 bản
---> nếu claim lặp nhưng conflict label real/fake: drop toàn bộ nhóm conflict
---> ghi clean_dataset.json
---> ghi clean_dataset_report.json
```

## 1.4 Output

| File | Vai trò |
|---|---|
| `data/claims/clean_dataset.json` | Dataset sạch dùng cho retrieval/verifier. |
| `data/claims/clean_dataset_report.json` | Thống kê sau clean. |

Thống kê sau clean:

| Chỉ số | Giá trị |
|---|---:|
| Tổng claims | 11,344 |
| Real claims | 3,514 |
| Fake claims | 7,830 |
| Unique keys | 2,051 |

## 1.5 Edge Cases

| Tình huống | Cách xử lý |
|---|---|
| Claim bị lặp cùng label | Giữ 1 claim, bỏ bản trùng. |
| Claim giống nhau nhưng có cả `real` và `fake` | Drop toàn bộ nhóm vì label conflict. |
| Thiếu field bắt buộc | Không dùng row đó. |
| Key không có real hoặc không có fake | Vẫn giữ, chỉ thống kê trong report. |

---

# 2. Pipeline Tạo Graph

## 2.1 Flow

```text
3 cuốn SGK Lịch sử 10, 11, 12
---> OCR từng trang
---> data/corpus/lichsu_10, lichsu_11, lichsu_12
---> clean corpus
---> chunking theo sách/bài/mục
---> chunks.json
---> NER/entity extraction
---> relation extraction
---> entity alignment/alias merge
---> build graph nodes + edges
---> build entity aliases
---> graph outputs
```

## 2.2 Input

Nguồn tri thức:

| Sách | Raw OCR pages |
|---|---:|
| Lịch sử 10 | 206 |
| Lịch sử 11 | 159 |
| Lịch sử 12 | 226 |
| Tổng | 591 |

Raw OCR:

```text
data/corpus/lichsu_10/
data/corpus/lichsu_11/
data/corpus/lichsu_12/
```

Ví dụ:

```text
data/corpus/lichsu_12/lichsu_12.pdf_223.jpg.txt
```

## 2.3 Clean Corpus Và Chunking

Flow:

```text
Raw OCR pages
---> bỏ câu hỏi/bài tập/chú thích hình/header/footer nếu detect được
---> giữ nội dung lịch sử chính
---> detect heading/bài/mục
---> gom text thành chunk
---> thêm metadata: book, section, pages, source_files
---> chunks.json
```

Output:

```text
data/outputs/corpus/chunks.json
```

Số chunk hiện tại:

```text
540 chunks
```

Mỗi chunk có dạng:

```json
{
  "chunk_id": "lichsu_12_s124_bai12_sec7_001",
  "book": "lichsu_12",
  "section": "2. Chính sách chính trị, văn hoá, giáo dục của thực dân Pháp",
  "pages": [76],
  "source_files": ["..."],
  "text": "...",
  "year_mentions": [1912, 1930]
}
```

## 2.4 Entity Và Relation

Từ mỗi chunk:

```text
chunk text
---> extract entities
---> extract relations giữa entities
---> lưu source_chunk cho từng relation
```

Node types chính:

| Node type | Ví dụ |
|---|---|
| `Person` | Hồ Chí Minh, Nguyễn Ái Quốc |
| `Organization` | thực dân Pháp, Đảng Cộng sản Việt Nam |
| `Event` | Cách mạng tháng Tám |
| `Place` | Đông Dương, Campuchia |
| `Time` | 1945, 1954 |
| `Concept` | khai thác thuộc địa |

Relation types dùng cho retrieval:

```text
PARTICIPATED_IN
OCCURRED_AT
LOCATED_IN
RELATED_TO
CAUSES
RESULTS_IN
BEFORE
AFTER
```

## 2.5 Chunk Nối Với Graph Như Thế Nào?

Graph có 2 kiểu liên hệ với chunk:

```text
chunk --MENTIONS--> node
edge --source_chunk--> chunk
```

Ví dụ:

```text
chunk_A --MENTIONS--> node_Pháp
chunk_A --MENTIONS--> node_khai_thác_thuộc_địa

node_Pháp --RELATED_TO--> node_khai_thác_thuộc_địa
                       |
                       +-- source_chunk = chunk_A
```

Ý nghĩa:

| Liên hệ | Dùng để làm gì |
|---|---|
| `MENTIONS` | Biết node nào được nhắc trong chunk nào. |
| `source_chunk` trên edge | Biết relation được trích ra từ chunk nào. |

## 2.6 Output Graph

| File | Vai trò |
|---|---|
| `data/outputs/graph/graph_nodes.json` | Danh sách nodes. |
| `data/outputs/graph/graph_edges.json` | Danh sách edges. |
| `data/outputs/graph/entity_aliases.json` | Alias để match facet text vào node. |
| `data/outputs/graph/temporal_index.json` | Index thời gian/năm nếu cần dùng. |

## 2.7 Edge Cases

| Tình huống | Cách xử lý |
|---|---|
| Một entity có nhiều tên gọi | Dùng `entity_aliases.json` để gom alias về canonical node. |
| Một chunk nhắc nhiều nodes | Tạo nhiều edge `MENTIONS`. |
| Một relation được trích từ chunk | Edge lưu `source_chunk`. |
| Entity bị trùng sau extraction | Entity alignment/alias merge gom lại. |
| Relation không nằm trong whitelist retrieval | Không dùng ở bước inference graph retrieval. |

---

# 3. Pipeline Tạo Facet

## 3.1 Flow

```text
clean_dataset.json
---> lấy từng claim
---> facet extraction
---> person / organization / event / place / time / concept / quantity / action / result
---> claim_facets.json
---> match facets vào graph aliases/nodes
---> facet_matches.json
```

## 3.2 Facet Là Gì?

Facet là các phần nhỏ của claim cần kiểm chứng.

Ví dụ claim:

```text
Thực dân Pháp đã triển khai chương trình khai thác thuộc địa lần thứ hai tại Đông Dương, chủ yếu tập trung ở Campuchia, bắt đầu vào năm 1910 và kéo dài cho tới 1955.
```

Facet output:

```json
{
  "person": [],
  "organization": ["thực dân Pháp"],
  "event": ["chương trình khai thác thuộc địa lần thứ hai"],
  "place": ["Đông Dương", "Campuchia"],
  "time": ["1910", "1955"],
  "concept": ["khai thác thuộc địa"],
  "quantity": [],
  "action": [],
  "result": []
}
```

## 3.3 Facet Types

| Facet | Ý nghĩa |
|---|---|
| `person` | Nhân vật. |
| `organization` | Tổ chức/lực lượng/nhà nước. |
| `event` | Sự kiện/văn kiện/giai đoạn. |
| `place` | Địa điểm/quốc gia/khu vực. |
| `time` | Năm/giai đoạn/mốc thời gian. |
| `concept` | Khái niệm lịch sử/chính trị/xã hội. |
| `quantity` | Con số/số lượng/tỉ lệ. |
| `action` | Hành động chính trong claim. |
| `result` | Kết quả/hệ quả. |

## 3.4 Matching Facet Vào Graph

Flow:

```text
facet value
---> normalize text
---> exact alias match
---> normalized alias match
---> optional year match nếu facet là time
---> graph node matches
```

Graph type map:

| Facet | Chỉ match node type |
|---|---|
| `person` | `Person` |
| `organization` | `Organization` |
| `event` | `Event` |
| `place` | `Place` |
| `time` | `Time` |
| `concept` | `Concept` |

Các facet `quantity`, `action`, `result` hiện không match trực tiếp vào graph node. Chúng vẫn được giữ để verifier đọc claim rõ hơn.

## 3.5 Match Rate

Match summary tính ở cấp claim:

```text
match_rate = matched_facets / total_facets
```

Với claim ví dụ:

```text
total_facets = 7
matched_facets = 5
match_rate = 5 / 7 = 0.7142857142857143
```

Ý nghĩa:

```text
match_rate = graph hiểu được bao nhiêu phần của claim
```

Nó không phải điểm chunk. Nó dùng để debug và đưa metadata cho verifier.

## 3.6 Edge Cases

| Tình huống | Cách xử lý |
|---|---|
| 1 facet match nhiều nodes | Giữ tối đa `max_matches_per_facet = 5`. |
| 1 facet không match node nào | Đánh dấu `matched=false`, facet vẫn được giữ trong JSON. |
| 1 facet value xuất hiện nhiều lần qua nhiều reason | Khi tính coverage sẽ dedup theo `(facet_type, facet_value)`. |
| Facet dài như event/action khó match | Có thể không match nếu alias graph không có cụm tương ứng. |
| Facet time có năm nhưng graph không có node/time index | Không match hoặc match rỗng. |

---

# 4. Pipeline Inference

## 4.1 Flow Tổng Quát

```text
Claim
---> extract facets
---> match facets vào graph nodes
---> retrieve graph chunks từ matched nodes
---> pre-filter candidate chunks
---> rerank graph chunks
---> text retrieval lấy top text chunks
---> fuse text evidence + graph evidence
---> verifier GPT/Gemini
---> label real/fake + reasoning
```

Pipeline hybrid hiện dùng:

```text
Claim
---> Text retrieval: top 3 text chunks
---> Graph retrieval: top 3 graph chunks
---> Fuse thành 6 evidence
---> Gemini/GPT verifier
---> real/fake
```

## 4.2 Bước 1: Claim Thành Facets

Input:

```text
claim = "Thực dân Pháp đã triển khai chương trình khai thác thuộc địa lần thứ hai..."
```

Output:

```text
organization = thực dân Pháp
event = chương trình khai thác thuộc địa lần thứ hai
place = Đông Dương, Campuchia
time = 1910, 1955
concept = khai thác thuộc địa
```

## 4.3 Bước 2: Facets Match Vào Graph Nodes

Flow:

```text
thực dân Pháp
---> normalize
---> alias lookup
---> ent_001226 = Pháp

Đông Dương
---> alias lookup
---> ent_001298 = Đông Dương

Campuchia
---> alias lookup
---> ent_000560 = Campuchia
```

Nếu một facet match nhiều nodes:

```text
facet A
---> node B1
---> node B2
---> node B3
...
---> giữ tối đa 5 nodes
```

Ngưỡng:

```yaml
matching:
  max_matches_per_facet: 5
```

## 4.4 Bước 3: Retrieve Graph Chunks

Từ matched nodes, retrieve chunks bằng 2 nguồn chính:

```text
node mentions
relation 1-hop
```

### 4.4.1 Node Mentions

```text
matched node
---> node này được nhắc trong chunk nào?
---> lấy chunk đó
```

Ví dụ:

```text
Campuchia
---> node ent_000560
---> source chunks có nhắc Campuchia
---> add vào evidence
```

### 4.4.2 Relation 1-Hop

```text
matched node
---> lấy các edge kề node đó đúng 1 bước
---> nếu relation type nằm trong whitelist
---> lấy source_chunk của edge
---> add vào evidence
```

Relation whitelist:

```text
PARTICIPATED_IN
OCCURRED_AT
LOCATED_IN
RELATED_TO
CAUSES
RESULTS_IN
BEFORE
AFTER
```

Ví dụ:

```text
node_Pháp --RELATED_TO--> node_khai_thác_thuộc_địa
                       |
                       +-- source_chunk = lichsu_12_s124_bai12_sec7_001
```

Chunk `lichsu_12_s124_bai12_sec7_001` được lấy vì relation 1-hop.

## 4.5 Nếu 1 Node Có Nhiều Relations Thì Sao?

Ví dụ:

```text
facet A
---> match node B
---> node B có 7 relations
---> 7 relations dẫn tới 10 chunks
```

Logic:

```text
node B
---> lấy source chunks từ node mentions
---> lấy source_chunk từ relation 1-hop
---> gom theo chunk_id để dedup
---> dừng khi facet này đạt max_chunks_per_facet
```

Ngưỡng:

```yaml
evidence:
  max_chunks_per_facet: 5
```

Vì vậy không lấy hết 10 chunks. Mỗi facet chỉ lấy tối đa 5 chunks.

Sau đó toàn claim cũng bị giới hạn:

```yaml
evidence:
  max_chunks_per_claim: 12
```

Flow cắt:

```text
tất cả chunks từ các facets
---> dedup theo chunk_id
---> sort thô
---> lấy tối đa 12 chunks
```

## 4.6 Pre-Filter Trước Rerank

Nếu retrieve ra quá nhiều chunks:

```text
23 candidate chunks
---> pre-filter
---> 12 selected chunks
```

Sort thô trước khi cắt:

```text
1. Chunk hit nhiều facet khác nhau hơn thì lên trước
2. Nếu bằng nhau, chunk có nhiều relation_hits hơn thì lên trước
3. Nếu vẫn bằng nhau, sort theo chunk_id để deterministic
```

Công thức sort thô trong ý nghĩa:

```text
sort_key =
  - unique_facet_hits_count
  - relation_hits_count
  + chunk_id
```

Đây chưa phải rerank cuối. Đây chỉ là lọc thô để tránh quá nhiều chunks nhiễu.

## 4.7 Rerank Graph Chunks

Sau khi còn tối đa 12 chunks, pipeline tính điểm từng chunk.

Công thức rerank dùng trong mô tả hiện tại:

```text
final_score =
  0.55 * facet_coverage
+ 0.35 * relation_score
+ 0.10 * text_overlap
```

### 4.7.1 Facet Coverage

```text
facet_coverage =
  số facet value khác nhau mà chunk hit được
  /
  total_facets của claim
```

Ví dụ claim có 7 facet values:

```text
thực dân Pháp
chương trình khai thác thuộc địa lần thứ hai
Đông Dương
Campuchia
1910
1955
khai thác thuộc địa
```

Nếu chunk hit:

```text
Campuchia
1955
```

thì:

```text
facet_coverage = 2 / 7 = 0.285714
```

Nếu `1955` xuất hiện nhiều lần trong cùng chunk qua nhiều reason:

```text
time=1955 node_mention
time=1955 relation_1hop
```

vẫn chỉ tính 1 facet:

```text
(time, 1955)
```

### 4.7.2 Relation Score

```text
relation_score =
  min(1, log(1 + relation_hits_count) / log(4))
```

Ví dụ chunk có 2 relation hits:

```text
relation_score = log(3) / log(4)
               = 0.792481250360578
```

Nếu chunk không có relation hit:

```text
relation_score = 0
```

### 4.7.3 Text Overlap

```text
text_overlap =
  số token claim xuất hiện trong chunk
  /
  số token claim
```

Tokenization hiện đơn giản:

```text
lowercase
---> split theo khoảng trắng
---> chỉ giữ token dài >= 3 ký tự
```

Ví dụ:

```text
claim tokens = thực, dân, pháp, khai, thác, thuộc, địa, đông, dương, campuchia
chunk tokens = thực, dân, pháp, khai, thác, thuộc, địa, đông, dương
```

```text
text_overlap = 9 / 10 = 0.9
```

## 4.8 Ví Dụ Tính Final Score

Một graph chunk có:

```text
facet_coverage = 0.2857142857142857
relation_score = 0.792481250360578
text_overlap = 0.3870967741935484
```

Tính:

```text
final_score =
  0.55 * 0.2857142857142857
+ 0.35 * 0.792481250360578
+ 0.10 * 0.3870967741935484

= 0.15714285714285714
+ 0.2773684376262023
+ 0.03870967741935484

= 0.4732209721884143
```

Sau rerank:

```text
12 selected chunks
---> tính final_score
---> sort giảm dần theo final_score
---> lấy top 8 graph chunks
```

Ngưỡng:

```yaml
rerank:
  top_k: 8
```

## 4.9 Fuse Text + Graph

Text retrieval đã có sẵn từ baseline:

```text
data/outputs/retrieved/hybrid_top5.json
```

Flow:

```text
top text chunks
---> lấy top 3

top graph chunks
---> lấy top 3

top 3 text + top 3 graph
---> dedup theo chunk_id
---> tối đa 6 evidence
---> đưa verifier
```

Ngưỡng:

```yaml
fusion:
  text_top_k: 3
  graph_top_k: 3
  max_total_evidence: 6
```

## 4.10 Verifier Nhận Những Gì?

Verifier nhận mỗi item gồm:

```text
claim
key/chủ đề
facets đã extract
facet_match_summary
top evidence E1...E6
```

Mỗi evidence có:

```text
evidence_id: E1, E2, ...
chunk_id
book
pages
section
scores
facet_hits
relation_hits
text
```

Verifier trả:

```json
{
  "label": "real|fake",
  "confidence": 0.9,
  "evidence_ids": ["E1", "E3"],
  "wrong_facets": ["time", "place"],
  "reasoning": "lý do ngắn gọn"
}
```

## 4.11 Verifier Models

Có thể chạy nhiều verifier để so:

```text
Hybrid evidence
---> GPT-4o-mini
---> result folder riêng

Hybrid evidence
---> Gemini 2.5 Flash
---> result folder riêng
```

Output:

```text
data/outputs/facet/verify/gpt-4o-mini/facet_verified.json
data/outputs/facet/verify/gemini-2.5-flash/facet_verified.json
```

## 4.12 Edge Cases Trong Inference

| Tình huống | Logic hiện tại |
|---|---|
| 1 facet match nhiều nodes | Giữ tối đa 5 nodes. |
| 1 node có nhiều relations | Chỉ lấy relation thuộc whitelist, lấy tối đa theo `max_chunks_per_facet`. |
| Nhiều relations cùng source chunk | Dedup thành 1 evidence chunk, gom nhiều `relation_hits`. |
| Một chunk hit cùng facet nhiều lần | Dedup khi tính `facet_coverage`. |
| Retrieve ra quá nhiều chunks | Sort thô rồi lấy tối đa 12 chunks. |
| Rerank ra nhiều chunks | Lấy top 8 graph chunks. |
| Fuse text+graph quá nhiều | Lấy top 3 text + top 3 graph, tối đa 6 evidence. |
| Evidence thiếu một số facets | Verifier vẫn thấy `missing_facets` trong summary. |
| Graph evidence nhiễu | Text retrieval trong hybrid có thể bù lại. |

---

# 5. Lệnh Chạy Chính

## 5.1 Clean Dataset

```bash
python3 src/dataset/clean_dataset.py
```

## 5.2 Chạy Facet Graph Retrieval

```bash
python3 -m src.facet.run_facet_r001 --limit 11344 --use-llm --workers 2 --batch-size 10
```

## 5.3 Fuse Text + Graph

```bash
python3 -m src.facet.fuse_hybrid_facet
```

## 5.4 Verify Bằng Gemini

```bash
python3 -m src.facet.verify_facet \
  --provider gemini --model gemini-2.5-flash \
  --input-path data/outputs/facet/hybrid_facet_reranked.json \
  --output-dir data/outputs/facet/verify/gemini-2.5-flash-soft \
  --workers 2 --batch-size 5
```

Evaluate:

```bash
python3 -m src.facet.evaluate_verified \
  --input-path data/outputs/facet/verify/gemini-2.5-flash-soft/facet_verified.json \
  --output-report data/outputs/facet/verify/gemini-2.5-flash-soft/accuracy_report.md
```

## 5.5 Resume Khi Bị Dừng

Verifier có checkpoint/resume.

Nếu bị break:

```text
chạy lại đúng lệnh cũ
không thêm --no-resume
```

Pipeline sẽ đọc file output cũ và chỉ chạy tiếp các row chưa có kết quả hợp lệ.

---

# 6. Ghi Chú Quan Trọng

File này mô tả pipeline theo cách dùng cho báo cáo/thuyết trình. Nếu thay đổi công thức rerank trong tài liệu, cần đồng bộ lại code/config trước khi rerun để output JSON phản ánh đúng công thức mới.
