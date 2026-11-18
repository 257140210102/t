2. Hướng dẫn chạy dự án theo đúng cấu trúc thư mục hiện tạiMở Terminal ngay trong VS Code (Ctrl + ~) tại thư mục chứa các tệp trên và thực hiện lần lượt 3 bước:   Bước 1: Khởi tạo cơ sở dữ liệu PostgreSQLTạo cơ sở dữ liệu tên edulms_pro trong PostgreSQL (qua pgAdmin hoặc psql), sau đó nạp bảng từ tệp schema.sql ở thư mục gốc:   
Bash
    psql -U postgres -c "CREATE DATABASE edulms_pro;"
    psql -U postgres -d edulms_pro -f schema.sql
Bước 2: Khởi chạy máy chủ Backend (main.py)Vì tệp main.py nằm ngay ở thư mục gốc (không nằm trong thư mục con backend/), bạn chạy lệnh sau:   
Bash
pip install fastapi uvicorn sqlalchemy psycopg2-binary pydantic python-jose[cryptography] bcrypt python-multipart google-genai
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
(Nếu dùng AI Gemini thật, chạy thêm set GEMINI_API_KEY=your_key trên Windows hoặc export GEMINI_API_KEY=your_key trên macOS/Linux trước khi chạy uvicorn).Bước 3: Mở giao diện Web Frontend (index.html)Mở một cửa sổ Terminal thứ hai (bấm dấu + ở góc phải panel Terminal) và chạy:
Bash
    python -m http.server 3000
Truy cập trình duyệt tại địa chỉ http://localhost:3000 để sử dụng hệ thống.
3. Lưu ý nhanh khi đăng nhập lần đầuChuỗi password_hash mẫu trong schema.sql chỉ là chuỗi minh họa. Để đặt mật khẩu 123456 chuẩn bcrypt cho tài khoản admin trong PostgreSQL, bạn chạy nhanh lệnh sau trong Terminal:
Bash
    python -c "import bcrypt; print(bcrypt.hashpw(b'123456', bcrypt.gensalt()).decode())"
Sau đó cập nhật chuỗi vừa in ra vào bảng users (UPDATE users SET password_hash = '<chuỗi_hash>' WHERE username = 'admin';) là có thể đăng nhập với tài khoản admin / 123456 và tạo thêm tài khoản Giáo viên, Học sinh ngay trên giao diện.

Hướng dẫn khởi chạy backend/main.py

Cài đặt thư viện phụ thuộc:

Bash
    pip install fastapi uvicorn sqlalchemy psycopg2-binary pydantic python-jose[cryptography] bcrypt python-multipart google-genai

Thiết lập biến môi trường & chạy máy chủ:

Bash
    export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/edulms_pro"
    export GEMINI_API_KEY="your_gemini_api_key"
    uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

