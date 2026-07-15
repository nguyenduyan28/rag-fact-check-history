# Ví Dụ Facet Matching Và Evidence Retrieval

Claim ví dụ:

```text
Năm 1945, Hồ Chí Minh đọc Tuyên ngôn Độc lập tại Ba Đình.
```

Mục tiêu của file này là mô phỏng cách pipeline facet hoạt động với một claim cụ thể: tách facet ra sao, match vào graph thế nào, lấy evidence từ node/edge/chunk thế nào, và rerank evidence ra sao.

## 1. Claim Được Tách Thành Facet

Sau bước facet extraction, claim có thể được tách như sau:

```json
{
  "time": ["1945"],
  "person": ["Hồ Chí Minh"],
  "event": ["Tuyên ngôn Độc lập"],
  "place": ["Ba Đình"],
  "action": ["đọc Tuyên ngôn Độc lập"],
  "result": []
}
```

Ý nghĩa:

| Facet | Giá trị | Dùng để kiểm gì |
|---|---|---|
| `time` | `1945` | Claim có đúng mốc năm không. |
| `person` | `Hồ Chí Minh` | Claim có đúng nhân vật không. |
| `event` | `Tuyên ngôn Độc lập` | Claim có đúng sự kiện/văn kiện không. |
| `place` | `Ba Đình` | Claim có đúng địa điểm không. |
| `action` | `đọc Tuyên ngôn Độc lập` | Claim có đúng hành động không. |

Lưu ý: `action` và `result` hiện thường không match trực tiếp vào graph node. Chúng vẫn được đưa cho verifier để hiểu claim, nhưng bước graph matching chủ yếu match các facet như `person`, `organization`, `event`, `place`, `time`, `concept`.

## 2. Giả Sử Graph Có Các Nodes

Giả sử graph đã build từ SGK có các node sau:

| Node ID | Type | Name | Aliases |
|---|---|---|---|
| `person_hochiminh` | `Person` | Hồ Chí Minh | Hồ Chí Minh, Chủ tịch Hồ Chí Minh, Nguyễn Ái Quốc |
| `event_tuyenngon_doclap` | `Event` | Tuyên ngôn Độc lập | Tuyên ngôn Độc lập, bản Tuyên ngôn Độc lập |
| `place_badinh_square` | `Place` | Quảng trường Ba Đình | Ba Đình, Quảng trường Ba Đình |
| `place_badinh_district` | `Place` | Ba Đình | Ba Đình, quận Ba Đình |
| `time_1945` | `Time` | 1945 | 1945 |
| `event_cachmang_thangtam` | `Event` | Cách mạng tháng Tám | Cách mạng tháng Tám, Tổng khởi nghĩa tháng Tám |
| `org_vndcch` | `Organization` | Việt Nam Dân chủ Cộng hòa | Việt Nam Dân chủ Cộng hòa |

Ở đây cố ý có 2 node cùng liên quan đến `Ba Đình`:

```text
place_badinh_square = Quảng trường Ba Đình
place_badinh_district = Ba Đình/quận Ba Đình
```

Đây là trường hợp một facet match được nhiều node.

## 3. Giả Sử Graph Có Các Edges

Graph cũng có các relation:

| Edge ID | Source | Relation | Target | source_chunk |
|---|---|---|---|---|
| `e1` | `person_hochiminh` | `PARTICIPATED_IN` | `event_tuyenngon_doclap` | `lichsu_12_s40_001` |
| `e2` | `event_tuyenngon_doclap` | `OCCURRED_AT` | `place_badinh_square` | `lichsu_12_s40_001` |
| `e3` | `event_tuyenngon_doclap` | `OCCURRED_AT` | `time_1945` | `lichsu_12_s40_001` |
| `e4` | `event_cachmang_thangtam` | `BEFORE` | `event_tuyenngon_doclap` | `lichsu_12_s39_002` |
| `e5` | `event_tuyenngon_doclap` | `RESULTS_IN` | `org_vndcch` | `lichsu_12_s40_002` |
| `e6` | `place_badinh_district` | `RELATED_TO` | `place_badinh_square` | `lichsu_12_s80_001` |

Ý nghĩa:

