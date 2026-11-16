# HƯỚNG DẪN SỬ DỤNG AI REPORT STUDIO

AI Report Studio là hệ thống phân tích dữ liệu và tự động tạo báo cáo tài chính theo mẫu, có AI hỗ trợ. Người dùng đăng nhập, tải tệp dữ liệu lên, phân tích, nhờ AI nhận xét rồi xuất báo cáo.

## Đăng ký và đăng nhập
- Đăng ký bằng họ tên, email và mật khẩu. Hệ thống gửi mã 6 số tới email để xác nhận trước khi tạo tài khoản (khi tính năng này được bật).
- Đăng nhập bằng email và mật khẩu, hoặc bằng nút "Tiếp tục với Google" nếu quản trị viên đã bật. Người dùng thường cũng nhập mã 6 số gửi qua email sau khi đúng mật khẩu hoặc sau khi qua Google.
- Mã xác nhận có hiệu lực 10 phút, dùng một lần, nhập sai 5 lần thì phải làm lại. Có thể bấm "Gửi lại mã" sau 60 giây.
- Quên mật khẩu: bấm "Quên mật khẩu" ở trang đăng nhập để nhận liên kết đặt lại qua email.
- Quản trị viên có thể bật xác thực hai bước (mã 6 số từ ứng dụng xác thực).
- Giao diện có chế độ sáng và tối, nút chuyển nằm trên thanh trên cùng.

## Các trang chính (menu bên trái)
- Tổng quan: bảng điều khiển với trạng thái dịch vụ, tệp và báo cáo gần đây, lối tắt sang các trang khác.
- Tải dữ liệu: tải tệp CSV hoặc Excel, kiểm tra chất lượng dữ liệu và ánh xạ cột trước khi phân tích. Dung lượng tối đa mỗi tệp do quản trị viên đặt trong Cài đặt (từ 1 đến 10 MB).
- Phân tích dữ liệu: thống kê mô tả, biểu đồ và mối liên hệ giữa các cột trong dữ liệu của bạn.
- Dự đoán và phân nhóm: chia khách hàng thành các nhóm theo thói quen mua, dự báo doanh thu, hoặc dự đoán một cột từ các cột khác. Trang hiển thị cả mức sai số của dự đoán để bạn biết nên tin đến đâu.
- Phân tích tài chính: đọc báo cáo tài chính (bảng cân đối kế toán, kết quả kinh doanh), tính các chỉ số, dự báo, chấm điểm sức khỏe tài chính, thử kịch bản (ví dụ doanh thu giảm 10%), so với ngành, so sánh hai kỳ hoặc hai tệp và kiểm tra số liệu có khớp nhau không. Các tab chính: Tổng quan, Bảng cân đối kế toán, Kết quả kinh doanh, Chỉ số tài chính, Phân tích lợi nhuận (DuPont), Biến động và cơ cấu, Dự báo, Sức khỏe tài chính, Thử kịch bản, So với ngành, So sánh kỳ hoặc tệp, Khớp khoản mục.
- AI nhận xét và gợi ý (gọi tắt là AI Studio): AI nhận xét báo cáo tài chính (điểm nổi bật, xu hướng, rủi ro, khuyến nghị) và trả lời câu hỏi về báo cáo của bạn.
- Mẫu báo cáo: chọn mẫu, chỉnh nhận xét rồi xuất hoặc chia sẻ.
- Lịch sử: xem lại các phân tích và báo cáo đã tạo, quản lý liên kết chia sẻ.
- Tài khoản: bấm vào tên hoặc ảnh ở góc phải trên cùng. Tại đây bạn đổi tên hiển thị, đổi hoặc gỡ ảnh đại diện, đổi mật khẩu, xem số thiết bị đang đăng nhập và đăng xuất các thiết bị khác, tải bản sao thông tin của mình, hoặc xóa tài khoản.
- Quản trị (chỉ quản trị viên): Người dùng, Nhật ký, Sao lưu, Cài đặt.

## Cách dùng từng bước (quy trình thường gặp)
1. Vào "Tải dữ liệu", chọn tệp CSV hoặc Excel (ví dụ báo cáo tài chính nhiều năm), kiểm tra bảng ánh xạ cột.
2. Vào "Phân tích tài chính" hoặc "Phân tích dữ liệu", chọn tệp và chạy phân tích. Hệ thống tự nhận diện các báo cáo tài chính trong tệp (bảng cân đối kế toán, kết quả kinh doanh, lưu chuyển tiền tệ).
3. Vào "AI nhận xét và gợi ý" để nhờ AI nhận xét hoặc đặt câu hỏi. Lần đầu bạn cần đồng ý gửi số liệu tổng hợp tới dịch vụ AI.
4. Vào "Mẫu báo cáo", chọn mẫu phù hợp, chỉnh nhận xét rồi xuất tệp.

## AI Studio và giới hạn
- AI chỉ diễn giải các số liệu mà hệ thống đã tính; số trong câu trả lời được đối chiếu với số liệu gốc, số nào không khớp sẽ được đánh dấu để bạn kiểm tra.
- Chỉ số liệu tổng hợp được gửi tới dịch vụ AI, không gửi toàn bộ dữ liệu thô. Câu trả lời của AI cần được người có chuyên môn kiểm tra trước khi dùng.
- Giới hạn mỗi người: 10 lần tạo nhận xét và 20 câu hỏi mỗi giờ, để bảo vệ hạn mức API.
- Nếu AI Studio báo chưa cấu hình, quản trị viên cần nhập khóa API trong Cài đặt.

