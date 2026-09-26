import streamlit as st

# Chỉ import các module giao diện UI, đã gỡ bỏ db và auth do utool quản lý global
from tools.tool_gdrive_secure.src.components.upload_ui import render_upload_section
from tools.tool_gdrive_secure.src.components.download_ui import render_download_section

def render_gdrive_secure_tool():
    """Giao diện công cụ đã được gỡ bỏ lớp đăng nhập nội bộ"""
    st.title("G-Drive Secure Box ☁️")
    st.divider()
    
    # Cập nhật tiêu đề tab để phản ánh tính năng quản lý (xóa file)
    tab1, tab2 = st.tabs(["Tải lên & Mã hóa 🔒", "Quản lý & Tải về 🔓"])
    
    with tab1:
        render_upload_section()
        
    with tab2:
        render_download_section()