```text
Hồ Chí Minh --PARTICIPATED_IN--> Tuyên ngôn Độc lập
Tuyên ngôn Độc lập --OCCURRED_AT--> Quảng trường Ba Đình
Tuyên ngôn Độc lập --OCCURRED_AT--> 1945
Tuyên ngôn Độc lập --RESULTS_IN--> Việt Nam Dân chủ Cộng hòa
```

## 4. Giả Sử Có Các Chunks

Các chunk trong corpus:

| Chunk ID | Text tóm tắt |
|---|---|
| `lichsu_12_s40_001` | Ngày 2-9-1945, tại Quảng trường Ba Đình, Chủ tịch Hồ Chí Minh đọc Tuyên ngôn Độc lập. |
| `lichsu_12_s40_002` | Bản Tuyên ngôn Độc lập khai sinh nước Việt Nam Dân chủ Cộng hòa. |
| `lichsu_12_s39_002` | Sau thắng lợi của Cách mạng tháng Tám năm 1945, nước Việt Nam bước vào kỷ nguyên mới. |
| `lichsu_12_s80_001` | Ba Đình là một địa danh ở Hà Nội, gắn với nhiều sự kiện lịch sử. |
| `lichsu_10_s10_001` | Một đoạn khác có nhắc năm 1945 nhưng không liên quan trực tiếp đến Tuyên ngôn Độc lập. |

Mỗi node trong graph biết nó từng xuất hiện ở chunk nào. Ví dụ:

```json
{
  "person_hochiminh": ["lichsu_12_s40_001"],
  "event_tuyenngon_doclap": ["lichsu_12_s40_001", "lichsu_12_s40_002"],
  "place_badinh_square": ["lichsu_12_s40_001"],
  "place_badinh_district": ["lichsu_12_s80_001"],
  "time_1945": ["lichsu_12_s40_001", "lichsu_12_s39_002", "lichsu_10_s10_001"]
}
```

## 5. Matching Facet Vào Graph

Pipeline lấy từng facet value đi match.

### 5.1 Match `time = 1945`

Vì facet type là `time`, pipeline dùng `year_index`.

Input:

```text
1945
```

Match:

```json
{
  "facet_type": "time",
  "facet_value": "1945",
  "matched": true,
  "matches": [
    {
      "node_id": "time_1945",
      "node_name": "1945",
      "node_type": "Time",
      "match_method": "year_index"
    }
  ]
}
```

### 5.2 Match `person = Hồ Chí Minh`

Pipeline normalize text:

```text
Hồ Chí Minh -> ho chi minh
```

Sau đó so với alias trong `entity_aliases.json`.

Match:

```json
{
  "facet_type": "person",
  "facet_value": "Hồ Chí Minh",
  "matched": true,
  "matches": [
    {
      "node_id": "person_hochiminh",
      "node_name": "Hồ Chí Minh",
      "node_type": "Person",
      "matched_alias": "Hồ Chí Minh",
      "match_method": "alias_exact"
    }
  ]
}
```

### 5.3 Match `event = Tuyên ngôn Độc lập`

Match:

```json
{
  "facet_type": "event",
  "facet_value": "Tuyên ngôn Độc lập",
  "matched": true,
  "matches": [
    {
      "node_id": "event_tuyenngon_doclap",
      "node_name": "Tuyên ngôn Độc lập",
      "node_type": "Event",
      "matched_alias": "Tuyên ngôn Độc lập",
      "match_method": "alias_exact"
    }
  ]
}
```

### 5.4 Match `place = Ba Đình`

Facet này có thể match nhiều node:

```json
{
  "facet_type": "place",
  "facet_value": "Ba Đình",
  "matched": true,
  "matches": [
    {
      "node_id": "place_badinh_square",
      "node_name": "Quảng trường Ba Đình",
      "node_type": "Place",
      "matched_alias": "Ba Đình",
      "match_method": "alias_exact"
    },
    {
      "node_id": "place_badinh_district",
      "node_name": "Ba Đình",
      "node_type": "Place",
      "matched_alias": "Ba Đình",
      "match_method": "alias_exact"
    }
  ]
}
```

Trong code hiện tại, mỗi facet value lấy tối đa:

```yaml
matching:
  max_matches_per_facet: 5
```

