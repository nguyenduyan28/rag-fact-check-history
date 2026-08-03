## A. DỮ LIỆU

**A1. Dataset được tạo từ đâu? OCR bằng cái gì, xử lý nhiễu OCR ra sao?**
- Hai nguồn: (1) nội dung SGK Lịch sử 10–12 → sinh nhận định; (2) trắc nghiệm đề thi
  VNHSGE và VMLU → chuyển thể thành câu khẳng định hoàn chỉnh.
- Corpus bằng chứng: 3 cuốn SGK số hóa bằng OCR → 591 trang văn bản thô.
- Xử lý nhiễu OCR (591 → 571 trang, 540 chunk):
  - chuẩn hóa Unicode NFC + chuẩn hóa khoảng trắng;
  - loại 20 trang rác: mục lục/trang xuất bản (10), trang quá ngắn dưới 80 ký tự (10);
  - lọc 159 khối câu hỏi ôn tập/bài tập (không phải nội dung kiến thức);
  - phần nhiễu còn sót được thừa nhận là hạn chế (E3): ~10% bằng chứng vàng bị ảnh hưởng
    bởi chunking/OCR — xếp ưu tiên #1 hướng phát triển.

**A2. Chunk được tạo thế nào? Tại sao nguyên 3 cuốn sách mà chỉ có 540 chunk?**
- KHÔNG cắt theo độ dài cố định — chunk theo cấu trúc sách–bài–mục (section-aware,
  rule-based): nhận diện heading (54 bài, 135 mục đánh số, 441 heading in hoa...),
  mỗi mục là một đơn vị chunk, mục quá dài (131 mục) mới cắt tiếp, tối đa 2.200 ký tự,
  tối thiểu 120, có overlap 1 mục trước.
- 540 là hợp lý vì: 571 trang sạch → mỗi chunk trung bình gói ~1 mục (~1.800 ký tự);
  phân bổ: Lịch sử 10 → 152, Lịch sử 11 → 113, Lịch sử 12 → 275.

**A3. Quy trình tạo dataset là gì? (trả lời gộp, vẽ được thành 6 bước)**
- Bước 1 — Thu thập nguồn: nội dung SGK + câu hỏi trắc nghiệm VNHSGE/VMLU.
- Bước 2 — Sinh tri thức gốc (`key`) bằng `gpt-4o-mini` từ nội dung SGK.
- Bước 3 — Sinh nhận định từ key (cũng `gpt-4o-mini`):
  - claim `real`: giữ đúng key, diễn đạt lại thành câu khẳng định;
  - claim `fake`: bóp méo có kiểm soát một chi tiết — đổi năm/giai đoạn, thay nhân vật
    hoặc tổ chức, đổi địa điểm, đảo chiều hành động, sai số lượng/kết quả;
  - nhánh trắc nghiệm: đáp án đúng → claim `real`, phương án nhiễu → claim `fake`.
- Bước 4 — Sinh bằng chứng tham chiếu (`relevant`) bằng **NotebookLM**: nạp SGK làm
  nguồn, đưa claim vào để NotebookLM trích đoạn bằng chứng bám nguồn; các claim
  cùng `key` dùng chung một `relevant`.
- Bước 5 — Kiểm định chất lượng: ẨN nhãn gốc rồi đưa vào LLM voting theo đa số,
  kèm kiểm tra tay mẫu các ca xung đột (chi tiết ở A5).
- Bước 6 — Làm sạch: khử trùng lặp theo claim (141 dòng), loại 3 nhóm xung đột nhãn
  (cùng claim mà 2 nhãn khác nhau — drop cả nhóm) → 11.491 → 11.344 nhận định,
  2.051 key duy nhất.
- Nếu hỏi ngắn gọn "ai bảo đảm nhãn đúng": biểu quyết đa mô hình + rà tay ca bất đồng
  (A5); thừa nhận nhiễu nhãn còn lại là hạn chế (C5), audit thủ công là hướng phát triển.

**A4. Claim fake sinh bằng LLM — có sợ quá dễ, có "pattern" không?**
- Có, và tụi em ĐO được điều đó: LLM-only bắt fake nhóm sinh-từ-SGK tới 96% recall
  → fake tự động thiên về bóp méo lộ liễu.
- Đối trọng: 66% dữ liệu là claim chuyển thể đề thi — khó hơn hẳn, LLM-only chỉ còn 77%.
- Hạn chế này được khai báo thẳng trong phân tích lỗi.

**A5. Verify dữ liệu LLM tạo làm sao? LLM voting là gì, dùng model nào?**
- Vấn đề: claim do LLM sinh có thể sai nghĩa, mơ hồ, hoặc nhãn không khớp nội dung.
- Cơ chế biểu quyết (LLM voting) — điểm mấu chốt: nhãn gốc bị ẨN trước khi vote:
  - mỗi claim được `LLAMA, QWEN, GEMINI` đánh giá độc lập 3 lượt,
    không nhìn thấy nhãn gốc;
  - quyết theo đa số: `fake-fake-real → fake`, `real-real-fake → real`;
  - kiểm chứng chất lượng voting: lấy mẫu ~10% các ca xung đột (vote 2–1)
    rà tay → ~87% quyết định của đa số là đúng;
  - claim không cứu được (mơ hồ, sai cấu trúc) → loại bỏ.
- Lớp làm sạch cuối bằng luật (tất định, không LLM): dedup + xử lý xung đột nhãn —
  bằng chứng còn lưu trong `clean_dataset_report.json` (3 cặp claim trùng nhau nhưng
  ngược nhãn giữa 2 đề thi khác nhau → loại cả 2, minh bạch trong báo cáo).
- Thừa nhận trung thực (nếu bị truy): voting bằng LLM không thay được chuyên gia sử học;
  nhiễu nhãn còn lại là hạn chế đã khai báo, ước lượng trần dataset là hướng phát triển.

**A6. Dataset EDA thế nào? Mất cân bằng vậy thì đánh giá kiểu gì?**
- EDA chính:
  - 11.344 claim: `real` 3.514 (31%) / `fake` 7.830 (69%);
  - theo nguồn: 7.457 (66%) chuyển thể đề thi His/MET, 3.887 (34%) sinh từ SGK;
  - 2.051 key duy nhất; corpus 540 chunk, độ dài chunk trung vị ~1.800 ký tự;
  - độ khó lệch theo nguồn (đo được): nhóm SGK dễ hơn nhóm đề thi
    (hit-rate bằng chứng 86,6% vs 72,9%; LLM-only 85,3% vs 77,0%).
- Mất cân bằng 69/31 → 4 biện pháp đánh giá:
  - mức nền được nêu tường minh: đoán toàn bộ `fake` đã đạt 69% accuracy;
  - mọi kết quả full set báo kèm Macro-F1 + precision/recall TỪNG nhãn
    (kết quả chính: 81,46% accuracy, 79,36% Macro-F1, recall hai nhãn cân bằng 80–82%);
  - xây tập cân bằng 2.000 (1.000/1.000, nền 50%) để so sánh các kiến trúc công bằng;
  - so sánh cặp trên cùng claim ID + kiểm định McNemar thay vì so accuracy thô.

**A7. Tập cân bằng 2.000 chọn sao? Sao không ngẫu nhiên?**
- Chọn tất định: 1.000 real + 1.000 fake đầu tiên theo thứ tự dữ liệu, do ràng buộc
  chi phí bước phân rã khía cạnh.
- Đổi lại: cố định ID → mọi cấu hình so sánh cặp được trên cùng claim (McNemar).
- Thiên lệch thành phần được khai báo (§4.1.1) và định lượng (§4.6).
- Kết quả chính thức báo trên toàn bộ 11.344 câu nên không phụ thuộc tập này.

# Extra

**E-1. Kiểm định McNemar là gì?**
- Dùng khi nào: so sánh 2 cấu hình chấm trên CÙNG một tập claim (so sánh cặp),
  để trả lời "chênh lệch này là thật hay chỉ do may rủi".
- Cách hoạt động — chỉ nhìn các câu hai hệ BẤT ĐỒNG:
  - b = số câu hệ A đúng, hệ B sai;
  - c = số câu hệ B đúng, hệ A sai;
  - các câu cả hai cùng đúng/cùng sai bị bỏ qua (không phân biệt được hai hệ);
  - nếu hai hệ thực chất ngang nhau thì mỗi ca bất đồng như tung đồng xu 50/50
    → b và c phải xấp xỉ nhau; b lệch c càng nhiều càng khó tin là ngẫu nhiên.
