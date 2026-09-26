import os
import sys

# 1. Chặn paddlex/modelscope ngầm nạp torch gây lỗi DLL (shm.dll) trên Python 3.13
sys.modules['torch'] = None

# 2. Khóa OneDNN / MKLDNN và vô hiệu hóa PIR Compiler trước khi bất kỳ module nào khởi tạo Paddle
os.environ["FLAGS_use_mkldnn"] = "0"
os.environ["PADDLE_ONEDNN"] = "0"
os.environ["FLAGS_enable_pir_api"] = "0"
os.environ["FLAGS_enable_pir_in_executor"] = "0"

# 3. Giảm log verbose và tắt cảnh báo C++
os.environ["GLOG_minloglevel"] = "2"
os.environ["FLAGS_verbosity"] = "0"

import streamlit as st
from common.styles import apply_custom_styles
from tools.tool_docx_converter.view import render_docx_converter_tool
from tools.tool_stamp_pdf.view import render as render_stamp_pdf_tool
from tools.tool_checklist_pro.view import render_checklist_pro_tool
from tools.tool_bom_checker.view import render_bom_checker_tool
from tools.tool_pdf_to_word_ocr.view import render_pdf_to_word_tool
from tools.tool_spec_auditor.view import render_spec_auditor_tool
from tools.tool_gdrive_secure.view import render_gdrive_secure_tool

from core.db import init_db, get_active_users_count, MAX_CONCURRENT_USERS
from core.auth import global_auth_guard

st.set_page_config(
    page_title="Personal Toolbox",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ĐẶT EMAIL ADMIN CỦA BẠN TẠI ĐÂY
ADMIN_EMAIL = "phantichcrypto@gmail.com"

def main():
    apply_custom_styles()
    
    init_db()
    global_auth_guard()
    
    # Lấy email của người dùng đang đăng nhập hiện tại
    current_user_email = st.session_state.get("utool_user_email", "")
    
    st.sidebar.title("🎛️ Personal Toolbox")
    st.sidebar.caption("Workspace Platform")
    
    # 1. Danh sách công cụ cơ bản (Ai cũng thấy)
    tools_registry = {
        "📄 Chuyển đổi DOCX sang Excel": render_docx_converter_tool,
        "📑 Chuyển PDF/Scan sang Word (OCR)": render_pdf_to_word_tool,
        "📋 Checklist Pro (Đối soát tiêu chí)": render_checklist_pro_tool,
        "🔏 Đóng dấu giáp lai PDF": render_stamp_pdf_tool,
        "🔬 Đối soát Chỉ tiêu Kỹ thuật & Datasheet": render_spec_auditor_tool,
        "🔍 Kiểm tra nguồn hàng BOM": render_bom_checker_tool,
    }
    
    # 2. Phân quyền: Nếu đúng là Admin thì mới nhét thêm tool G-Drive vào menu
    if current_user_email == ADMIN_EMAIL:
        tools_registry["☁️ G-Drive Secure Box (Admin)"] = render_gdrive_secure_tool
    
    selected_tool = st.sidebar.radio(
        "Lựa chọn công cụ:",
        options=list(tools_registry.keys()),
        index=0
    )
    
    st.sidebar.divider()
    st.sidebar.markdown(f"**Tải trọng VPS:** ` {get_active_users_count()}/{MAX_CONCURRENT_USERS} ` 🟢")
    
    tools_registry[selected_tool]()

if __name__ == "__main__":
    main()