Nên nếu `Ba Đình` match nhiều node, pipeline giữ tối đa 5 match đầu tiên sau khi đã sort/dedup alias candidates.

### 5.5 `action = đọc Tuyên ngôn Độc lập`

Vì `action` không nằm trong graph type map, pipeline hiện không match alias cho `action`.

Kết quả có thể là:

```json
{
  "facet_type": "action",
  "facet_value": "đọc Tuyên ngôn Độc lập",
  "matched": false,
  "matches": []
}
```

Action vẫn hữu ích ở verifier stage vì nó nói claim đang yêu cầu kiểm chứng hành động gì.

## 6. Nếu Một Facet Match Nhiều Nodes Thì Sao?

Ví dụ `Ba Đình` match 2 node:

```text
place_badinh_square
place_badinh_district
```

Pipeline không chọn ngay node đúng duy nhất. Nó sẽ lấy evidence từ cả hai node, nhưng có giới hạn:

```yaml
evidence:
  max_chunks_per_facet: 5
```

Nghĩa là với facet `Ba Đình`, dù match nhiều node và mỗi node có nhiều chunk/edge, pipeline chỉ lấy tối đa 5 chunks liên quan cho facet này.

Cách lấy theo code hiện tại:

1. Với từng matched node, lấy các chunks mà node đó xuất hiện trực tiếp.
2. Lấy các edge 1-hop của node đó nếu relation nằm trong whitelist.
3. Lấy `source_chunk` của edge đó làm evidence.
4. Khi đủ `max_chunks_per_facet`, dừng.

## 7. Nếu Node Có Nhiều Edges Thì Sao?

Ví dụ node `event_tuyenngon_doclap` có nhiều edge:

```text
PARTICIPATED_IN với Hồ Chí Minh
OCCURRED_AT với Quảng trường Ba Đình
OCCURRED_AT với 1945
RESULTS_IN với Việt Nam Dân chủ Cộng hòa
BEFORE/AFTER với sự kiện khác
```

Pipeline chỉ lấy edge nếu relation thuộc danh sách:

```yaml
include_neighbor_relations:
  - PARTICIPATED_IN
  - OCCURRED_AT
  - LOCATED_IN
  - RELATED_TO
  - CAUSES
  - RESULTS_IN
  - BEFORE
  - AFTER
```

Với mỗi edge hợp lệ, pipeline lấy `source_chunk` của edge.

Ví dụ:

```json
{
  "edge_id": "e2",
  "type": "OCCURRED_AT",
  "source": "event_tuyenngon_doclap",
  "target": "place_badinh_square",
  "source_chunk": "lichsu_12_s40_001"
}
```

Thì chunk `lichsu_12_s40_001` được thêm vào evidence với reason:

```text
relation_1hop
```

## 8. Evidence Candidates Sau Retrieval

Sau matching và graph retrieval, claim có thể có candidate evidence như sau:

| Chunk | Vì sao được lấy |
|---|---|
| `lichsu_12_s40_001` | Match `Hồ Chí Minh`, `Tuyên ngôn Độc lập`, `Ba Đình`, `1945`; có relation 1-hop. |
| `lichsu_12_s40_002` | Match `Tuyên ngôn Độc lập`; có relation `RESULTS_IN`. |
| `lichsu_12_s39_002` | Match `1945`; có relation với Cách mạng tháng Tám. |
| `lichsu_12_s80_001` | Match node `Ba Đình` nhưng là địa danh chung. |
| `lichsu_10_s10_001` | Có năm `1945` nhưng không liên quan trực tiếp. |

Trong JSON evidence, mỗi chunk có thể ghi:

```json
{
  "chunk_id": "lichsu_12_s40_001",
  "facet_hits": [
    {"facet_type": "person", "facet_value": "Hồ Chí Minh", "reason": "node_mention"},
    {"facet_type": "event", "facet_value": "Tuyên ngôn Độc lập", "reason": "node_mention"},
    {"facet_type": "place", "facet_value": "Ba Đình", "reason": "relation_1hop"},
    {"facet_type": "time", "facet_value": "1945", "reason": "node_mention"}
  ],
  "relation_hits": [
    {"type": "PARTICIPATED_IN"},
    {"type": "OCCURRED_AT"}
  ],
  "text": "Ngày 2-9-1945, tại Quảng trường Ba Đình, Chủ tịch Hồ Chí Minh đọc Tuyên ngôn Độc lập..."
}
```

