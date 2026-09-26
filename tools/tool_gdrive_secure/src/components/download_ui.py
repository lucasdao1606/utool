import streamlit as st
import pandas as pd
import io
import zipfile
from datetime import datetime
from tools.tool_gdrive_secure.src.api.drive_service import list_encrypted_files, download_from_drive, delete_from_drive
from tools.tool_gdrive_secure.src.utils.crypto_utils import decrypt_data

def format_size(size_bytes):
    """Chuyển đổi Byte sang KB, MB, GB cho dễ đọc."""
    if not size_bytes: return "0 B"
    size_bytes = int(size_bytes)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"

def format_date(date_str):
    """Định dạng lại chuỗi thời gian của Google."""
    if not date_str: return ""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%fZ")
        return dt.strftime("%d/%m/%Y %H:%M")
    except:
        return date_str

def render_download_section():
    st.header("🗂️ Trình Quản Lý Dữ Liệu")
    
    # Nút làm mới dữ liệu
    if st.button("🔄 Làm mới danh sách", key="refresh_btn"):
        st.rerun()
        
    files = list_encrypted_files()
    
    if not files:
        st.info("📂 Thư mục trống. Không có file mã hóa nào.")
        return

    # 1. Chuyển đổi dữ liệu API sang dạng Bảng (Pandas DataFrame)
    data = []
    for f in files:
        data.append({
            "Chọn": False,
            "ID": f.get("id"),
            "Tên File": f.get("name", "").replace(".enc", ""), # Ẩn đuôi .enc cho đẹp
            "Kích thước": format_size(f.get("size", 0)),
            "Ngày tạo": format_date(f.get("createdTime", ""))
        })
        
    df = pd.DataFrame(data)

    # 2. Hiển thị bảng Data Editor cho phép tick chọn
    edited_df = st.data_editor(
        df,
        column_config={
            "Chọn": st.column_config.CheckboxColumn("Chọn", default=False),
            "ID": None, # Ẩn cột ID hệ thống
            "Tên File": st.column_config.TextColumn("Tên File", disabled=True),
            "Kích thước": st.column_config.TextColumn("Kích thước", disabled=True),
            "Ngày tạo": st.column_config.TextColumn("Ngày tạo", disabled=True),
        },
        hide_index=True,
        use_container_width=True,
        key="file_manager_table"
    )

    # Lọc ra danh sách các file đang được tick
    selected_rows = edited_df[edited_df["Chọn"] == True]
    selected_ids = selected_rows["ID"].tolist()
    selected_names = selected_rows["Tên File"].tolist()
    
    # Reset trạng thái tải về nếu người dùng thay đổi lựa chọn tick
    current_selection_key = "-".join(selected_ids)
    if st.session_state.get("last_selection") != current_selection_key:
        st.session_state.ready_to_download = False
        st.session_state.confirm_delete_multiple = False
        st.session_state.last_selection = current_selection_key
        
    st.markdown(f"**Đã chọn:** `{len(selected_ids)}` tập tin")

    # 3. Hiển thị thanh Công cụ (Chỉ hiện khi có ít nhất 1 file được chọn)
    if len(selected_ids) > 0:
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("⬇️ Xử lý Tải về", use_container_width=True, type="primary"):
                with st.spinner("Đang kết nối Drive và giải mã dữ liệu..."):
                    try:
                        if len(selected_ids) == 1:
                            # Nếu chỉ chọn 1 file -> Trả về file gốc
                            enc_bytes = download_from_drive(selected_ids[0])
                            dec_bytes = decrypt_data(enc_bytes)
                            
                            st.session_state.download_data = dec_bytes
                            st.session_state.download_filename = selected_names[0]
                            st.session_state.download_mime = "application/octet-stream"
                        else:
                            # Nếu chọn nhiều file -> Đóng gói thành file ZIP
                            zip_buffer = io.BytesIO()
                            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                                for fid, fname in zip(selected_ids, selected_names):
                                    enc_bytes = download_from_drive(fid)
                                    dec_bytes = decrypt_data(enc_bytes)
                                    zip_file.writestr(fname, dec_bytes)
                                    
                            st.session_state.download_data = zip_buffer.getvalue()
                            st.session_state.download_filename = "Du_Lieu_Giai_Ma.zip"
                            st.session_state.download_mime = "application/zip"
                            
                        st.session_state.ready_to_download = True
                    except Exception as e:
                        st.error(f"Lỗi hệ thống: Khóa Secret Key không hợp lệ hoặc file bị hỏng.")
                        st.exception(e)
        
        with col2:
            if st.button("🗑️ Xóa đã chọn", use_container_width=True):
                st.session_state.confirm_delete_multiple = True

        # Render Nút Download thật sau khi dữ liệu đã sẵn sàng trên RAM
        if st.session_state.get("ready_to_download", False):
            st.success("✅ Dữ liệu đã sẵn sàng!")
            st.download_button(
                label=f"💾 Bấm để lưu: {st.session_state.download_filename}",
                data=st.session_state.download_data,
                file_name=st.session_state.download_filename,
                mime=st.session_state.download_mime,
                use_container_width=True,
                type="secondary"
            )

        # Render Giao diện Xác nhận Xóa hàng loạt
        if st.session_state.get("confirm_delete_multiple", False):
            st.warning(f"⚠️ Bạn có chắc chắn muốn xóa vĩnh viễn {len(selected_ids)} tập tin này?")
            c_yes, c_no = st.columns(2)
            with c_yes:
                if st.button("✅ Có, Xóa ngay", use_container_width=True, type="primary"):
                    with st.spinner("Đang ra lệnh xóa vĩnh viễn..."):
                        for fid in selected_ids:
                            delete_from_drive(fid)
                    st.success("Đã xóa hoàn tất!")
                    st.session_state.confirm_delete_multiple = False
                    st.session_state.ready_to_download = False
                    st.rerun()
            with c_no:
                if st.button("❌ Hủy thao tác", use_container_width=True):
                    st.session_state.confirm_delete_multiple = False
                    st.rerun()