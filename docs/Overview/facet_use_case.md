# Facet Use Case: `Hồ Chí Minh đến Pháp năm 1911`

Claim ví dụ:

```text
Hồ Chí Minh đến Pháp năm 1911.
```

File này giải thích hệ thống facet/graph retrieval sẽ xử lý claim này như thế nào, từ lúc claim đi vào cho tới khi chọn evidence đưa cho LLM.

Trong ví dụ này dùng ngưỡng giả lập để dễ hiểu:

```yaml
matching:
  max_matches_per_facet: 2   # giả sử tối đa 2 nodes/facet

evidence:
  max_chunks_per_facet: 5
  max_chunks_per_claim: 12

rerank:
  top_k: 8

fusion:
  text_top_k: 3
  graph_top_k: 3
  max_total_evidence: 6
```

Ghi chú: config thật hiện tại đang để `max_matches_per_facet = 5`, nhưng use case này giả sử bằng `2` theo yêu cầu để thấy rõ cách cắt khi match quá nhiều node.

---

# 1. Graph Giả Định

Để giải thích rõ, giả sử graph hiện tại có các nodes, relations và chunks sau.

## 1.1 Nodes

| Node ID | Type | Name | Aliases |
|---|---|---|---|
| `person_hcm` | `Person` | Hồ Chí Minh | Hồ Chí Minh, Nguyễn Ái Quốc, Nguyễn Tất Thành |
| `place_france` | `Place` | Pháp | Pháp, nước Pháp, France |
| `place_marseille` | `Place` | Mác-xây | Mác-xây, Marseille |
| `place_paris` | `Place` | Pa-ri | Pa-ri, Paris |
| `org_france_colonial` | `Organization` | thực dân Pháp | Pháp, thực dân Pháp |
| `time_1911` | `Time` | 1911 | 1911 |
| `event_departure_1911` | `Event` | Nguyễn Tất Thành ra đi tìm đường cứu nước | ra đi tìm đường cứu nước, rời bến Nhà Rồng |
| `event_in_france` | `Event` | Nguyễn Ái Quốc hoạt động ở Pháp | hoạt động ở Pháp, đến Pháp |

Điểm cần chú ý:

```text
Facet "Pháp" có thể match nhiều nodes:
- place_france
- org_france_colonial
- place_paris
- place_marseille
```

Đây là case "1 facet có quá nhiều nodes".

## 1.2 Relations

| Edge ID | Source | Relation | Target | source_chunk |
|---|---|---|---|---|
| `e1` | `person_hcm` | `RELATED_TO` | `event_departure_1911` | `c1` |
| `e2` | `event_departure_1911` | `OCCURRED_AT` | `time_1911` | `c1` |
| `e3` | `event_departure_1911` | `LOCATED_IN` | `place_marseille` | `c1` |
| `e4` | `place_marseille` | `LOCATED_IN` | `place_france` | `c1` |
| `e5` | `person_hcm` | `RELATED_TO` | `event_in_france` | `c2` |
| `e6` | `event_in_france` | `LOCATED_IN` | `place_france` | `c2` |
| `e7` | `person_hcm` | `RELATED_TO` | `place_paris` | `c3` |
| `e8` | `org_france_colonial` | `RELATED_TO` | `place_france` | `c4` |

Relation whitelist dùng để retrieve:

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

Các relation ở bảng trên đều nằm trong whitelist nên đều có thể được dùng.

## 1.3 Chunks

| Chunk ID | Text giả định |
|---|---|
| `c1` | Năm 1911, Nguyễn Tất Thành rời bến Nhà Rồng trên tàu Đô đốc La-tu-sơ Tơ-rê-vin và đến Mác-xây, Pháp. |
| `c2` | Trong thời gian hoạt động ở Pháp, Nguyễn Ái Quốc tham gia phong trào công nhân và tiếp cận chủ nghĩa Mác - Lênin. |
| `c3` | Tại Pa-ri, Nguyễn Ái Quốc gửi bản Yêu sách của nhân dân An Nam tới Hội nghị Vécxai năm 1919. |
| `c4` | Thực dân Pháp tăng cường khai thác thuộc địa ở Đông Dương sau Chiến tranh thế giới thứ nhất. |
| `c5` | Năm 1911, nhiều biến động chính trị diễn ra ở Trung Quốc và khu vực châu Á. |
| `c6` | Hồ Chí Minh là lãnh tụ của cách mạng Việt Nam. |