## 9. Rerank Evidence

Pipeline chưa đưa tất cả evidence cho verifier ngay. Nó chấm điểm từng chunk rồi sort.

Công thức hiện tại:

```text
final =
  0.55 * facet_coverage
+ 0.35 * relation_score
+ 0.10 * text_overlap
```

### 9.1 Chunk Rất Tốt

Chunk:

```text
Ngày 2-9-1945, tại Quảng trường Ba Đình, Chủ tịch Hồ Chí Minh đọc Tuyên ngôn Độc lập...
```

Điểm giả lập:

| Score | Giá trị | Vì sao |
|---|---:|---|
| `facet_coverage` | 0.80 | Cover `time`, `person`, `event`, `place`; action nằm trong text nhưng không match graph. |
| `relation_score` | 0.79 | Có nhiều relation hits như `PARTICIPATED_IN`, `OCCURRED_AT`. |
| `text_overlap` | 0.85 | Trùng nhiều từ với claim. |
| `final` | 0.80 | Rất nên đưa lên top. |

### 9.2 Chunk Trung Bình

Chunk:

```text
Bản Tuyên ngôn Độc lập khai sinh nước Việt Nam Dân chủ Cộng hòa.
```

Điểm giả lập:

| Score | Giá trị | Vì sao |
|---|---:|---|
| `facet_coverage` | 0.20 | Chỉ cover event. |
| `relation_score` | 0.50 | Có relation `RESULTS_IN`. |
| `text_overlap` | 0.45 | Có trùng `Tuyên ngôn Độc lập`. |
| `final` | 0.33 | Có ích nhưng không bằng chunk đầu. |

### 9.3 Chunk Nhiễu

Chunk:

```text
Ba Đình là một địa danh ở Hà Nội, gắn với nhiều sự kiện lịch sử.
```

Điểm giả lập:

| Score | Giá trị | Vì sao |
|---|---:|---|
| `facet_coverage` | 0.20 | Chỉ cover place. |
| `relation_score` | 0.00 | Không có relation quan trọng với claim. |
| `text_overlap` | 0.15 | Trùng ít từ. |
| `final` | 0.125 | Dễ bị đẩy xuống dưới. |

## 10. Kết Quả Sau Rerank

Sau rerank, thứ tự evidence có thể là:

| Rank | Chunk | Lý do |
|---:|---|---|
| 1 | `lichsu_12_s40_001` | Cover gần đủ facet, có thời gian, nhân vật, sự kiện, địa điểm. |
| 2 | `lichsu_12_s40_002` | Bổ sung kết quả của Tuyên ngôn Độc lập. |
| 3 | `lichsu_12_s39_002` | Bối cảnh năm 1945 và Cách mạng tháng Tám. |
| 4 | `lichsu_12_s80_001` | Chỉ liên quan địa danh Ba Đình, ít trọng tâm. |
| 5 | `lichsu_10_s10_001` | Có năm 1945 nhưng lệch chủ đề. |

Verifier sẽ nhận top evidence, ví dụ:

```text
E1 = lichsu_12_s40_001
E2 = lichsu_12_s40_002
E3 = lichsu_12_s39_002
```

Với evidence như vậy, verifier có thể dự đoán:

```json
{
  "label": "real",
  "confidence": 0.93,
  "evidence_ids": ["E1"],
  "wrong_facets": [],
  "reasoning": "E1 nêu rõ năm 1945, Hồ Chí Minh đọc Tuyên ngôn Độc lập tại Quảng trường Ba Đình."
}
```

## 11. Tóm Tắt Cách Hoạt Động

Toàn bộ flow với claim ví dụ:

```text
Claim:
Năm 1945, Hồ Chí Minh đọc Tuyên ngôn Độc lập tại Ba Đình.

1. Extract facet:
time=1945, person=Hồ Chí Minh, event=Tuyên ngôn Độc lập, place=Ba Đình

2. Match graph:
1945 -> time_1945
Hồ Chí Minh -> person_hochiminh
Tuyên ngôn Độc lập -> event_tuyenngon_doclap
Ba Đình -> place_badinh_square + place_badinh_district

3. Retrieve evidence:
lấy chunks nơi node xuất hiện
lấy chunks từ edge 1-hop

4. Rerank:
chunk nào cover nhiều facet hơn, có relation tốt hơn, đúng năm hơn, overlap claim hơn thì lên top

5. Verify:
Gemini/GPT đọc top evidence và quyết định real/fake
```

