# BÀI THUYẾT TRÌNH BẢO VỆ KHÓA LUẬN TỐT NGHIỆP

**Đề tài:** Xây dựng hệ thống kiểm chứng thông tin lịch sử Việt Nam dựa trên tài liệu THPT
**Sinh viên:** Nguyễn Duy Ân (22127006) - Đỗ Lê Khoa (22127195)
**GVHD:** TS. Lê Thanh Tùng - ThS. Văn Chí Nam
**Thời lượng dự kiến:** 15-20 phút

---

## Slide 1: Trang bìa

Kính thưa Quý Thầy Cô trong Hội đồng, kính thưa Quý Thầy Cô và các bạn.

Em là Nguyễn Duy Ân, cùng với bạn Đỗ Lê Khoa, chúng em xin được trình bày khóa luận tốt nghiệp với đề tài: **"Xây dựng hệ thống kiểm chứng thông tin lịch sử Việt Nam dựa trên tài liệu Trung học phổ thông"**, dưới sự hướng dẫn của thầy TS. Lê Thanh Tùng và thầy ThS. Văn Chí Nam.

---

## Slide 2: Nội dung

Bài trình bày của chúng em gồm bảy phần:

Đầu tiên là giới thiệu bài toán với đầu vào và đầu ra cụ thể. Tiếp theo là những thử thách của bài toán, các đóng góp chính của khóa luận, và các nghiên cứu liên quan trực tiếp. Phần trọng tâm là phương pháp đề xuất, sau đó là thực nghiệm và thảo luận kết quả. Cuối cùng là kết luận và hướng phát triển.

---

## Slide 3: Giới thiệu bài toán

Trước hết, em xin phát biểu bài toán.

Hiện nay, thông tin sai lệch về lịch sử Việt Nam lan truyền ngày càng nhanh trên các nền tảng trực tuyến, ảnh hưởng trực tiếp đến nhận thức của người học, đặc biệt là học sinh phổ thông. Vì vậy, chúng em xây dựng một hệ thống kiểm chứng nhận định lịch sử dựa trên nguồn tri thức chính thống.

Cụ thể, **đầu vào** của hệ thống là một câu nhận định về lịch sử Việt Nam bằng tiếng Việt.

**Phạm vi tri thức** để kiểm chứng được giới hạn trong sách giáo khoa Lịch sử lớp 10, 11 và 12, được tổ chức thành hai lớp: lớp văn bản và lớp đồ thị, và mọi kết luận đều có thể truy vết về nguồn.

**Đầu ra** gồm ba thành phần: thứ nhất là nhãn đúng hoặc sai; thứ hai là các đoạn bằng chứng liên quan trích từ sách giáo khoa; và thứ ba là lời giải thích bám sát bằng chứng. Như vậy, hệ thống không chỉ trả lời "đúng hay sai" mà còn trả lời "vì sao", với căn cứ mà người học có thể tự đối chiếu.

---

## Slide 4: Thử thách của bài toán

Bài toán này có ba nút thắt chính.

**Thứ nhất là dữ liệu chuyên biệt.** Hiện chưa có bộ dữ liệu kiểm chứng lịch sử Việt Nam nào có đầy đủ nhãn và bằng chứng. Các bộ dữ liệu tiếng Việt hiện có chủ yếu xây dựng từ báo chí và mạng xã hội, còn các nguồn mở như Wikipedia thì không bảo đảm phù hợp với nội dung giáo dục.

**Thứ hai là bằng chứng dài và phân tán.** Thông tin quyết định để kiểm chứng một nhận định có thể nằm rải rác ở nhiều đoạn văn, bị cắt bởi ranh giới phân đoạn, hoặc bị nhiễu do quá trình OCR sách giáo khoa.

**Thứ ba, kết luận phải giải thích được.** Trong bối cảnh giáo dục, chỉ dự đoán đúng/sai là chưa đủ — lời giải thích phải trích dẫn đúng nguồn và chỉ ra được cụ thể khía cạnh nào của nhận định bị sai lệch.