- p-value = xác suất thấy chênh lệch ít nhất như quan sát nếu hai hệ thật sự ngang
  nhau; quy ước p < 0,05 → khác biệt CÓ ý nghĩa thống kê.
- Ví dụ của tụi em: Hybrid vs Hybrid+Facet trên tập 2.000 — graph cứu 54 câu,
  làm hỏng 75 câu → p = 0,078 > 0,05 → CHƯA đủ bằng chứng kết luận hai hệ khác nhau
  (nên tụi em nói "tương đương về accuracy", không nói "graph kém hơn").
- Vì sao không so accuracy thô: chênh 1,05 điểm trên 2.000 câu chỉ là 21 câu —
  McNemar cho biết 21 câu đó nằm trong biên độ ngẫu nhiên hay không.

**E-2. Các thang đo có ý nghĩa gì?**
- `Accuracy` — tỉ lệ đoán đúng trên toàn bộ. Dễ hiểu nhưng ĐÁNH LỪA khi lệch nhãn:
  dataset 69% fake nên hệ đoán tất cả là fake đã đạt 69%.
- `Precision (nhãn X)` — trong các câu hệ ĐOÁN là X, bao nhiêu % đúng thật.
  Precision `fake` thấp = hay quy oan claim đúng thành sai.
- `Recall (nhãn X)` — trong các câu THẬT là X, hệ bắt được bao nhiêu %.
  Recall `fake` thấp = lọt tin giả; recall `real` thấp = oan tin thật.
  Với bài toán giáo dục, hai lỗi này đều gây hại → cần recall hai nhãn CÂN BẰNG
  (kết quả chính: 80,1% / 82,1%).
- `F1 (nhãn X)` — trung bình điều hòa của precision và recall nhãn đó
  (cao chỉ khi cả hai cùng cao).
- `Macro-F1` — trung bình F1 của hai nhãn, mỗi nhãn nặng NGANG NHAU bất kể số lượng
  → nhãn thiểu số `real` (31%) không bị chìm. Đây là thang chính khi dữ liệu lệch:
  81,46% accuracy nghe cao nhưng Macro-F1 79,36% phản ánh trung thực hơn.
- `Hit-rate / gold-in-context` — % câu mà bằng chứng vàng thật sự nằm trong context
  đưa cho bộ kiểm chứng. Thang này đo RIÊNG chất lượng truy xuất, giúp tách
  "lỗi do không tìm thấy bằng chứng" khỏi "lỗi do suy luận sai" (cặp với oracle 99,8%).
- `Coverage` — % câu hệ trả về nhãn hợp lệ, không lỗi định dạng/API (99,97%).
- `p-value` — xem E-1; luôn đi kèm khi tụi em tuyên bố cấu hình nào hơn cấu hình nào.

## B. PHƯƠNG PHÁP

**B1. BM25 là model gì? Xử lý như thế nào?**
- BM25 không phải mô hình học sâu; đây là một hàm xếp hạng truy xuất từ khóa dạng
  `sparse retrieval`, phát triển từ hướng TF–IDF.
- Cách xử lý trong hệ thống:
  - chuẩn hóa và tách từ toàn bộ 540 chunk để tạo chỉ mục từ vựng;
  - tách từ claim làm truy vấn;
  - chấm điểm từng chunk dựa trên mức độ trùng từ với claim, trong đó từ hiếm có trọng
    số cao hơn từ phổ biến, đồng thời có hiệu chỉnh tần suất từ và độ dài chunk;
  - xếp hạng các chunk theo điểm BM25, lấy top-20 ứng viên; ở cấu hình BM25-only thì lấy
    top-5 làm bằng chứng cho verifier.
- Top-5 của BM25 được lấy như sau:
  - BM25 chấm điểm toàn bộ 540 chunk;
  - sắp xếp điểm BM25 từ cao xuống thấp;
  - giữ 20 chunk đứng đầu làm tập ứng viên;
  - nếu chạy BM25-only, lấy trực tiếp 5 chunk đầu tiên trong danh sách này, tức các chunk
    có hạng 1 đến 5; không có bước model khác chấm lại.
- Điểm mạnh: tìm tốt tên riêng, tổ chức, sự kiện và niên đại xuất hiện trực tiếp trong SGK.
- Điểm yếu: dễ bỏ sót khi claim diễn đạt lại bằng từ đồng nghĩa hoặc khác nhiều về mặt từ vựng.
- Vai trò: BM25 chỉ tìm và xếp hạng bằng chứng, không trực tiếp kết luận claim `real/fake`.
- Kiến trúc xử lý:
  - `540 chunks --> chuẩn hóa và tách từ --> tạo chỉ mục BM25`;
  - `Claim --> chuẩn hóa và tách từ --> tính điểm BM25 với từng chunk --> xếp hạng
    top-20 --> chọn top-5 --> đưa bằng chứng vào verifier --> real/fake + giải thích`.

**B2. BGE-M3 là model gì? Xử lý như thế nào?**
- BGE-M3 là mô hình embedding đa ngôn ngữ của BAAI; hệ thống sử dụng nó như một
  `dense bi-encoder` để truy xuất theo ngữ nghĩa.
- Tên M3 thể hiện ba khả năng của mô hình: đa ngôn ngữ, đa chức năng truy xuất và xử lý
  văn bản ở nhiều độ dài; trong thí nghiệm này chỉ sử dụng đầu ra dense embedding.
- Cách xử lý trong hệ thống:
  - mã hóa trước mỗi chunk thành một vector và chuẩn hóa độ dài vector;
  - mã hóa claim thành vector trong cùng không gian biểu diễn;
  - tính tích vô hướng giữa vector claim và các vector chunk; vì các vector đã chuẩn hóa,
    giá trị này tương đương cosine similarity;
  - xếp hạng theo độ tương đồng, lấy top-20 ứng viên; ở cấu hình dense-only thì lấy top-5.
- Top-5 của BGE-M3 được lấy như sau:
  - BGE-M3 tạo vector cho claim và toàn bộ 540 chunk;
  - tính cosine similarity giữa vector claim và từng vector chunk;
  - sắp xếp điểm tương đồng từ cao xuống thấp;
  - giữ 20 chunk đứng đầu làm tập ứng viên;
  - nếu chạy BGE-M3-only, lấy trực tiếp 5 chunk có hạng 1 đến 5; không có bước model
    khác chấm lại.
- Điểm mạnh: tìm được các đoạn có ý nghĩa tương tự dù không trùng hoàn toàn từ khóa,
  nên phù hợp với claim được diễn đạt lại từ SGK hoặc đề thi.
- Điểm yếu: có thể ưu tiên đoạn gần về chủ đề nhưng sai chi tiết nhỏ như nhân vật, năm
  hoặc con số.
- Vai trò: BGE-M3 chỉ mã hóa và truy xuất bằng chứng, không phải model phân loại
  `real/fake` và cũng không tự sinh câu trả lời.
- Kiến trúc xử lý:
  - `540 chunks --> BGE-M3 --> vector hóa --> chuẩn hóa vector --> kho vector`;
  - `Claim --> BGE-M3 --> vector claim --> tính cosine similarity với kho vector -->
    xếp hạng top-20 --> chọn top-5 --> đưa bằng chứng vào verifier --> real/fake + giải thích`.

**B3. Hybrid là gì? Xử lý như thế nào?**
- Hybrid không phải một model riêng; đây là chiến lược kết hợp hai kênh truy xuất:
  - BM25 tìm theo trùng khớp từ khóa;
  - BGE-M3 tìm theo tương đồng ngữ nghĩa.
- Cách xử lý trong hệ thống:
  - cùng một claim được đưa song song vào BM25 và BGE-M3;
  - mỗi kênh trả về top-20 chunk;
  - hợp nhất hai bảng xếp hạng bằng Reciprocal Rank Fusion, với
    `RRF(d) = Σ 1 / (60 + rank_i(d))`;
  - chunk đứng cao ở một hoặc cả hai danh sách sẽ nhận điểm RRF cao;
  - sắp xếp lại theo điểm RRF và chọn top-5 chunk văn bản làm bằng chứng.
