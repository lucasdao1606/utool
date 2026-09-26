import os
import pathlib

def create_project_structure():
    # 1. Định nghĩa cấu trúc thư mục
    directories = [
        ".streamlit",          # Chứa file cấu hình và secrets của Streamlit
        "src",                 # Thư mục chứa toàn bộ mã nguồn chính
        "src/api",             # Xử lý các kết nối API bên ngoài (Google Drive, Sheets...)
        "src/components",      # Các thành phần giao diện Streamlit (Sidebar, Forms, Charts...)
        "src/utils",           # Các hàm tiện ích (kiểm tra bảo mật, xử lý định dạng file...)
        "assets",              # Chứa tài nguyên tĩnh (hình ảnh, file css, logo...)
        "tests",               # Thư mục chứa code kiểm thử tự động (Unit tests)
    ]

    # 2. Định nghĩa các file cần thiết và nội dung mặc định
    files = {
        ".streamlit/secrets.toml": "# ĐIỀN KHÓA BẢO MẬT VÀO ĐÂY (KHÔNG PUSH FILE NÀY LÊN GIT)\n",
        ".streamlit/config.toml": "[theme]\nprimaryColor = '#F63366'\n",
        
        "src/__init__.py": "",
        "src/api/__init__.py": "",
        "src/api/drive_service.py": "# Code xử lý logic upload lên Google Drive đặt ở đây\n",
        
        "src/components/__init__.py": "",
        "src/components/sidebar.py": "# Code tạo sidebar và form nhập mật khẩu đặt ở đây\n",
        "src/components/upload_ui.py": "# Code tạo giao diện nút bấm upload đặt ở đây\n",
        
        "src/utils/__init__.py": "",
        "src/utils/security.py": "# Các hàm kiểm tra mật khẩu, giới hạn dung lượng file\n",
        
        "app.py": "# FILE CHẠY CHÍNH\nimport streamlit as st\nfrom src.components import sidebar\n\nst.set_page_config(page_title='Secure Drive Upload', layout='wide')\nst.title('Giao Diện Chính')\n",
        
        "requirements.txt": "streamlit\ngoogle-api-python-client\ngoogle-auth\ngoogle-auth-httplib2\ngoogle-auth-oauthlib\n",
        
        ".gitignore": ".streamlit/secrets.toml\n__pycache__/\n*.pyc\n.env\nvenv/\nenv/\n.DS_Store\n",
        
        "README.md": "# Secure Streamlit Drive Uploader\n\n## Cấu trúc thư mục\n- `app.py`: Điểm khởi chạy của ứng dụng.\n- `src/`: Mã nguồn logic và giao diện.\n"
    }

    print("🚀 Bắt đầu khởi tạo cấu trúc dự án...")

    # Tạo thư mục
    for directory in directories:
        pathlib.Path(directory).mkdir(parents=True, exist_ok=True)
        print(f"📁 Đã tạo thư mục: {directory}")

    # Tạo files
    for filepath, content in files.items():
        if not os.path.exists(filepath):
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"📄 Đã tạo file: {filepath}")
        else:
            print(f"⚠️ File đã tồn tại (bỏ qua): {filepath}")

    print("\n✅ Hoàn tất! Cấu trúc dự án chuyên nghiệp đã sẵn sàng.")
    print("👉 Hãy chạy lệnh: streamlit run app.py để kiểm tra.")

if __name__ == "__main__":
    create_project_structure()