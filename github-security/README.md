# Quét bảo mật tự động trên GitHub

1. Chép thư mục `.github` này vào **gốc repo** (cùng cấp với thư mục `ai-report-service`), sửa đường dẫn `ai-report-service` trong hai tệp nếu repo của bạn tổ chức khác.
2. Đẩy lên GitHub (GitHub Desktop → Commit → Push).
3. Vào repo → tab **Actions** xem kết quả `security`; tab **Security → Dependabot** xem các đề xuất cập nhật.
4. Nếu gitleaks báo tìm thấy khóa: **đổi khóa đó ngay** (khóa Groq, khóa bí mật dùng chung), vì khóa đã vào lịch sử Git thì xóa tệp cũng không đủ.
5. Khuyến nghị: Settings → Code security → bật *Secret scanning* và *Push protection*.