---

## Slide 5: Đóng góp của khóa luận

Từ ba thử thách đó, khóa luận có ba đóng góp chính, nối liền từ dữ liệu, phương pháp đến đầu ra.

**Một là về dữ liệu:** chúng em xây dựng bộ dữ liệu kiểm chứng chuyên biệt cho lịch sử Việt Nam gồm 11.344 nhận định, mỗi nhận định gắn với nhãn và bằng chứng tham chiếu.

**Hai là về phương pháp:** chúng em đề xuất cơ sở tri thức hai lớp và phương pháp **Facet Graph RAG** — RAG đồ thị theo khía cạnh — kết hợp truy xuất văn bản với tín hiệu thực thể, quan hệ và thời gian từ đồ thị tri thức.

**Ba là về đầu ra:** hệ thống thực hiện đồng thời phân loại, trích dẫn bằng chứng và sinh lời giải thích theo khía cạnh, giúp giáo viên và học sinh đối chiếu trực tiếp với tài liệu chính thống.

---

## Slide 6: Nghiên cứu liên quan

Chúng em khảo sát ba công trình đại diện cho ba hướng tiếp cận, và mỗi hướng đều để lại khoảng trống trong miền lịch sử.

**Công trình thứ nhất, KG-BERT kết hợp Datalog,** kiểm chứng trên 130.190 bộ ba trích từ Wikipedia và đạt F1 rất cao là 0,9596. Điểm mạnh là tri thức có cấu trúc, nhưng phương pháp phụ thuộc vào bước trích xuất bộ ba và không cung cấp bằng chứng văn bản cho người dùng.

**Công trình thứ hai, SemViQA,** gắn kết việc chọn bằng chứng với phân loại ba nhãn, đạt strict accuracy 80,82%. Tuy nhiên, hệ thống chỉ chọn bằng chứng trong ngữ cảnh có sẵn, chưa truy xuất trên toàn kho tài liệu và còn yếu khi cần nhiều bằng chứng.

**Công trình thứ ba, ViFactCheck,** đóng góp 7.232 nhận định tin tức trên 12 chủ đề với quy trình chú thích chặt chẽ. Nhưng nguồn là tin tức với phạm vi thời gian hẹp, và kết quả tốt nhất dùng bằng chứng chuẩn nên chưa phản ánh hiệu quả đầu-cuối.

**Khoảng trống mà đề tài giải quyết** là kết hợp cả ba yếu tố: nguồn sách giáo khoa được kiểm soát, truy xuất trên toàn kho tài liệu, và đầu ra đầy đủ gồm nhãn, bằng chứng và lời giải thích có thể truy vết.

---

## Slide 7: Phương pháp đề xuất (slide chuyển tiếp)

Tiếp theo, em xin trình bày phương pháp đề xuất của khóa luận: **Facet Graph RAG** — với ba ý tưởng cốt lõi: truy xuất theo hai kênh song song, hợp nhất theo nguyên tắc bổ sung, và kiểm chứng dựa hoàn toàn trên bằng chứng.

---

## Slide 8: Kiến trúc tổng thể

Hệ thống được tổ chức thành hai pha.

**Pha lập chỉ mục** chỉ chạy một lần: sách giáo khoa lớp 10 đến 12 được OCR, làm sạch và phân đoạn theo đề mục, sau đó xây dựng đồng thời chỉ mục BM25, chỉ mục véc-tơ BGE-M3, và lớp đồ thị tri thức kèm từ điển bí danh với chỉ mục thời gian.

**Pha suy luận** chạy cho từng nhận định: nhận định được phân rã thành chín khía cạnh, rồi đi qua hai kênh truy xuất — kênh văn bản và kênh đồ thị. Kết quả hai kênh được hợp nhất theo cơ chế 5 cộng 3 và cắt theo cửa sổ liên quan, cuối cùng đưa vào bộ kiểm chứng để trả về nhãn, độ tin cậy, trích dẫn, khía cạnh sai và lời giải thích.