## 1.4 Mentions Giả Định

Ngoài relation edges ở trên, graph còn có edge `MENTIONS` để biết chunk nào nhắc node nào.

```text
chunk --MENTIONS--> node
```

Ví dụ:

| Chunk | MENTIONS node |
|---|---|
| `c1` | `person_hcm`, `time_1911`, `place_marseille`, `place_france`, `event_departure_1911` |
| `c2` | `person_hcm`, `place_france`, `event_in_france` |
| `c3` | `person_hcm`, `place_paris` |
| `c4` | `org_france_colonial`, `place_france` |
| `c5` | `time_1911` |
| `c6` | `person_hcm` |

Vì vậy có 2 đường để một chunk được lấy:

```text
Đường 1: node mention
chunk --MENTIONS--> matched node

Đường 2: relation 1-hop
matched node --RELATION--> neighbor node
edge.source_chunk = chunk
```

Đây là lý do phần relations chỉ có `source_chunk` từ `c1` tới `c4`, nhưng retrieval vẫn có thể lấy `c5` và `c6`: chúng đến từ `MENTIONS`, không đến từ relation.

---

# 2. Pipeline Tổng Quát Cho Claim

Flow:

```text
Claim
---> Extract facets
---> Match facets vào graph nodes
---> Retrieve chunks từ node mentions + relation 1-hop
---> Pre-filter nếu quá nhiều chunks
---> Rerank chunks
---> Fuse với text retrieval
---> Đưa evidence cho LLM verifier
---> real/fake
```

---

# 3. Extract Facets

Input:

```text
Hồ Chí Minh đến Pháp năm 1911.
```

Facet output giả định:

```json
{
  "person": ["Hồ Chí Minh"],
  "place": ["Pháp"],
  "time": ["1911"],
  "action": ["đến Pháp"],
  "organization": [],
  "event": [],
  "concept": [],
  "quantity": [],
  "result": []
}
```

Đếm facet values:

```text
person = 1
place = 1
time = 1
action = 1

total_facets = 4
```

---

# 4. Use Case 1: Match Bình Thường

## 4.1 Matching

Flow:

```text
Hồ Chí Minh
---> alias lookup
---> person_hcm

Pháp
---> alias lookup
---> place_france

1911
---> year/time lookup
---> time_1911

đến Pháp
---> action facet
---> không match trực tiếp vào graph node
```

Kết quả:

| Facet type | Facet value | Matched? | Node |
|---|---|---:|---|
| `person` | Hồ Chí Minh | Có | `person_hcm` |
| `place` | Pháp | Có | `place_france` |
| `time` | 1911 | Có | `time_1911` |
| `action` | đến Pháp | Không | Không match graph node |

Match rate:

```text
matched_facets = 3
total_facets = 4

match_rate = 3 / 4 = 0.75
```

Ý nghĩa:

```text
Graph hiểu được 3/4 phần của claim.
Action "đến Pháp" không match node, nhưng vẫn được giữ để LLM đọc.
```

---

# 5. Retrieve Chunks Từ Matched Nodes

Sau matching, hệ thống retrieve theo 2 hướng:

```text
node mentions
relation 1-hop
```

## 5.1 Node Mentions

Hỏi:

```text
matched node này được nhắc trong chunk nào?
```

Ví dụ:

```text
person_hcm
---> c1, c2, c3, c6

place_france
---> c1, c2, c4

time_1911
---> c1, c5
```

Các chunk này lấy từ bảng `MENTIONS` ở phần graph giả định. Ví dụ `c6` không nằm trong relation edge nào, nhưng nó có:

```text
c6 --MENTIONS--> person_hcm
```

nên khi facet `Hồ Chí Minh` match `person_hcm`, `c6` vẫn được lấy bằng đường `node_mention`.

## 5.2 Relation 1-Hop

Hỏi:

```text
matched node này có edge 1-hop nào?
edge đó có source_chunk nào?
```

Ví dụ:

```text
person_hcm
---> e1 source_chunk c1
---> e5 source_chunk c2
---> e7 source_chunk c3

place_france
---> e4 source_chunk c1
---> e6 source_chunk c2
---> e8 source_chunk c4

time_1911
---> e2 source_chunk c1
```

Retrieve ngược về chunk:

```text
node mention:
matched node
---> các chunk MENTIONS node đó
---> evidence candidate

relation 1-hop:
matched node
---> edge 1-hop
---> edge.source_chunk
---> evidence candidate
```