- Ý nghĩa công thức RRF:
  - `d` là một chunk đang được xét;
  - `i` là từng bảng xếp hạng, ở đây gồm bảng BM25 và bảng BGE-M3;
  - `rank_i(d)` là vị trí của chunk `d` trong bảng `i`, bắt đầu từ hạng 1;
  - ký hiệu `Σ` nghĩa là cộng đóng góp của chunk từ cả hai bảng;
  - nếu chunk không nằm trong top-20 của một bảng thì bảng đó đóng góp 0 điểm;
  - số 60 là hằng số làm trơn, giúp hạn chế việc hạng 1 áp đảo quá mạnh các hạng phía sau.
- RRF hiện tại không gán trọng số riêng cho hai kênh:
  - BM25 và BGE-M3 có vai trò ngang nhau trong phép cộng;
  - công thức đang chạy là `1/(60 + rank_BM25) + 1/(60 + rank_BGE-M3)`;
  - không có hệ số kiểu `w_BM25` hoặc `w_BGE-M3` đứng trước từng thành phần.
- Ví dụ một chunk đứng hạng 2 trong BM25 và hạng 5 trong BGE-M3:
  - điểm từ BM25: `1 / (60 + 2) = 1/62`;
  - điểm từ BGE-M3: `1 / (60 + 5) = 1/65`;
  - điểm tổng: `RRF(d) = 1/62 + 1/65 ≈ 0,0315`.
- Nếu một chunk đứng hạng 1 trong BM25 nhưng không có trong top-20 BGE-M3 thì điểm chỉ là
  `1/61 ≈ 0,0164`. Vì vậy, một chunk được cả hai kênh xếp hạng tốt thường đứng cao hơn
  chunk chỉ được một kênh tìm thấy.
- Nếu BM25 và BGE-M3 trả về hai danh sách top-20 khác nhau:
  - hệ lấy hợp hai danh sách và khử trùng theo chunk ID, nên có tối đa 40 chunk duy nhất;
  - với chunk chỉ có trong BM25: điểm RRF bằng `1 / (60 + hạng BM25)` và phần đóng góp
    từ BGE-M3 bằng 0;
  - với chunk chỉ có trong BGE-M3: điểm RRF bằng `1 / (60 + hạng BGE-M3)` và phần đóng
    góp từ BM25 bằng 0;
  - với chunk xuất hiện ở cả hai danh sách: cộng hai phần điểm, nên thường được đẩy lên cao;
  - sau khi tính điểm cho toàn bộ tập hợp tối đa 40 chunk, hệ sắp xếp giảm dần theo điểm
    RRF và lấy 5 chunk đứng đầu.
- Ví dụ hai danh sách khác hoàn toàn:
  - chunk hạng 1 của BM25 có điểm `1/61`;
  - chunk hạng 1 của BGE-M3 cũng có điểm `1/61`;
  - chunk hạng 2 của mỗi kênh có điểm `1/62`, tiếp tục tương tự đến hạng 20;
  - do không có chunk nào được hai kênh đồng thuận, các chunk cùng thứ hạng ở hai kênh
    sẽ bằng điểm nhau; hệ vẫn xếp toàn bộ tập hợp theo điểm và lấy top-5.
- Số chunk thực tế được hợp nhất là `20 + 20 - số chunk trùng nhau`; vì vậy chỉ đạt đủ
  40 khi hai danh sách không có bất kỳ chunk nào giống nhau.
- Dùng thứ hạng thay vì cộng trực tiếp điểm BM25 và cosine vì hai loại điểm không cùng
  thang đo.
- Mục đích: tận dụng đồng thời độ chính xác từ vựng của BM25 và khả năng bắt paraphrase
  của BGE-M3, giảm điểm yếu khi chỉ dùng một kênh.
- Vai trò trong hệ cuối: Hybrid tạo bằng chứng văn bản nền, sau đó kết hợp với Facet để
  kiểm tra và giải thích claim theo từng khía cạnh.
- Kiến trúc xử lý:
  - `Claim --> BM25 --> top-20 theo từ khóa`;
  - `Claim --> BGE-M3 --> top-20 theo ngữ nghĩa`;
  - `Hai bảng xếp hạng --> RRF (k=60) --> top-5 text chunks --> kết hợp Facet -->
    verifier --> real/fake + bằng chứng + wrong_facets`.

**B4. Hiện tại graph được build bằng cách nào và quy trình tạo ra sao?**
- Graph được xây offline từ 540 chunk SGK đã làm sạch; không được tạo lại cho từng claim.
- Đây là knowledge graph có nguồn gốc bằng chứng, hiện được lưu dưới dạng các tệp JSON
  `graph_nodes.json`, `graph_edges.json` và `history_graph.json`.
- Quy trình build gồm:
  - định nghĩa schema với 7 loại node: `DocumentChunk`, `Person`, `Organization`, `Event`,
    `Place`, `Time`, `Concept` và các loại quan hệ lịch sử được phép;
  - đưa lần lượt 540 chunk vào Gemini 2.5 Flash với prompt ràng buộc schema để trích
    thực thể, quan hệ và đoạn bằng chứng nguồn;
  - Gemini chỉ trích thông tin được nêu trong chunk, trả JSON, dùng ID cục bộ trong từng
    chunk và chạy với `temperature = 0`;
  - làm sạch tất định: bỏ thực thể/quan hệ dưới ngưỡng confidence 0,8, bỏ concept quá
    chung, self-loop, endpoint lỗi và sửa quan hệ sai kiểu về dạng an toàn;
  - chuẩn hóa và căn chỉnh thực thể đồng nghĩa: 5.866 mention sạch --> 3.742 đại diện
    sau exact normalization --> 3.599 thực thể canonical;
  - việc gộp tên giống hệt được làm bằng luật; 300 nhóm alias ứng viên khó được Gemini
    rà lại có ngữ cảnh để hạn chế gộp nhầm các thực thể lịch sử;
  - tạo tất định 540 node `DocumentChunk`, 3.599 node thực thể, cạnh `MENTIONS` nối chunk
    với thực thể và các cạnh quan hệ nối thực thể với nhau;
  - mỗi cạnh quan hệ giữ `source_chunk`, `evidence_text`, `description`, `confidence` để
    luôn truy vết ngược về SGK;
  - khử trùng cạnh, kiểm tra endpoint và tạo temporal index cho 297 năm duy nhất.
- Graph không được xem là nguồn sự thật độc lập; nó là lớp chỉ mục có cấu trúc để hệ
  điều hướng về đúng chunk SGK.
- Kiến trúc build:
  - `591 trang OCR --> làm sạch còn 571 trang --> chia 540 chunk --> Gemini trích thực
    thể và quan hệ theo schema --> deterministic cleanup --> entity alignment --> build
    node/cạnh --> kiểm tra graph --> temporal index`.

**B5. Tại sao mỗi `DocumentChunk` lại được tính là một node?**
- Knowledge graph của hệ thống có hai lớp node:
  - lớp tri thức lịch sử: `Person`, `Organization`, `Event`, `Place`, `Time`, `Concept`;
  - lớp nguồn/provenance: `DocumentChunk`.
- `DocumentChunk` không phải một thực thể lịch sử; nó là node đại diện cho một đoạn SGK
  cụ thể và được tạo tất định từ corpus, không phải do Gemini trích xuất.
- Mỗi chunk được xem là một node vì nó có định danh và metadata riêng:
  - `chunk_id`;
  - nội dung văn bản;
  - sách, chương, mục và trang;
  - các năm xuất hiện trong đoạn;
  - tệp nguồn OCR tương ứng.
- Node `DocumentChunk` nối với các node thực thể bằng cạnh `MENTIONS`:
  - ví dụ: `Chunk_LS12_Bai3 --> MENTIONS --> Hồ Chí Minh`;
  - từ node `Hồ Chí Minh`, hệ thống có thể đi ngược qua cạnh `MENTIONS` để lấy đúng
    đoạn SGK đã nhắc đến nhân vật đó.
- Mục đích cụ thể:
  - truy vết mỗi thực thể và quan hệ về đúng bằng chứng trong SGK;
  - hỗ trợ Facet Graph retrieval đi từ facet --> entity node --> source chunk;
  - giữ thông tin sách/trang để trích dẫn và kiểm tra lại;
  - không để graph trở thành tập quan hệ không rõ nguồn do LLM sinh ra.