Việc tách hai pha giúp phần xử lý tốn kém trên toàn kho chỉ làm một lần, đồng thời cho phép đánh giá và gỡ lỗi từng tầng độc lập.

---

## Slide 9: Xây dựng bộ dữ liệu

Về dữ liệu, chúng em hợp nhất hai nguồn theo hai nhánh song song.

Nhánh thứ nhất sinh nhận định trực tiếp từ nội dung sách giáo khoa; nhánh thứ hai chuyển các câu hỏi trắc nghiệm của bộ đề thi VNHSGE thành câu khẳng định hoàn chỉnh. Nhận định sai được tạo bằng năm loại biến đổi có chủ đích, như thay đổi số liệu, hoán đổi thực thể hay đảo ngược diễn biến.

Toàn bộ dữ liệu sau đó được **kiểm định bằng biểu quyết đa mô hình**: ba mô hình Llama, Qwen và Gemini đánh giá mù độc lập từng mẫu, lấy đồng thuận 2 trên 3, các trường hợp bất đồng được rà soát thủ công. Cuối cùng, sau khi kiểm tra trường bắt buộc, loại trùng lặp và xung đột nhãn, bộ dữ liệu còn **11.344 nhận định** với **2.051 chủ đề duy nhất**, trong đó 3.887 mẫu từ sách giáo khoa chiếm khoảng 34%, và 7.457 mẫu từ VNHSGE chiếm khoảng 66%.

---

## Slide 10: Cơ sở tri thức hai lớp

Cơ sở tri thức của hệ thống gồm hai lớp bổ trợ cho nhau.

**Lớp văn bản** giữ nội dung nguyên bản để trích dẫn: từ 591 tệp OCR, chúng em giữ lại 571 trang hợp lệ và tạo ra 540 đoạn văn phân theo đề mục, được lập chỉ mục bằng cả BM25 và BGE-M3.

**Lớp đồ thị** cung cấp tín hiệu có cấu trúc: 3.599 thực thể đã chuẩn hóa thuộc sáu loại, 4.867 quan hệ có kiểu, tổng cộng 10.729 cạnh. Việc hợp nhất thực thể xử lý các cách gọi khác nhau, ví dụ "Mỹ", "Mĩ", "Hoa Kỳ" hay "Nguyễn Ái Quốc" với "Hồ Chí Minh".

Điểm quan trọng nhất: **mọi quan hệ trong đồ thị đều lưu source_chunk và evidence_text**, nghĩa là bất kỳ dữ kiện nào tìm được qua đồ thị đều truy vết được về đúng đoạn sách giáo khoa gốc. Đây là điều kiện để đầu ra của hệ thống luôn có căn cứ kiểm tra được.

---

## Slide 11: Truy xuất và giải thích

Đây là trái tim của phương pháp, với nguyên tắc thiết kế: **đồ thị bổ sung phần văn bản bỏ sót, chứ không thay thế**.

**Kênh văn bản** dùng câu nhận định nguyên bản làm truy vấn, kết hợp BM25 với BGE-M3 rồi hợp nhất bằng Reciprocal Rank Fusion với k bằng 60, giữ lại 5 đoạn tốt nhất.

**Kênh đồ thị** hoạt động qua phân rã khía cạnh: mỗi nhận định được tách thành chín loại khía cạnh — nhân vật, tổ chức, sự kiện, địa điểm, thời gian, khái niệm, số lượng, hành động và kết quả. Các khía cạnh được khớp vào nút đồ thị qua bí danh, cụm con và chỉ mục năm, từ đó thu thập và chấm điểm các đoạn ứng viên, bổ sung tối đa 3 đoạn.

**Bước hợp nhất 5 cộng 3** khử trùng lặp, và mỗi đoạn dài được cắt bằng kỹ thuật smart crop: chọn cửa sổ 1.400 ký tự liên quan nhất với nhận định thay vì cắt máy móc phần đầu đoạn.