## 5.3 Gom Evidence Candidates

Các chunk lấy được:

```text
c1, c2, c3, c4, c5, c6
```

Nếu cùng một chunk xuất hiện từ nhiều đường khác nhau, hệ thống dedup theo `chunk_id`.

Ví dụ `c1` xuất hiện từ:

```text
person_hcm node mention
place_france node mention
time_1911 node mention
e1 relation_1hop
e2 relation_1hop
e4 relation_1hop
```

Nhưng vẫn chỉ có 1 evidence item:

```json
{
  "chunk_id": "c1",
  "facet_hits": [
    {"facet_type": "person", "facet_value": "Hồ Chí Minh"},
    {"facet_type": "place", "facet_value": "Pháp"},
    {"facet_type": "time", "facet_value": "1911"}
  ],
  "relation_hits": [
    {"edge_id": "e1", "type": "RELATED_TO"},
    {"edge_id": "e2", "type": "OCCURRED_AT"},
    {"edge_id": "e4", "type": "LOCATED_IN"}
  ],
  "text": "Năm 1911, Nguyễn Tất Thành ... đến Mác-xây, Pháp."
}
```

---

# 6. Use Case 2: Một Facet Match Quá Nhiều Nodes

Giả sử facet:

```text
place = Pháp
```

Match được 4 node:

```text
place_france
org_france_colonial
place_paris
place_marseille
```

Nhưng ngưỡng giả lập:

```yaml
max_matches_per_facet: 2
```

Vậy hệ thống chỉ giữ 2 node đầu sau khi sort alias candidates:

```text
Pháp
---> place_france
---> org_france_colonial
```

Các node bị cắt:

```text
place_paris
place_marseille
```

Ý nghĩa:

```text
Những chunk chỉ nối qua place_paris/place_marseille có thể không được lấy từ facet Pháp.
```

Tuy nhiên, nếu `place_marseille` xuất hiện qua relation 1-hop từ `event_departure_1911`, nó vẫn có thể được lấy gián tiếp qua edge:

```text
event_departure_1911 --LOCATED_IN--> place_marseille
source_chunk = c1
```

## 6.1 Vì Sao Phải Cắt?

Nếu không cắt:

```text
1 facet mơ hồ
---> match quá nhiều nodes
---> lấy quá nhiều chunks
---> context nhiễu
---> verifier khó quyết định
```

Cắt giúp retrieval giữ được kích thước hợp lý.

---

# 7. Use Case 3: Một Node Có Nhiều Relations

Giả sử node:

```text
person_hcm
```

có 7 relations:

```text
e1, e5, e7, e9, e10, e11, e12
```

và các relations này trỏ về 10 chunks khác nhau.

Ngưỡng:

```yaml
max_chunks_per_facet: 5
```

Logic:

```text
facet person = Hồ Chí Minh
---> match person_hcm
---> lấy chunks node mention trước
---> lấy source_chunk từ relation 1-hop sau
---> cứ thêm chunk cho tới khi facet này đạt 5 unique chunks
---> dừng
```

Ví dụ:

```text
person_hcm node mentions: c1, c2, c3, c6
relation chunks: c1, c2, c3, c7, c8, c9, c10
```

Hệ thống có thể lấy:

```text
c1, c2, c3, c6, c7
```

rồi dừng vì đã đủ 5 chunks cho facet `person`.

Các chunk còn lại:

```text
c8, c9, c10
```

không lấy ở facet này.

## 7.1 Nếu Relation Không Có Source Chunk?

Nếu edge:

```json
{
  "edge_id": "e99",
  "type": "RELATED_TO",
  "source": "person_hcm",
  "target": "place_france",
  "source_chunk": null
}
```

thì hệ thống không lấy được chunk từ relation này.

```text
edge không có source_chunk
---> không tạo evidence candidate
```

---

# 8. Use Case 4: Quá Nhiều Candidate Chunks

Giả sử toàn claim retrieve ra:

```text
candidate_chunks = 25
```

Ngưỡng:

```yaml
max_chunks_per_claim: 12
```

Hệ thống pre-filter:

```text
25 chunks
---> sort thô
---> lấy 12 chunks đầu
```

Sort thô:

```text
1. Chunk hit nhiều facet khác nhau hơn đứng trước
2. Nếu bằng nhau, chunk có nhiều relation_hits hơn đứng trước
3. Nếu vẫn bằng nhau, chunk_id nhỏ hơn đứng trước
```