Điểm quan trọng:

```text
Matching không quyết định real/fake.
Retrieval không quyết định real/fake.
Rerank không quyết định real/fake.
Verifier mới là bước quyết định label cuối cùng.
```

---

# Ví Dụ Thực Tế Từ Dataset

Claim thật trong dataset:

```text
Thực dân Pháp đã triển khai chương trình khai thác thuộc địa lần thứ hai tại Đông Dương, chủ yếu tập trung ở Campuchia, bắt đầu vào năm 1910 và kéo dài cho tới 1955.
```

Metadata:

| Field | Giá trị |
|---|---|
| `ID` | `1_fake` |
| `row_index` | `0` |
| Gold label | `fake` |

Claim này là fake vì có các chi tiết sai quan trọng:

| Phần claim | Vấn đề |
|---|---|
| `chủ yếu tập trung ở Campuchia` | Evidence SGK cho thấy trọng tâm liên quan đến Việt Nam/Đông Dương, không phải chủ yếu Campuchia. |
| `bắt đầu vào năm 1910` | Khai thác thuộc địa lần thứ hai gắn với sau Chiến tranh thế giới thứ nhất, khoảng từ 1919. |
| `kéo dài cho tới 1955` | Mốc 1955 không phải thời điểm kết thúc chương trình khai thác thuộc địa lần thứ hai. |

## A. Facet Extraction Thực Tế

Output trong `data/outputs/facet/claim_facets.json`:

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

Tổng số facet value:

```text
organization: 1
event: 1
place: 2
time: 2
concept: 1
=> total_facets = 7
```

## B. Matching Vào Graph Thực Tế

Output summary trong `facet_matches.json`:

```json
{
  "total_facets": 7,
  "matched_facets": 5,
  "match_rate": 0.7142857142857143
}
```

Công thức:

```text
match_rate = matched_facets / total_facets
           = 5 / 7
           = 0.7142857142857143
```

Chi tiết từng facet:

| Facet type | Facet value | Matched? | Match vào node |
|---|---|---:|---|
| `organization` | `thực dân Pháp` | Có | `ent_001226` = `Pháp` |
| `event` | `chương trình khai thác thuộc địa lần thứ hai` | Không | Không có node event match trực tiếp |
| `place` | `Đông Dương` | Có | `ent_001298` = `Đông Dương` |
| `place` | `Campuchia` | Có | `ent_000560` = `Campuchia` |
| `time` | `1910` | Không | Không có time node/chunk match trong year index |
| `time` | `1955` | Có | Match 5 time nodes chứa năm 1955 |
| `concept` | `khai thác thuộc địa` | Có | `ent_001684` = `khai thác thuộc địa` |

Ví dụ match `time = 1955`:

```json
[
  {"node_id": "ent_000001", "node_name": "1 - 1 - 1955", "node_type": "Time"},
  {"node_id": "ent_000031", "node_name": "14-5-1955", "node_type": "Time"},
  {"node_id": "ent_000041", "node_name": "16 - 5 - 1955", "node_type": "Time"},
  {"node_id": "ent_000143", "node_name": "1955", "node_type": "Time"},
  {"node_id": "ent_000144", "node_name": "1955 - 1993", "node_type": "Time"}
]
```

Ở đây `1955` match nhiều nodes. Pipeline giữ tối đa:

```yaml
matching:
  max_matches_per_facet: 5
```

Nên đúng 5 node time được giữ.

## C. Retrieval Evidence Thực Tế

Sau matching, pipeline lấy evidence từ:

```text
node mentions
relation 1-hop
```

Ý nghĩa 2 nguồn evidence:

