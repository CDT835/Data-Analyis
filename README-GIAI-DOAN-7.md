# AI Report Studio – Dịch vụ Python (bản 0.7.0, Giai đoạn 7)

Giai đoạn 7 bổ sung **mẫu báo cáo tài chính** và **xuất Word / PDF / Excel**. AI dùng **Groq** (không còn Gemini).

## Cài đặt thư viện mới
`requirements.txt` đã thêm `python-docx`, `reportlab`, `matplotlib`. Đẩy code lên GitHub, Render sẽ tự build lại (lần build đầu lâu hơn vì thư viện nặng hơn).

## API mới (đều ký HMAC như các API cũ)
| Phương thức | Đường dẫn | Việc làm |
|---|---|---|
| POST | `/api/v1/reports/templates` | Danh mục 4 mẫu và 18 phần, cho biết phần nào dùng được theo dữ liệu hiện có |
| POST | `/api/v1/reports/preview` | Dựng báo cáo dạng "khối" để xem trước |
| POST | `/api/v1/reports/export` | Xuất `docx`, `pdf` hoặc `xlsx` (trả base64) |

## 4 mẫu
- `fin_overview` – Báo cáo phân tích tài chính tổng hợp (18 phần)
- `fin_liquidity` – Thanh toán và cơ cấu vốn
- `fin_profitability` – Sinh lời và hiệu quả
- `fin_quality` – Chất lượng số liệu (cần kiểm tra lỗi gốc/hệ quả)

Phần nào thiếu dữ liệu (không có Bảng cân đối kế toán, chưa có nhận xét AI…) thì **tự bỏ qua kèm lý do**, không bịa số. Nhận xét AI dùng bản người dùng đã sửa (nếu có); ý có số chưa đối chiếu được sẽ có ghi chú.

## Kiểm thử
```
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q          # 76 test
```

---
# Bản 0.8.0: xuất báo cáo từ bản soạn thủ công
- `POST /api/v1/reports/render`: nhận danh sách khối do người dùng soạn (tiêu đề, đoạn văn, danh sách, lưu ý, bảng, biểu đồ), kiểm tra và làm sạch rồi xuất `docx`/`pdf`/`xlsx`.
- `POST /api/v1/reports/preview` có thêm `fragment: true`: chỉ trả khối của các phần đã chọn (không tiêu đề, không đánh số) để chèn vào bản soạn.
- Bảng tự nhập: cột toàn số căn phải, cột chữ căn trái.
- Test: `python -m pytest -q` (92 test).

## Bản 0.8.0 – xuất báo cáo soạn thủ công
- `POST /api/v1/reports/render`: nhận các khối do người dùng soạn, **kiểm tra và làm sạch** (loại khối lạ, giới hạn độ dài, số khối, số biểu đồ), tự đánh số tiêu đề rồi xuất `docx`/`pdf`/`xlsx`.
- `POST /api/v1/reports/preview` nhận thêm `fragment: true` để chỉ trả các khối của những phần đã chọn (dùng khi chèn từ dữ liệu vào bản soạn).
- Kiểm thử: `python -m pytest -q` (92 test).

## 0.20.0 — Bảo mật nhóm B

**Xoay khóa bí mật không gián đoạn.** Dịch vụ Python chấp nhận chữ ký của khóa hiện tại và khóa cũ trong lúc chuyển đổi:
1. Trên Render đặt `AIAR_SHARED_SECRET_PREVIOUS` = khóa cũ và `AIAR_SHARED_SECRET` = khóa mới, rồi để Render triển khai lại.
2. Trong plugin (Cài đặt hệ thống) lưu khóa mới.
3. Kiểm tra kết nối thành công, rồi xóa biến `AIAR_SHARED_SECRET_PREVIOUS` trên Render.

**Giới hạn tốc độ (Python).** `AIAR_RATE_PER_MIN` (mặc định 120 yêu cầu hợp lệ/phút, toàn dịch vụ) và `AIAR_AUTH_FAIL_PER_MIN` (mặc định 20 lần ký sai/phút mỗi IP, trả 429 kèm Retry-After). Bộ đếm nằm trong bộ nhớ nên mỗi lần dịch vụ khởi động lại sẽ đặt về 0 và chỉ áp dụng trong một tiến trình.

**Quét phụ thuộc và lộ khóa.** Thư mục `github-security/` có Dependabot, pip-audit và gitleaks; xem README trong thư mục đó. Lưu ý: chưa chạy pip-audit được trong môi trường phát triển (không truy cập được cơ sở dữ liệu lỗ hổng), nên chưa có kết quả quét.

**Xác thực hai bước (TOTP) cho quản trị viên** (plugin): bật trong Cài đặt hệ thống, nhập khóa thủ công vào Google Authenticator/Authy (chưa có mã QR), nhận 8 mã khôi phục dùng một lần. Đăng nhập thành hai bước; mã TOTP không dùng lại được trong cùng bước 30 giây; sai 5 lần thì hủy phiên chờ. Đăng nhập bằng mật khẩu ở wp-login.php/XML-RPC bị chặn với tài khoản đã bật 2FA. Chưa bao phủ mật khẩu ứng dụng (Application Passwords).

**Tự đăng xuất khi không hoạt động:** Cài đặt → Phiên đăng nhập (mặc định 120 phút, 0 = tắt), áp dụng cho các thao tác của plugin.

## 0.22.0 — Bảo mật nhóm D (dữ liệu gửi AI, thời gian lưu)

**Che dữ liệu nhận diện trước khi gửi sang Groq** (`app/services/privacy.py`, biến `AIAR_AI_MASK`, mặc định bật). Nội dung gửi Groq vốn chỉ gồm số liệu đã tính, nhãn kỳ và tên chỉ tiêu — không có tên tệp, tên người dùng hay nội dung thô của tệp. Lớp che là chốt chặn thêm: email, liên kết, số điện thoại, dãy từ 10 chữ số liền (mã số thuế, số tài khoản, CCCD) và cụm "Công ty/Ngân hàng/Tập đoàn…" kèm tên được thay bằng `[đã ẩn]`. Kết quả trả về có trường `masked` (số vị trí đã che). Các số tiền định dạng kiểu Việt Nam (1.234.567.890; 12,5%) không bị che. Giới hạn: tên công ty chỉ nhận dạng được khi đi sau các từ khóa trên; tên riêng đứng một mình trong nhãn dòng sẽ không bị che.

**Thời gian lưu dữ liệu** (plugin, Cài đặt → Thời gian lưu dữ liệu): tự xóa tệp tải lên, tệp đã làm sạch, kết quả phân tích, ML và nhận xét AI của tệp cũ hơn N ngày (0 = không tự xóa, mặc định). Báo cáo đã tạo được giữ. Chạy tối đa mỗi ngày một lần, kích hoạt khi có truy cập website (WP-Cron không cần thiết). Mỗi lần xóa ghi nhật ký `retention_purge`. Nhật ký hoạt động vẫn tự dọn sau 180 ngày.

## 0.23.0 — Nhóm A: phân tích nâng cao (dịch vụ Python)

Thêm `app/services/finance_ext.py` và các điểm vào `POST /api/v1/finance/forecast`, `/finance/health-score`, `/finance/scenario`, `POST /api/v1/ai/ask`. Dự báo dùng hồi quy tuyến tính (OLS) với khoảng dự đoán 80%, từ chối khi dưới 3 kỳ hoặc kỳ không cùng loại. Hỏi đáp dùng cùng cơ chế đối chiếu số và che dữ liệu như phần nhận xét. Có thêm 13 test (`tests/test_finance_ext.py`).