- Vì corpus có 540 chunk sạch nên graph có đúng 540 node `DocumentChunk`, mỗi chunk ứng
  với một node.
- Nếu không biểu diễn chunk thành node:
  - graph vẫn có thể lưu `source_chunk` như một thuộc tính của cạnh;
  - nhưng việc duyệt từ thực thể về văn bản nguồn, thống kê mention và lấy evidence bằng
    graph sẽ khó và kém nhất quán hơn.
- Kiến trúc liên kết:
  - `SGK --> DocumentChunk node --> MENTIONS --> Entity node --> semantic relation -->
    Entity node khác`;
  - `Facet của claim --> Entity node --> MENTIONS/source_chunk --> bằng chứng SGK`.
- Cách trả lời ngắn: `DocumentChunk` là **node nguồn**, không phải **node tri thức lịch sử**;
  nó được đưa vào graph để mọi kết quả đều truy vết được về đoạn SGK gốc.

**B6. EDA graph hiện tại như thế nào?**
- Luồng dữ liệu trước khi thành graph:
  - Gemini trích thô 6.029 entity mention và 5.057 relation từ 540 chunk;
  - sau làm sạch còn 5.866 entity mention và 4.867 relation;
  - entity alignment rút 5.866 mention về 3.742 đại diện chuẩn hóa, sau đó còn 3.599
    thực thể canonical.
- Tổng số node: 4.139, gồm:
  - `DocumentChunk`: 540;
  - `Concept`: 853;
  - `Time`: 850;
  - `Event`: 672;
  - `Place`: 503;
  - `Organization`: 427;
  - `Person`: 294.
- Tổng số edge: 10.729, gồm:
  - `MENTIONS`: 5.862 cạnh nối chunk với thực thể;
  - 4.867 cạnh quan hệ ngữ nghĩa nối các thực thể với nhau.
- Phân bố 4.867 cạnh quan hệ ngữ nghĩa:
  - `RELATED_TO`: 2.973;
  - `RESULTS_IN`: 570;
  - `OCCURRED_AT`: 544;
  - `CAUSES`: 320;
  - `PARTICIPATED_IN`: 223;
  - `LOCATED_IN`: 124;
  - `AFTER`: 67;
  - `BEFORE`: 46.
- Chỉ số chất lượng cấu trúc:
  - 0 node ID trùng;
  - 0 edge ID trùng;
  - 0 endpoint bị gãy;
  - 0 cạnh thiếu `source_chunk`;
  - 0 cạnh quan hệ thiếu bằng chứng;
  - 0 self-loop sau khi build.
- Nhận xét chính từ EDA:
  - `Concept`, `Time` và `Event` chiếm nhiều node, phù hợp đặc trưng SGK lịch sử;
  - `RELATED_TO` chiếm `2.973 / 4.867 ≈ 61,1%` cạnh ngữ nghĩa, cho thấy graph có độ phủ
    tốt nhưng nhiều quan hệ còn chung chung;
  - vì `RELATED_TO` chỉ biểu diễn sự liên quan, nó yếu hơn các cạnh cụ thể khi cần chứng
    minh trực tiếp một quan hệ đúng hoặc sai;
  - điểm mạnh là toàn bộ cạnh quan hệ đều truy vết được về chunk nguồn, còn hạn chế lớn
    nhất là độ đặc hiệu của loại quan hệ.

**B7. Facet có build gì không? Nếu có thì build cái gì?**
- Có, nhưng Facet không build thêm một knowledge graph mới và không huấn luyện model mới.
- Facet build một biểu diễn có cấu trúc riêng cho từng claim và các bảng ánh xạ từ claim
  sang graph/evidence.
- Các artifact chính được tạo gồm:
  - `claim_facets.json`: lưu 9 nhóm khía cạnh, `claim_focus` và ghi chú của từng claim;
  - `facet_matches.json`: lưu mỗi giá trị facet khớp với node graph nào và bằng phương
    pháp nào;
  - `facet_evidence.json`: lưu các chunk ứng viên được tìm qua node, năm hoặc quan hệ;
  - `facet_reranked.json`: lưu bằng chứng graph sau khi chấm điểm theo facet;
  - `hybrid_facet_reranked.json`: kết hợp top-5 bằng chứng Hybrid với tối đa 3 bằng chứng
    từ nhánh Facet Graph.
- Cách tạo facet:
  - chỉ đưa nội dung claim vào, không đưa label hoặc gold evidence;
  - luật tất định nhận diện alias graph, năm và số lượng làm tín hiệu ban đầu;
  - GPT-4o-mini xử lý theo batch và phân rã claim thành tối đa 9 loại facet;
  - chuẩn hóa JSON, giới hạn tối đa số giá trị mỗi loại và cache để mọi cấu hình dùng
    cùng một kết quả phân rã.
- Cách facet nối với graph:
  - 6 loại `person`, `organization`, `event`, `place`, `time`, `concept` được khớp theo
    exact alias --> normalized alias --> year index --> substring fallback;
  - 3 loại `quantity`, `action`, `result` chưa tạo node và không match trực tiếp vào graph,
    nhưng được đưa cho verifier để kiểm tra và tạo `wrong_facets`;
  - từ node match được, hệ tìm chunk nguồn qua `node mention`, `temporal index` và quan
    hệ `1-hop`, sau đó rerank theo độ phủ facet, quan hệ, thời gian và trùng từ.
- Kiến trúc xử lý:
  - `Claim --> rule-based signals + GPT-4o-mini --> 9 facet --> match facet với graph -->
    lấy graph evidence --> facet-aware rerank --> kết hợp top-5 Hybrid + tối đa 3 graph
    evidence --> verifier --> real/fake + bằng chứng + wrong_facets`.
- Cách trả lời ngắn: Facet build **hồ sơ khía cạnh của claim**, **bảng match facet–node**
  và **tập bằng chứng theo facet**; nó không build một graph thứ hai.

**B8. Luồng xử lý Facet hiện tại là gì? Matching vào graph, retrieve và tính điểm chunk như thế nào?**
- Luồng tổng quát:
  - `Claim --> trích 9 khía cạnh --> match 6 khía cạnh với graph --> lấy candidate chunks
    qua node/time/relation --> khử trùng và giới hạn candidate --> tính facet-aware score
    --> rerank graph chunks --> lấy tối đa 3 graph chunks --> ghép với top-5 Hybrid -->
    verifier --> real/fake + bằng chứng + wrong_facets`.
- Bước 1 — Nhận claim:
  - chỉ sử dụng trường `claim`;
  - không đưa `label`, `key` hoặc gold evidence vào truy vấn để tránh rò rỉ đáp án;
  - chuẩn hóa Unicode NFC và khoảng trắng.
- Bước 2 — Trích 9 khía cạnh:
  - luật tất định tìm alias đã có trong graph, năm và số lượng;
  - GPT-4o-mini nhận claim cùng các gợi ý rule-based và trả về JSON gồm `person`,
    `organization`, `event`, `place`, `time`, `concept`, `quantity`, `action`, `result`;
  - mỗi loại được giới hạn tối đa 8 giá trị, sau đó chuẩn hóa và khử trùng;
  - kết quả được cache trong `claim_facets.json` để mọi lần chạy dùng cùng một facet input.
- Ví dụ:
  - claim: “Nguyễn Ái Quốc thành lập Việt Minh năm 1942 tại Hà Nội”;
  - `person = [Nguyễn Ái Quốc]`;
  - `organization = [Việt Minh]`;
  - `time = [1942]`;
  - `place = [Hà Nội]`;
  - `action = [thành lập]`.
- Bước 3 — Matching facet vào graph:
  - `person` chỉ match node `Person`;
  - `organization` chỉ match `Organization`;
  - `event` chỉ match `Event`;
  - `place` chỉ match `Place`;
  - `time` chỉ match `Time` và temporal index;
  - `concept` chỉ match `Concept`;
  - `quantity`, `action`, `result` không match node vì graph hiện chưa có node tương ứng.