Ví dụ:

| Chunk | Unique facet hits | Relation hits | Thứ tự |
|---|---:|---:|---:|
| `c1` | 3 | 3 | 1 |
| `c2` | 2 | 2 | 2 |
| `c4` | 1 | 2 | 3 |
| `c5` | 1 | 0 | 4 |

Sau pre-filter:

```text
selected_chunks = 12
```

Rồi mới rerank chi tiết.

---

# 9. Rerank Chunks

Sau pre-filter, mỗi chunk được chấm điểm:

```text
final_score =
  0.55 * facet_coverage
+ 0.35 * relation_score
+ 0.10 * text_overlap
```

## 9.1 Facet Coverage

```text
facet_coverage =
  số facet value khác nhau mà chunk hit được
  /
  total_facets
```

Claim có:

```text
total_facets = 4
```

Chunk `c1` hit:

```text
person = Hồ Chí Minh
place = Pháp
time = 1911
```

Nên:

```text
facet_coverage = 3 / 4 = 0.75
```

Chunk `c2` hit:

```text
person = Hồ Chí Minh
place = Pháp
```

Nên:

```text
facet_coverage = 2 / 4 = 0.5
```

## 9.2 Relation Score

Công thức:

```text
relation_score =
  min(1, log(1 + relation_hits_count) / log(4))
```

Nếu chunk `c1` có 3 relation hits:

```text
relation_score = log(4) / log(4) = 1.0
```

Nếu chunk `c2` có 2 relation hits:

```text
relation_score = log(3) / log(4)
               = 0.792481250360578
```

Nếu chunk `c5` có 0 relation hits:

```text
relation_score = 0
```

## 9.3 Text Overlap

Công thức:

```text
text_overlap =
  số token claim xuất hiện trong chunk
  /
  số token claim
```

Claim:

```text
Hồ Chí Minh đến Pháp năm 1911
```

Token claim sau khi lowercase/split và giữ token dài >= 3:

```text
hồ, chí, minh, đến, pháp, năm, 1911
```

Chunk `c1`:

```text
Năm 1911, Nguyễn Tất Thành ... đến Mác-xây, Pháp.
```

Giả sử overlap với claim:

```text
đến, pháp, năm, 1911
```

```text
text_overlap = 4 / 7 = 0.5714
```

Lưu ý: nếu chunk dùng alias `Nguyễn Tất Thành` thay vì `Hồ Chí Minh`, lexical overlap không tự hiểu là cùng người. Phần đó được bù bởi graph facet match.

## 9.4 Tính Final Score Cho Các Chunk

### Chunk `c1`

```text
facet_coverage = 0.75
relation_score = 1.0
text_overlap = 0.5714
```

```text
final_score =
  0.55 * 0.75
+ 0.35 * 1.0
+ 0.10 * 0.5714

= 0.4125
+ 0.35
+ 0.05714

= 0.81964
```

### Chunk `c2`

```text
facet_coverage = 0.5
relation_score = 0.7925
text_overlap = 0.2857
```

```text
final_score =
  0.55 * 0.5
+ 0.35 * 0.7925
+ 0.10 * 0.2857

= 0.275
+ 0.2774
+ 0.0286

= 0.5810
```

### Chunk `c5`

```text
facet_coverage = 0.25
relation_score = 0
text_overlap = 0.2857
```

```text
final_score =
  0.55 * 0.25
+ 0.35 * 0
+ 0.10 * 0.2857

= 0.1375
+ 0
+ 0.0286

= 0.1661
```

## 9.5 Kết Quả Rerank

| Rank | Chunk | Facet coverage | Relation score | Text overlap | Final |
|---:|---|---:|---:|---:|---:|
| 1 | `c1` | 0.75 | 1.00 | 0.5714 | 0.8196 |
| 2 | `c2` | 0.50 | 0.7925 | 0.2857 | 0.5810 |
| 3 | `c5` | 0.25 | 0.00 | 0.2857 | 0.1661 |

Sau rerank:

```text
sort giảm theo final_score
---> lấy top_k = 8 graph chunks
```

Nếu chỉ có 3 chunks thì giữ cả 3.

---

# 10. Use Case 5: Nếu Mọi Điểm Bằng Nhau

Nếu nhiều chunks có cùng:

```text
facet_coverage
relation_score
text_overlap
final_score
```

thì hệ thống dùng:

```text
chunk_id tăng dần
```