| Nguồn | Nghĩa là gì | Ví dụ với claim này |
|---|---|---|
| `node mentions` | Lấy chunk nơi matched node xuất hiện trực tiếp trong corpus. Nếu facet `Campuchia` match node `ent_000560`, pipeline lấy các chunk từng nhắc node Campuchia. | `Campuchia` xuất hiện trong một chunk về Đông Dương/Lào/Campuchia, chunk đó được thêm vào evidence. |
| `relation 1-hop` | Từ matched node, đi qua các edge kề nó đúng 1 bước, rồi lấy `source_chunk` của edge đó. | Node `khai thác thuộc địa` có edge `RELATED_TO` với node `Pháp`, nên chunk nguồn của edge này được lấy. |

Nói ngắn gọn:

```text
node mentions  = node này được nhắc ở chunk nào?
relation 1-hop = node này nối với node nào, edge đó lấy từ chunk nào?
```

Output trong `facet_evidence.json`:

```json
{
  "candidate_chunks": 23,
  "selected_chunks": 12
}
```

Ý nghĩa:

| Metric | Ý nghĩa |
|---|---|
| `candidate_chunks = 23` | Graph retrieval tìm được 23 chunks có liên quan đến các matched facets/nodes. |
| `selected_chunks = 12` | Do config `max_chunks_per_claim = 12`, chỉ giữ 12 candidate chunks để rerank. |

Config:

```yaml
evidence:
  max_chunks_per_facet: 5
  max_chunks_per_claim: 12
```

Vì claim này có nhiều match rộng như `Pháp`, `Đông Dương`, `Campuchia`, `1955`, nên graph lấy được nhiều chunk, nhưng không phải chunk nào cũng thật sự đúng trọng tâm.

## D. Một Số Evidence Candidate Thật

### Candidate 1: `lichsu_12_s240_bai21_sec6_001`

Lý do được lấy:

```json
[
  {"facet_type": "place", "facet_value": "Campuchia", "reason": "node_mention"},
  {"facet_type": "time", "facet_value": "1955", "reason": "node_mention"},
  {"facet_type": "time", "facet_value": "1955", "reason": "relation_1hop"}
]
```

Relation hits:

```json
[
  {"type": "RELATED_TO", "source": "ent_000001", "target": "ent_001449"},
  {"type": "RELATED_TO", "source": "ent_001525", "target": "ent_000001"}
]
```

Text tóm tắt:

```text
... GIONEVƠ NĂM 1954 ... Hiệp định Giơnevơ năm 1954 ...
```

Chunk này không nói đúng trực tiếp về khai thác thuộc địa lần thứ hai. Nó được lấy vì có `Campuchia` và `1955`, nên là evidence liên quan nhưng khá nhiễu.

### Candidate 2: `lichsu_12_s124_bai12_sec7_001`

Lý do được lấy:

```json
[
  {"facet_type": "concept", "facet_value": "khai thác thuộc địa", "reason": "node_mention"},
  {"facet_type": "concept", "facet_value": "khai thác thuộc địa", "reason": "relation_1hop"}
]
```

Text tóm tắt:

```text
... toàn bộ nền kinh tế Đông Dương ...
Thực dân Pháp còn thi hành các biện pháp tăng thuế ...
năm 1930 tăng gấp ba lần so với năm 1912 ...
```

Chunk này liên quan hơn vì có `Đông Dương`, `thực dân Pháp`, `khai thác thuộc địa`, nhưng nó không trực tiếp cover toàn bộ claim sai về `Campuchia`, `1910`, `1955`.

### Candidate 3: `lichsu_11_s129_bai22_sec2_001`

Lý do được lấy:

```json
[
  {"facet_type": "place", "facet_value": "Đông Dương", "reason": "node_mention"}
]
```

Text tóm tắt:

```text
... LẦN THỨ NHẤT CỦA THỰC DÂN PHÁP ...
Sau khi đã cơ bản bình định được Việt Nam bằng quân sự,
thực dân Pháp bắt đầu ...
```

Chunk này có overlap text khá cao với claim, nhưng nói về lần thứ nhất, không phải lần thứ hai.

## E. Rerank Evidence: Công Thức Và Số Thật

Rerank dùng công thức:

```text
final_score =
  0.55 * facet_coverage
+ 0.35 * relation_score
+ 0.10 * text_overlap
```

Trong đó:

```text
facet_coverage = số facet khác nhau mà chunk hit được / total_facets
relation_score = min(1, log(1 + số relation_hits) / log(4))
text_overlap = số token claim xuất hiện trong evidence / số token claim
```