- Thứ tự/cơ chế matching:
  - chuẩn hóa facet và alias: lowercase, bỏ khác biệt dấu câu/khoảng trắng nhưng giữ
    nội dung tiếng Việt;
  - với `time`, ưu tiên tìm năm trong temporal index;
  - tìm exact/normalized alias trong `entity_aliases.json`;
  - nếu không có kết quả thì dùng substring fallback, ví dụ `Quốc dân Đảng` có thể khớp
    alias dài hơn `Việt Nam Quốc dân Đảng`;
  - bỏ alias quá ngắn dưới 4 ký tự, substring phải có ít nhất 6 ký tự;
  - mỗi giá trị facet được giữ tối đa 5 node match;
  - lưu `node_id`, `node_type`, `matched_alias`, `match_method`, `mention_count` để audit.
- Bước 4 — Retrieve candidate chunk từ mỗi node đã match:
  - đường `node_mention`: lấy các `DocumentChunk` nối với node bằng cạnh `MENTIONS`;
  - đường `relation_1hop`: lấy `source_chunk` của các cạnh 1-hop đi vào hoặc đi ra node,
    gồm `PARTICIPATED_IN`, `OCCURRED_AT`, `LOCATED_IN`, `RELATED_TO`, `CAUSES`,
    `RESULTS_IN`, `BEFORE`, `AFTER`;
  - đường `temporal_index`: với facet `time`, lấy chunk được index theo năm trong claim;
  - mọi đường đều trả về chunk SGK thật; node/edge chỉ đóng vai trò điều hướng.
- Giới hạn candidate trước khi chấm điểm:
  - đường node mention + relation 1-hop lấy tối đa 5 chunk cho mỗi giá trị facet;
  - riêng facet `time` có thể bổ sung tối đa 5 chunk từ temporal index trước khi áp dụng
    giới hạn chung;
  - khử trùng theo `chunk_id`: một chunk đi vào từ nhiều facet hoặc nhiều đường chỉ giữ
    một lần nhưng cộng dồn `facet_hits`, `relation_hits` và `node_ids`;
  - ưu tiên sơ bộ chunk phủ nhiều facet hơn, có nhiều relation hit hơn, rồi giới hạn tối đa
    12 candidate chunk cho mỗi claim.
- Bước 5 — Tính điểm cho từng candidate chunk:
  - `facet_coverage = số facet khác nhau dẫn tới chunk / tổng số facet của claim`;
  - `relation_score = min(1, log(1 + số relation_hits) / log(4))`;
  - `temporal_score = số năm của claim xuất hiện trong chunk / tổng số năm của claim`;
  - `text_overlap = số token phân biệt của claim xuất hiện trong chunk / tổng số token
    phân biệt của claim`, chỉ xét token dài từ 3 ký tự;
  - điểm thô:
    `score = 0,45×facet_coverage + 0,25×relation_score + 0,20×temporal_score + 0,10×text_overlap`;
  - chunk quá phổ biến trong candidate của nhiều claim bị giảm bằng hub penalty:
    `final_score = score / (1 + 0,15×ln(1 + hub_frequency))`.
- Chi tiết cách tính từng thành phần điểm:
  - `facet_coverage`:
    - mẫu số là tổng số **giá trị facet** được trích từ claim, không phải luôn cố định là 9;
    - tử số là số cặp `(facet_type, facet_value)` khác nhau đã dẫn tới chunk đang xét;
    - công thức: `facet_coverage = số facet hit khác nhau của chunk / tổng facet values`;
    - ví dụ claim có 5 giá trị facet gồm 1 person, 1 organization, 1 time, 1 place và
      1 action; chunk được retrieve nhờ person, organization và time thì
      `facet_coverage = 3/5 = 0,6`;
    - trọng số 0,45 là cao nhất vì chunk phủ nhiều phần của claim thường có khả năng chứa
      bằng chứng đầy đủ hơn;
    - các facet không match graph như `action`, `quantity`, `result` vẫn nằm trong mẫu số,
      nên hệ không tự xem claim đã được phủ đầy đủ chỉ vì match được các entity chính.
  - `relation_score`:
    - đếm số `relation_hits` khác nhau đưa chunk vào candidate pool;
    - công thức: `relation_score = min(1, ln(1 + n_relation_hits) / ln(4))`;
    - 0 relation hit --> `0`;
    - 1 relation hit --> `ln(2)/ln(4) = 0,5`;
    - 2 relation hits --> `ln(3)/ln(4) ≈ 0,792`;
    - từ 3 relation hits trở lên --> bị chặn tối đa ở `1`;
    - log giúp điểm tăng dần nhưng không để một chunk có quá nhiều cạnh lấn át toàn bộ
      các tín hiệu còn lại;
    - trọng số 0,25 ưu tiên chunk có quan hệ 1-hop có bằng chứng nguồn hơn chunk chỉ nhắc
      tên thực thể qua cạnh `MENTIONS`.
  - `temporal_score`:
    - lấy tập năm trong claim bằng regex;
    - lấy tập năm của chunk từ metadata `years` kết hợp các năm xuất hiện trong text;
    - công thức: `temporal_score = |claim_years ∩ chunk_years| / |claim_years|`;
    - ví dụ claim có hai năm `{1945, 1946}`, chunk chỉ chứa `1945` thì điểm bằng `1/2 = 0,5`;
    - nếu claim không có năm thì `temporal_score = 0`, thành phần này không cộng điểm;
    - trọng số 0,20 giúp ưu tiên bằng chứng đúng mốc thời gian nhưng không quyết định toàn
      bộ thứ hạng.
  - `text_overlap`:
    - tokenize claim và chunk, chỉ giữ các token dài từ 3 ký tự rồi chuyển thành hai tập
      token phân biệt;
    - công thức: `text_overlap = |claim_tokens ∩ chunk_tokens| / |claim_tokens|`;
    - ví dụ claim có 10 token phân biệt hợp lệ, chunk chứa 4 token trong số đó thì
      `text_overlap = 4/10 = 0,4`;
    - nếu claim không còn token hợp lệ thì điểm bằng 0;
    - trọng số chỉ 0,10 vì đây là tín hiệu phụ; phần ngữ nghĩa đã được hỗ trợ bởi facet và
      nhánh Hybrid.
  - `hub penalty`:
    - `hub_frequency` là số claim mà một chunk xuất hiện trong candidate pool, mỗi chunk
      chỉ được đếm một lần trên mỗi claim;
    - công thức: `final_score = raw_score / (1 + 0,15 × ln(1 + hub_frequency))`;
    - chunk càng xuất hiện cho nhiều claim thì mẫu số càng lớn và điểm cuối càng giảm;
    - mục đích là hạ các chunk chung chung hoặc hub chunk thường được graph trả về cho
      quá nhiều truy vấn.
- Ví dụ tính điểm hoàn chỉnh cho một chunk:
  - claim có 5 facet values, chunk phủ 3 --> `facet_coverage = 0,6`;
  - chunk có 2 relation hits --> `relation_score ≈ 0,792`;
  - claim có 2 năm, chunk khớp 1 năm --> `temporal_score = 0,5`;
  - claim có 10 token, chunk khớp 4 token --> `text_overlap = 0,4`;
  - điểm thô:
    `0,45×0,6 + 0,25×0,792 + 0,20×0,5 + 0,10×0,4 = 0,608`;
  - nếu chunk xuất hiện trong candidate pool của 9 claim thì
    `final_score = 0,608 / (1 + 0,15×ln(10)) ≈ 0,452`;
  - hệ tính tương tự cho các candidate còn lại rồi xếp `final_score` từ cao xuống thấp.
- Các giới hạn config hiện tại:
  - trích facet:
    - có 9 loại facet được phép;
    - mỗi loại facet có tối đa 8 giá trị;
    - facet extraction chạy batch 10 claim;
  - matching:
    - alias ngắn dưới 4 ký tự bị loại khỏi alias index;
    - substring fallback yêu cầu tối thiểu 6 ký tự;
    - mỗi **giá trị facet** match tối đa 5 node graph;
    - không dùng embedding fallback trong facet-to-node matching;
  - retrieve graph evidence:
    - chỉ duyệt quan hệ 1-hop;
    - mỗi giá trị facet lấy tối đa 5 chunk qua node mention và relation 1-hop;
    - facet `time` có thể bổ sung tối đa 5 chunk theo temporal index;
    - sau khi hợp nhất và khử trùng, mỗi claim giữ tối đa 12 candidate chunk trước rerank;
  - rerank:
    - trọng số lần lượt là `0,45/0,25/0,20/0,10`;
    - hệ số hub penalty là `0,15`;
    - lưu tối đa top-8 graph evidence sau rerank;
    - text mỗi graph evidence được giới hạn 1.400 ký tự ở bước rerank;
  - fusion với Hybrid:
    - lấy top-5 text chunks từ Hybrid;
    - lấy tối đa top-3 graph chunks từ Facet;
    - khử trùng theo `chunk_id` và giữ tối đa 8 bằng chứng cuối;
    - nếu có chunk trùng giữa hai nhánh thì số evidence cuối có thể nhỏ hơn 8.