Cuối cùng, bộ kiểm chứng chỉ được phép suy luận trên bằng chứng đã cung cấp, và trả về JSON gồm nhãn, độ tin cậy, ID bằng chứng trích dẫn, danh sách khía cạnh sai, và lời giải thích ngắn.

---

## Slide 12: Thực nghiệm và kết quả (slide chuyển tiếp)

Phần tiếp theo, em xin trình bày thực nghiệm, gồm thiết lập dữ liệu, tiêu chí đánh giá, so sánh với baseline, ablation study và thảo luận.

---

## Slide 13: Thiết lập và cách đánh giá

Chúng em đánh giá **tách theo từng tầng**: truy xuất, phân loại và cấu trúc lời giải thích được đo độc lập.

Về **dữ liệu**: có hai tập đánh giá — tập cân bằng 2.000 nhận định với 1.000 đúng, 1.000 sai để so sánh các phương pháp trong cùng điều kiện; và tập đầy đủ 11.344 nhận định để báo cáo kết quả cuối. Kho tham chiếu là 540 đoạn sách giáo khoa.

Về **baseline**: trên tập cân bằng, chúng em so sánh với truy xuất Dense, BM25 và Hybrid; trên tập đầy đủ bổ sung thêm LLM-only và RAG truyền thống. Ngoài ra có cấu hình Oracle dùng bằng chứng chuẩn trên 500 mẫu để ước lượng cận trên của bộ kiểm chứng.

Về **tiêu chí**: tầng truy xuất đo bằng evidence hit rate; tầng phân loại đo bằng accuracy, macro F1 và precision/recall từng nhãn, kèm kiểm định McNemar cho các so sánh cặp; tầng giải thích đo tỷ lệ trích dẫn, tính hợp lệ của ID và việc chỉ ra khía cạnh sai.

---

## Slide 14: Kết quả truy xuất

Kết quả truy xuất cho thấy một đặc trưng rõ của miền lịch sử: **tên riêng và niên đại khiến tín hiệu từ vựng giữ vai trò chủ đạo**.

BM25 đạt 90,1%, vượt truy xuất Dense tới **7,7 điểm**. Hybrid chỉ nhỉnh hơn BM25 có 0,4 điểm, xác nhận rằng biểu diễn ngữ nghĩa không thay thế được từ khóa định danh trong miền này.

Kênh đồ thị nâng thêm 0,8 điểm so với Hybrid, giúp hệ thống đề xuất đạt **91,3% evidence hit rate với 8 bằng chứng** — mức cao nhất trong các cấu hình khảo sát. Con số này đúng với vai trò thiết kế của kênh đồ thị: bổ sung những đoạn mà truy xuất văn bản bỏ sót.

---

## Slide 15: So sánh với baseline

Về kết quả phân loại, trên **tập đầy đủ 11.344 nhận định**, hệ thống đề xuất đứng đầu cả sáu cấu hình với **82,65% accuracy** và **80,32% macro F1**. Xin lưu ý mức nền của tập này là 69% do phân bố nhãn lệch, nên chúng em luôn báo cáo kèm macro F1.

So với Hybrid — baseline mạnh nhất cùng loại — hệ thống cao hơn 0,77 điểm accuracy và 0,56 điểm F1. So với LLM-only chỉ đạt 77,97%, kết quả cho thấy truy xuất bằng chứng đóng góp gần 5 điểm accuracy.

Trên **tập cân bằng**, hệ thống đạt **88,10%** cả accuracy lẫn F1, cũng là mức cao nhất trong bốn cấu hình. Chênh lệch giữa hai tập chủ yếu do nhóm nhận định chuyển thể từ đề thi — chiếm 66% tập đầy đủ — diễn đạt khác xa văn bản gốc nên khó truy xuất hơn.

---

## Slide 16: Ablation study và thảo luận