Ví dụ:

| Chunk | Final |
|---|---:|
| `c10` | 0.5 |
| `c02` | 0.5 |
| `c07` | 0.5 |

Thứ tự:

```text
c02
c07
c10
```

Mục tiêu là deterministic: chạy lại nhiều lần vẫn cùng kết quả.

---

# 11. Use Case 6: Facet Không Match

Facet:

```text
action = đến Pháp
```

Không match graph node.

Logic:

```text
action facet
---> không có node
---> không retrieve graph chunks trực tiếp
---> vẫn đưa action vào verifier trong phần claim facets
```

Ảnh hưởng:

```text
total_facets = 4
matched_facets = 3
missing_facets = 1
```

Verifier sẽ thấy:

```json
{
  "total_facets": 4,
  "matched_facets": 3,
  "missing_facets": 1
}
```

Nó biết graph evidence có thể thiếu phần hành động.

---

# 12. Fuse Text + Graph

Sau graph rerank:

```text
top graph chunks = c1, c2, c5, ...
```

Text retrieval cũng chạy riêng:

```text
claim
---> BM25 + Dense text retrieval
---> top text chunks
```

Fusion:

```text
top 3 text chunks
+ top 3 graph chunks
---> dedup
---> tối đa 6 evidence
---> đưa LLM
```

Ví dụ evidence đưa cho LLM:

| Evidence ID | Source | Chunk | Nội dung |
|---|---|---|---|
| `E1` | text | `text_1` | Đoạn SGK nhắc Nguyễn Tất Thành rời Việt Nam năm 1911. |
| `E2` | text | `text_2` | Đoạn SGK nhắc hoạt động của Nguyễn Ái Quốc ở Pháp. |
| `E3` | text | `text_3` | Đoạn SGK nhắc bối cảnh năm 1911. |
| `E4` | graph | `c1` | Năm 1911, Nguyễn Tất Thành đến Mác-xây, Pháp. |
| `E5` | graph | `c2` | Nguyễn Ái Quốc hoạt động ở Pháp. |
| `E6` | graph | `c5` | Năm 1911 trong bối cảnh khác. |

---

# 13. LLM Verifier Nhận Gì?

Verifier nhận:

```text
Claim:
Hồ Chí Minh đến Pháp năm 1911.

Claim facets:
person = Hồ Chí Minh
place = Pháp
time = 1911
action = đến Pháp

Facet summary:
total_facets = 4
matched_facets = 3
missing_facets = 1

Evidence:
E1...E6
```

Verifier trả:

```json
{
  "label": "real",
  "confidence": 0.86,
  "evidence_ids": ["E1", "E4"],
  "wrong_facets": [],
  "reasoning": "Evidence E1/E4 cho thấy năm 1911 Nguyễn Tất Thành đến Mác-xây, Pháp."
}
```

Nếu evidence nói khác, ví dụ:

```text
Hồ Chí Minh đến Pháp năm 1917
```

thì verifier có thể trả:

```json
{
  "label": "fake",
  "confidence": 0.84,
  "evidence_ids": ["E2"],
  "wrong_facets": ["time"],
  "reasoning": "Evidence cho thấy mốc đến/hoạt động ở Pháp là 1917, không phải 1911."
}
```

---

# 14. Tóm Tắt Ngắn Gọn Cho Giảng Viên

```text
Claim
---> tách facet
---> facet match vào graph nodes
---> nếu 1 facet quá nhiều nodes: giữ tối đa N nodes
---> từ nodes lấy chunks bằng node mentions và relation 1-hop
---> nếu 1 node quá nhiều relations/chunks: giữ tối đa K chunks/facet
---> gom chunks, dedup, pre-filter tối đa 12 chunks/claim
---> rerank bằng facet_coverage + relation_score + text_overlap
---> lấy top graph chunks
---> fuse top graph chunks với top text chunks
---> LLM verifier dự đoán real/fake
```

Điểm quan trọng:

| Thành phần | Tác dụng |
|---|---|
| `match_rate` | Claim match graph tốt không. |
| `facet_coverage` | Một chunk cover được bao nhiêu facet của claim. |
| `relation_hits` | Chunk được hỗ trợ bởi bao nhiêu graph edges. |
| `text_overlap` | Chunk có trùng từ khóa với claim không. |
| `final_score` | Điểm chọn evidence trước khi đưa LLM. |
| `LLM verifier` | Bước cuối quyết định real/fake. |