- Bước 6 — Rerank và kết hợp Hybrid:
  - sắp xếp tối đa 12 candidate theo `final_score` giảm dần;
  - nhánh Facet giữ top-8 để lưu/audit, nhưng khi fusion chỉ lấy tối đa top-3 graph chunks;
  - lấy top-5 text chunks đã được BM25 + BGE-M3 + RRF chọn;
  - ghép `5 text + tối đa 3 graph`, khử trùng lại theo `chunk_id`, tối đa 8 bằng chứng;
  - nếu một graph chunk đã có trong top-5 text thì chỉ giữ một bản;
  - verifier đọc claim, 9 facet và tập bằng chứng cuối để trả nhãn, giải thích và
    `wrong_facets`.
- Cách trả lời ngắn:
  - `Claim --> 9 facet --> facet-to-node matching --> node/time/1-hop retrieval -->
    tối đa 12 candidate --> facet-aware scoring --> top-3 graph evidence --> ghép top-5
    Hybrid --> verifier`.

**B9. 9 khía cạnh là gì? Vì sao sử dụng 9 khía cạnh đó và mục đích cụ thể là gì?**
- 9 khía cạnh gồm:
  - `person`: nhân vật lịch sử;
  - `organization`: tổ chức, quốc gia, đảng phái hoặc lực lượng;
  - `event`: sự kiện, hội nghị, chiến dịch hoặc văn kiện;
  - `place`: địa điểm, quốc gia hoặc khu vực;
  - `time`: ngày, năm hoặc giai đoạn;
  - `concept`: chính sách, học thuyết hoặc khái niệm lịch sử;
  - `quantity`: con số, số lượng hoặc tỉ lệ;
  - `action`: hành động hoặc vai trò chính;
  - `result`: kết quả, tác động hoặc hệ quả.
- Vì sao chọn 9 loại này:
  - đây là các thành phần thường quyết định tính đúng/sai của một nhận định lịch sử;
  - chúng cũng bao phủ các kiểu bóp méo phổ biến trong dữ liệu như đổi nhân vật, tổ chức,
    thời gian, địa điểm, hành động, con số hoặc kết quả;
  - 6 loại đầu ánh xạ trực tiếp vào 6 kiểu nút đồ thị: `Person`, `Organization`, `Event`,
    `Place`, `Time`, `Concept`;
  - 3 loại `quantity`, `action`, `result` chưa ánh xạ trực tiếp thành nút, nhưng vẫn cần
    cho bước kiểm chứng và giải thích.
- Mục đích cụ thể:
  - tách một claim dài thành các đơn vị nhỏ cần kiểm tra, thay vì xem claim như một khối;
  - dùng 6 facet có kiểu để nối claim với các thực thể tương ứng và bổ sung bằng chứng
    cho kết quả truy xuất Hybrid;
  - cung cấp một checklist có cấu trúc để bộ kiểm chứng đối chiếu từng chi tiết với bằng chứng;
  - khi kết luận `fake`, trả về `wrong_facets` để chỉ rõ sai ở thời gian, nhân vật, địa điểm,
    hành động, kết quả... thay vì chỉ đưa ra một nhãn chung chung.
- Căn cứ phương pháp: kế thừa ý tưởng phân rã claim thành đơn vị nhỏ của FactScore và
  ProgramFC, nhưng hệ thống phân loại rõ từng đơn vị để phù hợp với miền lịch sử và cấu
  trúc dữ liệu của mình.
- Lưu ý khi trả lời: facet chỉ là tín hiệu truy xuất và khung kiểm tra; một giá trị xuất hiện
  trong claim không được mặc định là đúng mà vẫn phải được đối chiếu với bằng chứng.

**B10. Hybrid có dùng graph không? Graph đóng góp gì, tại sao dùng Facet Graph và khác gì BM25/BGE-M3/Hybrid?**
- Cần phân biệt đúng tên cấu hình:
  - `Hybrid` là text retrieval gồm `BM25 + BGE-M3 + RRF`; cấu hình này **không dùng graph**;
  - `Hybrid + Facet Graph` mới là hệ kết hợp top-5 text evidence của Hybrid với tối đa
    3 graph evidence từ nhánh Facet.
- Luồng hai cấu hình:
  - `Hybrid: Claim --> BM25 top-20 + BGE-M3 top-20 --> RRF --> top-5 text chunks`;
  - `Hybrid + Facet Graph: Claim --> Hybrid top-5 text chunks + Facet-to-Graph retrieval
    top-3 graph chunks --> verifier`.
- Khác nhau giữa từng phương pháp:
  - BM25:
    - tìm trực tiếp trong 540 chunk bằng mức trùng từ khóa;
    - mạnh với tên riêng, niên đại và cụm từ xuất hiện gần giống SGK;
    - yếu khi claim paraphrase hoặc dùng cách diễn đạt khác.
  - BGE-M3:
    - tìm trực tiếp trong 540 chunk bằng độ gần giữa vector claim và vector chunk;
    - mạnh với tương đồng ngữ nghĩa và paraphrase;
    - có thể lấy đoạn đúng chủ đề nhưng sai chi tiết nhỏ như năm, người hoặc số lượng.
  - Hybrid:
    - hợp nhất hai bảng xếp hạng BM25 và BGE-M3 bằng RRF;
    - tận dụng cả lexical và semantic retrieval;
    - bằng chứng vẫn là các đoạn văn bản phẳng, chưa biểu diễn claim sai ở khía cạnh nào.
  - Facet Graph:
    - tách claim thành các khía cạnh có kiểu;
    - match `person`, `organization`, `event`, `place`, `time`, `concept` với node graph;
    - đi từ node qua `MENTIONS`, temporal index hoặc quan hệ 1-hop để quay về chunk SGK;
    - chấm điểm chunk theo facet coverage, relation, thời gian, text overlap và hub penalty;
    - giữ dấu vết `facet --> node --> relation --> source_chunk` để giải thích và audit.
- Graph đóng góp gì cho retrieval:
  - tạo một đường tìm bằng chứng khác với lexical/vector similarity;
  - có thể tìm chunk thông qua alias thực thể, mốc thời gian hoặc quan hệ dù chunk không
    có độ giống cao với toàn bộ câu claim;
  - cứu 54 claim mà Hybrid dự đoán sai, trong đó có 45 claim `real`;
  - có 28 claim được kết luận đúng chỉ nhờ graph evidence trong phân tích citation;
  - recall `real` tăng từ 86,1% của Hybrid lên 87,6% với Hybrid + Facet Graph.
- Graph đóng góp gì ngoài accuracy:
  - liên kết evidence với node, relation, sách, bài, trang và source chunk;
  - giúp verifier kiểm tra từng phần thay vì chỉ đọc claim như một khối;
  - hỗ trợ trả `wrong_facets`, tức chỉ rõ sai ở `time`, `place`, `event`, `action`, `result`...;
  - 97,5% dự đoán `fake` của hệ đề xuất có chỉ ra khía cạnh sai.
- Tại sao phải dùng **Facet Graph** thay vì đưa nguyên claim vào graph:
  - graph có nhiều node và alias; match nguyên claim dễ bị chi phối bởi node phổ biến hoặc
    cụm từ chung chung;
  - facet giới hạn đúng kiểu node, ví dụ giá trị `person` chỉ được match với `Person`;
  - facet cho biết node/chunk nào đang phục vụ phần nào của claim;
  - facet coverage giúp ưu tiên chunk phủ nhiều chi tiết cần kiểm tra;
  - graph hiện có 61,1% cạnh `RELATED_TO`, nên cần facet và reranking để giảm candidate
    chung chung, dù chưa loại bỏ hoàn toàn distractor.