Claim này có:

```text
total_facets = 7
```

Ghi chú: các output JSON hiện tại có thể vẫn là kết quả theo công thức cũ nếu chưa rerun pipeline. Các số dưới đây là tính lại theo công thức mới từ các thành phần score đã có.

## F. Tính Score Cho Top 1 Graph Evidence

Top 1 graph evidence:

```text
chunk_id = lichsu_12_s240_bai21_sec6_001
```

Scores thật:

```json
{
  "final_new": 0.47322061590241347,
  "facet_coverage": 0.2857142857142857,
  "relation": 0.792481250360578,
  "text_overlap": 0.3870967741935484
}
```

### 1. Facet coverage

Chunk này hit 2 facet khác nhau:

```text
place = Campuchia
time = 1955
```

Tổng facet của claim là 7:

```text
facet_coverage = 2 / 7
               = 0.2857142857142857
```

### 2. Relation score

Chunk này có 2 relation hits:

```text
relation_hits = 2
```

Công thức:

```text
relation_score = log(1 + relation_hits) / log(4)
               = log(3) / log(4)
               = 0.792481250360578
```

### 3. Text overlap

Score thật:

```text
text_overlap = 0.3870967741935484
```

Nghĩa là khoảng 38.7% token quan trọng của claim cũng xuất hiện trong text evidence.

### 4. Final score

Thay vào công thức:

```text
final =
  0.55 * 0.2857142857142857
+ 0.35 * 0.792481250360578
+ 0.10 * 0.3870967741935484

= 0.15714285714285714
+ 0.2773680813402023
+ 0.03870967741935484

= 0.4732206159024143
```

Vì vậy chunk này vẫn có thể đứng rất cao trong graph evidence, dù nội dung chưa thật sự là evidence tốt nhất về khai thác thuộc địa lần thứ hai. Nó lên cao vì khớp `Campuchia`, `1955`, có relation, có overlap text.

## G. Top Graph Evidence Sau Rerank

Top evidence trong `facet_reranked.json`:

| Rank | Chunk | Final mới | Facet coverage | Relation | Text overlap | Nhận xét |
|---:|---|---:|---:|---:|---:|---|
| 1 | `lichsu_12_s240_bai21_sec6_001` | 0.4732 | 0.2857 | 0.7925 | 0.3871 | Match `Campuchia`, `1955`, nhưng hơi lệch chủ đề. |
| 2 | `lichsu_12_s124_bai12_sec7_001` | 0.3019 | 0.1429 | 0.5000 | 0.4839 | Có `khai thác thuộc địa`, `Đông Dương`, `Pháp`; về nội dung hữu ích hơn. |
| 3 | `lichsu_12_s44_bai4_sec3_002` | 0.2923 | 0.1429 | 0.5000 | 0.3871 | Liên quan Campuchia/Lào/1955, không đúng trọng tâm khai thác thuộc địa. |
| 4 | `lichsu_12_s29_bai2_sec10_001` | 0.2859 | 0.1429 | 0.5000 | 0.3226 | Có 1955 nhưng lệch sang SEV/Liên Xô. |
| 5 | `lichsu_12_s287_bai23_sec14_001` | 0.2826 | 0.1429 | 0.5000 | 0.2903 | Liên quan Đông Dương nhưng lệch sang 1975. |
| 6 | `lichsu_10_s159_001` | 0.2794 | 0.1429 | 0.5000 | 0.2581 | Có thực dân Pháp nhưng lệch giai đoạn. |
| 7 | `lichsu_11_s129_bai22_sec2_001` | 0.1399 | 0.1429 | 0.0000 | 0.6129 | Text overlap cao nhưng không có relation. |
| 8 | `lichsu_10_s180_001` | 0.1302 | 0.1429 | 0.0000 | 0.5161 | Có Pháp nhưng không đúng chủ đề. |

Điểm đáng chú ý: graph rerank mới ưu tiên mạnh hơn cho facet coverage và relation score. Vì không còn điểm thời gian riêng, chunk chỉ có năm đúng nhưng ít relation/facet sẽ bớt lợi thế hơn trước.

## H. Hybrid Fuse: Text Evidence Cứu Lại Graph Evidence