Phần phân tích thành phần cho chúng em ba phát hiện quan trọng.

**Phát hiện lớn nhất: cách trình bày bằng chứng quan trọng ngang chất lượng truy xuất.** Cấu hình ban đầu cắt cứng 650 ký tự đầu mỗi đoạn chỉ đạt 71,70% accuracy, vì trong 34% trường hợp, bằng chứng đã truy xuất đúng nhưng phần chứa thông tin quyết định lại bị cắt bỏ. Sau hai nhóm cải tiến — tăng ngân sách bằng chứng và cắt theo cửa sổ liên quan — accuracy tăng **16,40 điểm**, lên 88,10%.

**Thứ hai, về kênh đồ thị:** so sánh cặp trên 2.000 nhận định, kênh đồ thị cải thiện ròng 21 trường hợp, với p bằng 0,078 — chưa đạt ý nghĩa thống kê. Điều này cho thấy đồ thị đóng vai trò bổ trợ có điều kiện: giúp ích khi văn bản thiếu, nhưng có thể gây nhiễu khi bổ sung đoạn đúng chủ đề mà thiếu chi tiết quyết định.

**Thứ ba, nút thắt mới là distractor:** cấu hình Oracle đạt 99,8%, nhưng ngay cả khi bằng chứng đúng đã nằm trong ngữ cảnh, accuracy chỉ đạt khoảng 85%. Khoảng cách này đến từ các đoạn gây nhiễu đi kèm — và đây chính là hướng cải tiến ưu tiên tiếp theo.

---

## Slide 17: Kết luận và hướng phát triển

Tổng kết lại, khóa luận đã **hoàn thành cả ba mục tiêu** đặt ra, với các kết quả chính:

- Bộ dữ liệu 11.344 nhận định có nhãn và bằng chứng tham chiếu;
- Cơ sở tri thức hai lớp trong đó mọi dữ kiện đều truy vết được về sách giáo khoa;
- 91,3% evidence hit rate và 88,10% accuracy trên tập cân bằng;
- 82,65% accuracy và 80,32% macro F1 trên tập đầy đủ;
- 98,5% kết quả có toàn bộ trích dẫn hợp lệ.

Về **hướng phát triển**, chúng em sắp xếp theo mức tác động, bám trực tiếp vào các nút thắt đã định lượng:

Một, phân đoạn chồng lấn và hiệu đính OCR để khắc phục khoảng 10% tổn thất cấu trúc kho tài liệu. Hai, thêm tầng tinh lọc bằng chứng nhằm thu hẹp khoảng cách từ 85% lên mức 99,8% của cấu hình Oracle. Ba, hợp nhất thích ứng — chỉ kích hoạt kênh đồ thị khi tín hiệu văn bản yếu. Và bốn, mở rộng nhãn "không đủ thông tin" cùng đánh giá thủ công chất lượng lời giải thích.

Đóng góp cốt lõi của đề tài là một quy trình kiểm chứng **có thể đo lường được ở từng tầng**, và cho phép người học đối chiếu mọi kết luận với sách giáo khoa.

---

## Slide 18: Cảm ơn

Bài trình bày của chúng em đến đây là kết thúc. Chúng em xin chân thành cảm ơn Quý Thầy Cô đã lắng nghe, và rất mong nhận được các câu hỏi, góp ý của Hội đồng để hoàn thiện đề tài. Em xin cảm ơn ạ.

---

## Ghi chú phân bổ thời gian (tham khảo)

| Phần | Slide | Thời gian |
| --- | --- | --- |
| Mở đầu + giới thiệu bài toán | 1-3 | ~2 phút |
| Thử thách + đóng góp | 4-5 | ~2 phút |
| Nghiên cứu liên quan | 6 | ~1,5 phút |
| Phương pháp đề xuất | 7-11 | ~6 phút |
| Thực nghiệm | 12-16 | ~5 phút |
| Kết luận + cảm ơn | 17-18 | ~2 phút |
