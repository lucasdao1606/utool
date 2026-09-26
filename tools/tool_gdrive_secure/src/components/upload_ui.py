import streamlit as st
import io
from tools.tool_gdrive_secure.src.utils.config import MAX_FILE_SIZE_MB
from tools.tool_gdrive_secure.src.api.drive_service import upload_to_drive
from tools.tool_gdrive_secure.src.utils.crypto_utils import encrypt_data

def render_upload_section():
    st.header("Tải Dữ Liệu Lên Google Drive ☁️")
    st.markdown(f"Hỗ trợ: `csv`, `txt`, `pdf`, `png`, `jpg`. Tối đa **{MAX_FILE_SIZE_MB}MB**.")
    
    uploaded_file = st.file_uploader("Chọn file từ máy tính", type=['csv', 'txt', 'pdf', 'png', 'jpg'])
    
    if uploaded_file is not None:
        if uploaded_file.size > MAX_FILE_SIZE_MB * 1024 * 1024:
            st.error(f"File vượt quá dung lượng cho phép ({MAX_FILE_SIZE_MB}MB).")
            return
            
        if st.button("🚀 Mã hóa và Tải lên Drive", type="primary"):
            with st.spinner("Đang mã hóa AES và đẩy lên máy chủ..."):
                try:
                    # 1. Đọc nội dung file gốc
                    raw_bytes = uploaded_file.getvalue()
                    
                    # 2. Mã hóa toàn bộ nội dung file
                    encrypted_bytes = encrypt_data(raw_bytes)
                    
                    # 3. Đưa dữ liệu đã mã hóa vào luồng BytesIO
                    file_io = io.BytesIO(encrypted_bytes)
                    
                    # Đổi tên file để dễ nhận biết (thêm đuôi .enc)
                    secure_filename = f"{uploaded_file.name}.enc"
                    
                    # 4. Tải file đã mã hóa lên Google Drive
                    file_id = upload_to_drive(file_io, secure_filename)
                    
                    st.success(f"Tải lên thành công! ID file: `{file_id}`")
                    st.info("File trên Drive hiện là một khối dữ liệu mã hóa (.enc). Không ai có thể mở hay xem trước nội dung trực tiếp trên nền tảng web của Google.")
                except Exception as e:
                    st.error(f"Lỗi API: {e}")