Sau graph rerank, pipeline fuse thêm text retrieval cũ.

Output trong `hybrid_facet_reranked.json`:

```json
{
  "text_candidates": 5,
  "graph_candidates": 8,
  "selected_text": 3,
  "selected_graph": 3,
  "selected_total": 6
}
```

Nghĩa là verifier nhận:

```text
E1-E3: top 3 text retrieval chunks
E4-E6: top 3 graph chunks
```

Top text evidence thực tế:

| Evidence | Source | Nội dung chính |
|---|---|---|
| E1 | `lichsu_12/lichsu_12.pdf_76.jpg.txt` | Chương Việt Nam từ năm 1919 đến năm 1930, nhắc tác động của cuộc khai thác thuộc địa lần thứ hai. |
| E2 | `lichsu_11/lichsu_11.pdf_137.jpg.txt` | Nói về khai thác thuộc địa lần thứ nhất của thực dân Pháp. |
| E3 | `lichsu_11/lichsu_11.pdf_87.jpg.txt` | Nói thực dân Pháp tăng cường khai thác thuộc địa ở Đông Dương, liên quan Lào và Campuchia. |

Top graph evidence nếu tính lại theo công thức mới:

| Evidence | Source | Nội dung chính |
|---|---|---|
| E4 | `lichsu_12_s240_bai21_sec6_001` | Campuchia/1955/Giơnevơ, lệch chủ đề chính. |
| E5 | `lichsu_12_s124_bai12_sec7_001` | Có `khai thác thuộc địa`, `Đông Dương`, `Pháp`; hữu ích hơn về chủ đề. |
| E6 | `lichsu_12_s44_bai4_sec3_002` | Lào/Campuchia/1955, lệch chủ đề chính. |

Với claim này, text retrieval hữu ích hơn graph retrieval vì E1 nói đúng giai đoạn 1919-1930 và cuộc khai thác thuộc địa lần thứ hai.

## I. Verifier Kết Luận Thực Tế

Với prompt mềm mới, Gemini output cho claim này:

```json
{
  "label": "fake",
  "confidence": 0.9,
  "evidence_ids": ["E1", "E3", "E4"],
  "wrong_facets": ["place", "time"],
  "reasoning": "Evidence E1 và E3 cho thấy chương trình khai thác thuộc địa lần thứ hai tập trung ở Việt Nam và các nước Đông Dương nói chung, không chỉ Campuchia. Evidence E1 cũng chỉ ra thời gian bắt đầu là sau Chiến tranh thế giới thứ nhất (1919), không phải 1910. Evidence E4 đề cập đến Hiệp định Giơnevơ năm 1954 chấm dứt chiến tranh xâm lược của Pháp ở Đông Dương, không phải chương trình khai thác kéo dài đến 1955."
}
```

Kết luận:

```text
Gold label = fake
Predicted label = fake
=> Correct
```

## J. Bài Học Từ Claim Này

Claim này cho thấy rõ vai trò của từng bước:

| Bước | Có ích gì | Hạn chế lộ ra |
|---|---|---|
| Facet extraction | Tách đúng các phần cần kiểm: Pháp, Đông Dương, Campuchia, 1910, 1955, khai thác thuộc địa. | Không tự biết claim đúng/sai. |
| Matching | Match được 5/7 facets vào graph. | Không match được event dài và năm 1910. |
| Graph retrieval | Tìm được nhiều chunk liên quan đến Campuchia/1955/Pháp/Đông Dương. | Vì claim fake có năm sai `1955`, graph kéo lên nhiều chunk lệch chủ đề nhưng có năm 1955. |
| Rerank | Chấm điểm rõ ràng, giải thích được vì sao chunk lên top. | Score cao chưa chắc evidence đúng trọng tâm lịch sử. |
| Text retrieval | Tìm được chunk rất đúng về giai đoạn 1919-1930 và khai thác thuộc địa lần thứ hai. | Text-only có thể thiếu structured signal. |
| Hybrid | Kết hợp text + graph giúp verifier có đủ evidence hơn. | Cần tránh graph evidence nhiễu làm loãng context. |

Với claim này, phần quyết định giúp model đoán đúng là text evidence E1/E3, còn graph evidence chủ yếu giúp chỉ ra mốc `1955` không phù hợp với claim.