- Hạn chế và kết luận trung thực:
  - Graph cứu 54 claim nhưng làm hỏng 75 claim Hybrid vốn đúng, net effect là giảm 21
    câu trên tập cân bằng 2.000;
  - accuracy giảm từ 88,10% của Hybrid xuống 87,05% của Hybrid + Facet Graph;
  - chênh lệch 1,05 điểm có `p = 0,078 > 0,05`, nên chưa có ý nghĩa thống kê;
  - recall `fake` giảm từ 90,1% xuống 86,5% vì graph đôi khi đưa evidence đúng chủ đề
    nhưng không bác bỏ đúng chi tiết sai;
  - xét riêng hit-rate, Hybrid top-8 đạt 92,9%, cao hơn 91,3% của cấu hình có graph;
  - vì vậy không được kết luận graph vượt Hybrid về accuracy hoặc coverage trung bình.
- Vậy tại sao vẫn giữ Facet Graph:
  - bài toán cần ba đầu ra: nhãn, bằng chứng và giải thích;
  - nếu mục tiêu duy nhất là accuracy trung bình thì Hybrid text hiện là lựa chọn mạnh hơn;
  - nếu cần truy vết bằng chứng có cấu trúc, cứu một số trường hợp text retrieval bỏ sót
    và giải thích theo khía cạnh thì Facet Graph mang lại năng lực mà BM25, BGE-M3 và
    Hybrid text không có.
- Cách trả lời ngắn:
  - “Hybrid không dùng graph; nó chỉ gồm BM25, BGE-M3 và RRF. Graph chỉ xuất hiện trong
    Hybrid + Facet Graph. Graph chưa tăng accuracy trung bình, nhưng bổ sung một đường
    retrieval theo thực thể–thời gian–quan hệ, truy vết về SGK và giải thích theo khía cạnh.”

**B11. Sao không fine-tune một model phân loại thay vì prompt LLM?**
- Oracle đạt 99,8% khi có đúng bằng chứng, cho thấy suy luận không phải nút thắt chính.
- Nút thắt hiện tại là truy xuất chưa tìm được đúng bằng chứng; fine-tune verifier không
  trực tiếp giải quyết vấn đề này.
- Fine-tune còn cần thêm dữ liệu nhãn chất lượng cao và có thể làm giảm sự linh hoạt của
  phần giải thích tự do.
- Hướng phát triển có thể thử tinh chỉnh một model mã nguồn mở phù hợp với tiếng Việt,
  nhưng đó chưa phải thành phần của hệ thống hiện tại.

**B12. Smart crop dựa vào trùng từ vựng — nếu claim sai từ khóa thì cửa sổ có bị chọn sai?**
- Có, đây là hạn chế đã được đo trong thí nghiệm.
- Hit-rate của bằng chứng toàn văn là 90,5%, sau smart crop còn 85,5%, tức bị giảm
  khoảng 5 điểm phần trăm.
- Tuy nhiên smart crop vẫn tốt hơn cách lấy phần đầu đoạn: 85,5% so với 59,5%, cải thiện
  khoảng 26 điểm phần trăm.
- Smart crop là heuristic gần như không phát sinh chi phí; thay bằng cơ chế chọn đoạn
  theo ngữ nghĩa là hướng cải tiến.

**B13. RRF hiện tại có trọng số không? `k=60` và bộ `0,45/0,25/0,20/0,10` là gì?**
- RRF hiện tại không có trọng số riêng cho BM25 và BGE-M3.
- Hai kênh được hợp nhất ngang nhau bằng:
  - `RRF(d) = 1/(60 + rank_BM25(d)) + 1/(60 + rank_BGE-M3(d))`;
  - nếu chunk vắng mặt trong top-20 của một kênh thì thành phần của kênh đó bằng 0.
- `k=60` là hằng số làm trơn thường dùng từ công trình RRF gốc và được cố định trước
  khi đánh giá.
- Bộ `0,45/0,25/0,20/0,10` không thuộc RRF; đây là trọng số của bước facet-aware
  reranking dành cho bằng chứng từ graph:
  - `0,45 × facet_coverage`;
  - `0,25 × relation_score`;
  - `0,20 × temporal_score`;
  - `0,10 × text_overlap`.
- Hai bước cần phân biệt:
  - `BM25 top-20 + BGE-M3 top-20 --> RRF không trọng số --> top-5 text chunks`;
  - `Facet Graph candidates --> facet-aware reranking có bốn trọng số --> tối đa 3 graph chunks`.
- Nếu dùng weighted RRF thì công thức phải có dạng
  `w_BM25/(60 + rank_BM25) + w_BGE/(60 + rank_BGE)`, nhưng hệ thống hiện tại không
  triển khai biến thể này.

## C. KẾT QUẢ

**C2. Sao tập cân bằng 87% mà toàn bộ chỉ 81,5%?**
Khác thành phần: tập đầy đủ 66% claim đề thi (diễn đạt xa văn bản gốc, hit-rate bằng
chứng chỉ 72,9% so với 86,6%). Pipeline ổn định: chạy full lặp lại đúng 87,6% trên chính
2.000 ID của tập cân bằng. (§4.6)

**C3. Oracle 99,8% — cho xem đáp án thì đo làm gì?**
Là cấu hình CHẨN ĐOÁN, dán nhãn rõ, không phải kết quả hệ thống: nó tách lỗi suy luận
khỏi lỗi truy xuất, xác định trần và định hướng toàn bộ phân tích thành phần. ViFactCheck
cũng dùng thiết lập gold-evidence tương tự.

**C4. Sao không so số với SemViQA/ViFactCheck?**
Khác bộ dữ liệu, miền và điều kiện (SemViQA chọn câu trong ngữ cảnh cho trước; tụi em
truy xuất từ toàn kho 540 đoạn). So trực tiếp bằng số là khập khiễng — nên đối chiếu
theo thiết kế/năng lực và kế thừa tinh thần strict accuracy (đánh giá truy xuất riêng).

**C5. Bảng hit-rate: hệ 8 bằng chứng so 5 là không công bằng?**
Đúng, nên bảng có dòng đối chứng cùng ngân sách: Hybrid top-8 đạt 92,9% — cao hơn hệ
(91,3%). Tụi em kết luận thẳng: xét riêng độ bao phủ, đồ thị không vượt việc lấy thêm văn
bản; giá trị của nó nằm ở nhóm câu cụ thể nó cứu được và cấu trúc giải thích. (§4.3.1)

## D. ĐÁNH GIÁ & TÁI LẬP

**D1. LLM ngẫu nhiên — kết quả tái lập được không?**
Temperature 0; toàn bộ tầng truy xuất tất định chạy cục bộ; checkpoint-resume; bằng chứng
thực nghiệm: full-run tái lập 87,58% trên cùng 2.000 ID (so 87,05% run gốc). Mã nguồn,
cấu hình, dữ liệu và kết quả từng câu nộp kèm — chạy lại được từ README.

**D2. Làm sao chắc Gemini không "thuộc bài" dataset này?**
Dataset tự xây, chưa công bố; claim fake sinh mới. Kiến thức nền của model là có thật
(LLM-only 81,65%) nhưng hệ vượt nó có ý nghĩa thống kê, và bài toán yêu cầu bằng chứng
dẫn nguồn — thứ trí nhớ model không cung cấp được.

**D3. Evidence hit-rate được đo như thế nào và rút ra được gì?**
- Mục tiêu của hit-rate là đo riêng tầng retrieval: hệ có tìm được đoạn chứa bằng chứng
  tham chiếu hay không, trước khi xét verifier có kết luận đúng hay không.
- Dữ liệu dùng để đo:
  - `gold_relevant` là đoạn bằng chứng tham chiếu của từng claim;
  - `retrieved_context` hoặc `top_evidence` là các chunk hệ thống trả về;
  - `gold_relevant` chỉ được đọc ở bước đánh giá, không được đưa vào query, matching,
    reranking hoặc prompt của hệ thống.
- Chuẩn hóa trước khi so sánh:
  - chuyển Unicode về NFC;
  - lowercase;
  - tách token bằng biểu thức `\w+`;
  - bỏ token ngắn dưới 3 ký tự để giảm ảnh hưởng của hư từ và nhiễu OCR;
  - dùng `Counter`, nên một token xuất hiện lặp lại trong gold được tính theo đúng số lần.