## Mẫu báo cáo và xuất tệp
- Có các mẫu phân tích tài chính: tổng quan, thanh khoản, sinh lời, chất lượng số liệu.
- Có mẫu theo Thông tư 200/2014/TT-BTC (Bảng cân đối kế toán B01-DN, Báo cáo kết quả kinh doanh B02-DN) và theo Thông tư 133/2016/TT-BTC (Báo cáo kết quả kinh doanh B02-DNN). Mẫu theo thông tư lấy số liệu theo mã số trong tệp bạn tải lên; dòng thiếu nhưng có dòng con thì được tính lại và ghi chú "(tính lại)"; không có số liệu thì hiển thị "—". Các biểu mẫu này nên được đối chiếu với văn bản gốc trước khi nộp chính thức.
- Có thể chọn bật hoặc tắt từng phần của báo cáo.
- Xuất ra Word (.docx), PDF, Excel (.xlsx) hoặc PowerPoint (.pptx).
- Có thể chia sẻ báo cáo bằng liên kết với thời hạn 1, 7 hoặc 30 ngày và thu hồi liên kết bất cứ lúc nào trong "Lịch sử".
- Có thể đặt lịch gửi báo cáo qua email theo chu kỳ (khi quản trị viên đã cấu hình gửi email).

## Bảo mật và quyền riêng tư
- Dữ liệu của mỗi người dùng chỉ người đó xem được. Quản trị viên quản lý tài khoản nhưng không đọc nội dung tệp của người dùng qua giao diện này.
- Quản trị viên có thể đặt thời gian tự động xóa dữ liệu cũ trong Cài đặt.
- Đăng nhập sai nhiều lần sẽ bị tạm khóa để chống đoán mật khẩu.

## Cài đặt và quản trị (chỉ quản trị viên)
- Cài đặt: kết nối dịch vụ phân tích Python, khóa API và mô hình AI, gửi email (Brevo), đăng nhập bằng Google, các công tắc mã xác nhận qua email, thời gian lưu dữ liệu, dung lượng tải lên tối đa.
- Người dùng: xem danh sách tài khoản, khóa hoặc mở khóa.
- Nhật ký: xem thao tác và sự kiện bảo mật.
- Sao lưu: tạo, tải về và khôi phục bản sao lưu.

## Xử lý sự cố thường gặp
- Dịch vụ phân tích báo "đang khởi động" hoặc chậm ở lần đầu: dịch vụ chạy trên gói miễn phí nên tự ngủ khi lâu không dùng; chờ khoảng một phút rồi thử lại.
- Không nhận được email mã xác nhận: kiểm tra mục thư rác, chờ 60 giây rồi bấm "Gửi lại mã". Mỗi địa chỉ email nhận số thư có giới hạn mỗi giờ.
- Phân tích tài chính không nhận ra báo cáo: kiểm tra tệp có cột tên chỉ tiêu và các cột kỳ (năm hoặc quý), và xem bước ánh xạ cột ở "Tải dữ liệu".
- Báo cáo kiểm tra số liệu lệch: vào "Tài chính" xem mục kiểm tra, thường do tệp gốc nhập sai hoặc thiếu dòng.
- Quên mật khẩu hoặc tài khoản bị khóa: dùng "Quên mật khẩu" hoặc nhờ quản trị viên mở khóa.

## Trang Tài khoản
- Ảnh đại diện: nếu bạn đăng nhập bằng Google, hệ thống lấy ảnh Google của bạn làm ảnh đại diện. Bạn có thể bấm "Đổi ảnh" để tải ảnh riêng (JPEG, PNG, GIF hoặc WebP, tối đa 2 MB), bấm "Cập nhật từ Google" để lấy lại ảnh Google, hoặc "Gỡ ảnh" để quay về chữ cái đầu của tên. Khi bạn đã tự tải ảnh lên, ảnh Google sẽ không tự ghi đè.
- Tên hiển thị: từ 2 đến 60 ký tự. Email dùng để đăng nhập nên chưa đổi được tại trang này.
- Đổi mật khẩu: nhập mật khẩu hiện tại và mật khẩu mới (8–64 ký tự, gồm cả chữ và số). Sau khi đổi, các thiết bị khác bị đăng xuất và bạn nhận một email thông báo. Nhập sai mật khẩu hiện tại 5 lần thì phải chờ 15 phút.
- Tài khoản tạo bằng Google chưa có mật khẩu riêng. Muốn đặt mật khẩu, hãy đăng xuất, bấm "Quên mật khẩu" ở trang đăng nhập và làm theo email.
- Thiết bị đăng nhập: nút "Đăng xuất thiết bị khác" giữ lại thiết bị bạn đang dùng.
- Dữ liệu của bạn: "Tải bản sao thông tin (JSON)" xuất hồ sơ cùng danh sách tệp và báo cáo, không gồm nội dung tệp.
- Xóa tài khoản: mở mục "Xóa tài khoản", gõ đúng email (và mật khẩu nếu có) để xác nhận. Toàn bộ tệp, phân tích, báo cáo, liên kết chia sẻ và lịch gửi báo cáo bị xóa vĩnh viễn. Tài khoản quản trị viên không xóa được ở trang này.
