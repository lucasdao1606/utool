# Personal Toolbox Platform (Streamlit)

Nền tảng tích hợp các công cụ làm việc cá nhân, thiết kế theo kiến trúc module hóa độc lập, chuẩn layout tương tự VAM.

## Cấu trúc dự án
- `app.py`: Entry point chính quản lý router và navigation sidebar.
- `core/`: Các module dùng chung (DB, logger, config, secrets).
- `common/`: Giao diện chung (CSS styles, export CSV UTF-8 BOM, formatters).
- `tools/`: Mỗi tool là một thư mục con riêng biệt với `engine.py` (logic tính toán) và `view.py` (giao diện Streamlit).

## Hướng dẫn cài đặt & khởi chạy
```bash
# 1. Tạo môi trường ảo
python -m venv venv
source venv/bin/activate  # Trên Linux/macOS
# venv\Scripts\activate  # Trên Windows

# 2. Cài đặt thư viện
pip install -r requirements.txt

# 3. Tạo file secrets từ mẫu
cp .streamlit/secrets.toml.example .streamlit/secrets.toml

# 4. Khởi chạy app
streamlit run app.py
```
