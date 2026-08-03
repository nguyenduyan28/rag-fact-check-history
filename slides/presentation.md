# Slide 1
- Xin chào thầy, hiện tại tụi em trình bày về hệ thống kiểm chứng văn b

# Slide 2
- Phần trình bày của tụi em sẽ có 7 phần <liệt kê>

# Slide 3
- Bài toán của tụi em là mình sẽ đưa vào 1 câu claim(nhận định) hệ thống sẽ dựa vào tri thức của lịch sử THPT(10, 11, 12) sau đó retrieve các văn bản và đưa vào LLM để đánh giá là câu này là đúng hay sai, cùng với bằng chứng và giải thích

# Slide 4
- Về thử thách của bài toán: hiện chỉ có các bộ dữ liệu như là MCQ thiếu đi các bộ dữ liệu lịch sử Việt Nam có label, evidence nên tụi em đã build 1 dataset từ sách giáo khoa lịch sử 10, 11, 12(bản 2006) và cần tìm ra được 1 kiến trúc có thể xử lí tốt được bài toán này

# Slide 5
- Hiện tại thì tụi em đã xây dựng được bộ dataset gồm 11,344 câu bao gồm real claim và fake claim có dãn dán và bằng chứng các đoạn liên quan và 1 đồ thị được tạo từ bộ dataset này, 1 kiến trúc xử lí dựa trên bộ dataset này

# Slide 6
- 3 hướng xử lí:

# Slide 7
- Tiếp theo là đến phần phương pháp đề xuất

# Slide 8
- Về kiến trúc tổng thể tụi em sẽ có 2 pha : 1 là tạo ra graph từ dataset, 2 là pha suy luận là kiến trúc chính của hệ thống hiện tại

# Slide 9
- Về cách xây dựng bộ dữ liệu: dataset của tụi em được xây dựng bởi 2 nguồn là sgk THPT và VNHSGE(bộ dữ liệu của cuộc thi dạng MCQ): SGK thì tụi em OCR ra rồi xử lí nhiễu trước dùng LLM để tạo ra các key sau đó từ các key này bỏ vào LLM để tạo ra các real claim và fake claim(fake claim được tạo ra từ real claim), còn MCQ thì chuyển câu hỏi thành đúng sai sẽ thu được 1 real và 3 fake. 
- Sau đó sẽ trộn hết lại với nhau và đưa vào notebooklm để sinh relevant của các đoạn dựa trên key(1 key là 1 relevant theo các real/fake tương ứng), rồi bỏ các claims relevant này vào 3 con LLM (LLAMA, QWEN, GEMINI) để voting và cuối cùng là lấy 10% xung đột của các con này để kiểm tra thử công ví dụ real real fake => real với độ chính xác là (87%??? không nhớ) => kiểm tra cuối trùng hay gì không => dataset golden
và dữ liệu hiện tại thu được có 11344 claims trong đó như biểu đồ là 69% fake và 31% real

# Slide 10
-  

# Slide 11
# Slide 12
# Slide 13
# Slide 14
# Slide 15
# Slide 16
# Slide 17