- Coverage của một gold evidence đối với một passage được tính bằng:
  - `covered_tokens = Σ min(số lần token xuất hiện trong gold, số lần token xuất hiện trong passage)`;
  - `coverage = covered_tokens / tổng số token của gold`.
- Quy tắc xác định một claim là hit:
  - so gold evidence riêng với từng chunk trong top-k, không nối tất cả chunk thành một đoạn;
  - nếu có ít nhất một chunk đạt `coverage >= 0,60` thì claim đó là `hit`;
  - nếu không chunk nào đạt ngưỡng thì là `miss`;
  - claim không có token gold hợp lệ được loại khỏi mẫu số.
- Hit-rate toàn tập:
  - `hit_rate = số claim hit / số claim có gold evidence hợp lệ`;
  - ví dụ gold có 10 token nội dung và một chunk phủ đúng ít nhất 6 token thì claim được
    tính là hit, dù chunk không trùng toàn bộ gold.
- Phân biệt hai phép đo:
  - `evidence hit-rate`: đo trên toàn văn các chunk vừa được retrieval trả về;
  - `gold-in-context`: đo lại trên phần văn bản sau smart crop thực sự được đưa cho verifier;
  - hit trước crop nhưng miss sau crop nghĩa là retrieval đã tìm đúng chunk nhưng bước
    cắt context làm rơi phần bằng chứng quan trọng.
- Kết quả trên tập cân bằng 2.000 claim, theo ngân sách chính:
  - Dense BGE-M3 top-5: 82,4%;
  - BM25 top-5: 90,1%;
  - Hybrid top-5: 90,5%;
  - Hybrid + Facet Graph, tối đa 8 evidence: 91,3%.
- Kết quả đo lại trên toàn bộ 11.344 claim từ artifact hiện tại:
  - Dense BGE-M3 top-5: 73,6% (`8.344/11.344`);
  - BM25 top-5: 79,7% (`9.036/11.344`);
  - Hybrid top-5: 81,5% (`9.244/11.344`);
  - Hybrid + Facet Graph top-8: 82,7% (`9.377/11.344`).
- Rút ra về các retriever:
  - BM25 vượt Dense rõ rệt, cho thấy tên riêng, niên đại và cụm từ lịch sử là tín hiệu
    từ vựng rất mạnh trong corpus này;
  - Hybrid cao hơn BM25 vì BGE-M3 cứu thêm một số trường hợp paraphrase, nhưng mức tăng
    không lớn trên tập cân bằng: 90,1% --> 90,5%;
  - hệ có graph đạt hit-rate cao nhất trong bảng chính, nhưng dùng tối đa 8 evidence trong
    khi baseline chỉ dùng 5 nên chưa thể quy toàn bộ phần tăng cho graph;
  - đối chứng cùng ngân sách cho thấy Hybrid top-8 đạt 92,9%, cao hơn 91,3% của hệ có
    graph; vì vậy graph chưa vượt cách đơn giản là lấy thêm text nếu chỉ xét coverage.
- Rút ra về nút thắt hệ thống:
  - oracle đạt 99,8% khi có đúng gold evidence, trong khi hit-rate thực tế thấp hơn nhiều;
  - điều này cho thấy thiếu hoặc làm rơi bằng chứng là một nút thắt lớn hơn năng lực suy
    luận của verifier;
  - trên full set, hệ cuối miss 1.967 claim ở phép đo raw evidence;
  - trong số đó, 634 claim, tương đương 5,6% toàn tập, có coverage tốt nhất trên **toàn
    corpus** vẫn dưới 60%; đây là tổn thất cấu trúc do OCR, chunking hoặc gold evidence
    trải qua nhiều chunk;
  - phần miss còn lại vẫn có chunk phù hợp đâu đó trong corpus, nên chủ yếu là lỗi retrieval
    hoặc ranking chưa đưa đúng chunk vào top-k.
- Hit-rate không cho biết điều gì:
  - hit không đồng nghĩa verifier sẽ dự đoán đúng;
  - metric chỉ xác nhận có ít nhất một chunk phủ gold, không đo các chunk còn lại có gây
    nhiễu hay không;
  - metric dựa trên overlap token nên chưa đánh giá đầy đủ đồng nghĩa, phủ định hoặc quan
    hệ support/refute;
  - vì vậy hit-rate phải đọc cùng accuracy, Macro-F1, oracle và phân tích distractor.
- Cách trả lời ngắn:
  - “Mỗi gold evidence được tokenize và so riêng với từng chunk top-k. Nếu một chunk phủ
    ít nhất 60% số token nội dung của gold thì claim là hit. Hit-rate giúp tách lỗi retrieval
    khỏi lỗi suy luận; kết quả cho thấy retrieval là nút thắt chính, nhưng hit-rate cao không
    đảm bảo accuracy cao vì context vẫn có thể chứa distractor.”

**D4. Ngưỡng 60% token của hit-rate là tự đặt?**
- Đúng, định nghĩa được nêu rõ trong §4.2.1 và cố định trước khi đo.
- Ngưỡng được dùng nhất quán cho mọi cấu hình để chịu được khác biệt diễn đạt và nhiễu OCR.
- Thay đổi ngưỡng sẽ làm dịch chuyển mức hit-rate tuyệt đối; vì vậy khi so sánh phải giữ
  cùng ngưỡng, cùng tập claim và cùng ngân sách top-k.

**D5. Chất lượng lời giải thích đánh giá thế nào? Chỉ số cấu trúc là chưa đủ.**
- Đồng ý, chỉ số cấu trúc chưa đủ để khẳng định lời giải thích đúng về mặt nội dung.
- Hiện hệ thống đo được:
  - 98,5% trích dẫn hợp lệ;
  - 97,5% dự đoán `fake` chỉ đích danh khía cạnh;
  - phân tích định tính trên các ví dụ.
- Đánh giá người theo rubric trên quy mô rộng là hướng hoàn thiện và đã được nêu trong
  §4.2.3 và C5.

## E. GIỚI HẠN & TRIỂN KHAI

**E1. Claim ngoài phạm vi SGK thì sao?**
Hệ chỉ phán trong phạm vi nguồn chuẩn đã khai báo; chưa có nhãn "không đủ thông tin" —
hạn chế số 5, hướng phát triển bổ sung NEI để hệ biết từ chối kết luận.

**E2. Chi phí vận hành mỗi nhận định?**
1 lượt Gemini (verify) + ~0,1 lượt GPT-4o-mini (phân rã, batch 10); truy xuất chạy local
miễn phí. Toàn bộ 11.344 câu hết ~11,3k lượt Gemini.

**E3. 10% tổn thất do chunking/OCR — sao không sửa luôn?**
Vì phát hiện này ra đời TỪ phân tích lỗi của hệ hoàn chỉnh (coverage trung vị 0,52 tại
các case trượt). Sửa nó là tái cấu trúc kho tài liệu — đúng việc của vòng tiếp theo,
được xếp ưu tiên #1 trong hướng phát triển vì nâng cận trên của mọi tầng.

## F. CÂU NHẠY CẢM — TRẢ LỜI TRUNG THỰC

**F1. "Lần trước báo cáo 86%, giờ sao còn 81,5%?"**
"Số 86% thuộc phiên bản đầu, đo bằng quy trình đánh giá cũ mà sau đó tụi em phát hiện có
lỗi: một số trường sinh dữ liệu lọt vào truy vấn truy xuất, làm kết quả bị thổi phồng.
Tụi em đã thiết kế lại quy trình — tách biệt tuyệt đối thông tin sinh dữ liệu khỏi đầu
vào hệ thống (nguyên tắc nêu ở §3.1) — và toàn bộ số trong quyển đo theo quy trình mới.
81,46% thấp hơn về mặt số nhưng là kết quả tin cậy được; thực tế trên cùng điều kiện cũ,
phiên bản đầu chỉ đạt 77%."
→ KHÔNG né tránh câu này; trả lời chủ động, ngắn, rồi chỉ vào nguyên tắc thiết kế.

**F2. Phân công công việc hai thành viên?**
(Tự chuẩn bị theo thực tế nhóm — nên rành mạch: ai phần dữ liệu, ai phần hệ thống/đánh giá.)
