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
