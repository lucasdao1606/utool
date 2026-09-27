import streamlit as st
import io
import mimetypes
from tools.tool_gdrive_secure.src.utils.config import MAX_FILE_SIZE_MB
from tools.tool_gdrive_secure.src.api.drive_service import upload_to_drive
from tools.tool_gdrive_secure.src.utils.crypto_utils import encrypt_data

def render_upload_section():
    st.header("Tải Dữ Liệu Lên Google Drive ☁️")
    st.markdown(f"Hỗ trợ: **Tất cả các định dạng file**. Tối đa **{MAX_FILE_SIZE_MB}MB**.")
    
    # Gỡ bỏ giới hạn type=['csv', 'txt'...] để cho phép up mọi định dạng
    uploaded_file = st.file_uploader("Chọn file từ máy tính")
    
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
                    
                    # 4. Tự động dự đoán mimetype dựa trên tên file
                    file_mimetype, _ = mimetypes.guess_type(uploaded_file.name)
                    if file_mimetype is None:
                        file_mimetype = 'application/octet-stream' # Kiểu nhị phân mặc định
                    
                    # Đổi tên file để dễ nhận biết (thêm đuôi .enc)
                    secure_filename = f"{uploaded_file.name}.enc"
                    
                    # 5. Tải file đã mã hóa lên Google Drive (cần đảm bảo hàm upload_to_drive hỗ trợ nhận mimetype)
                    # Lưu ý: Nếu hàm upload_to_drive của bạn chưa có tham số mimetype, 
                    # hãy cứ để chạy thử nghiệm nghiệm. Tôi sẽ cập nhật nếu cần.
                    file_id = upload_to_drive(file_io, secure_filename, mimetype=file_mimetype)
                    
                    st.success(f"Tải lên thành công! ID file: `{file_id}`")
                    st.info("File trên Drive hiện là một khối dữ liệu mã hóa (.enc). Không ai có thể mở hay xem trước nội dung trực tiếp trên nền tảng web của Google.")
                except TypeError:
                    # Fallback trong trường hợp hàm upload_to_drive cũ không hỗ trợ tham số mimetype
                    file_id = upload_to_drive(file_io, secure_filename)
                    st.success(f"Tải lên thành công! ID file: `{file_id}`")
                    st.info("File trên Drive hiện là một khối dữ liệu mã hóa (.enc).")
                except Exception as e:
                    st.error(f"Lỗi hệ thống: {e}")