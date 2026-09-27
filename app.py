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

# Import các hàm xử lý 2FA và mật khẩu
from core.db import (
    init_db, get_active_users_count, MAX_CONCURRENT_USERS,
    get_user_totp_secret, generate_totp_secret, get_totp_qr_code_base64, 
    set_user_totp_secret, verify_totp, verify_user, update_password
)
from core.auth import global_auth_guard

st.set_page_config(
    page_title="Personal Toolbox",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ĐẶT EMAIL ADMIN CỦA BẠN TẠI ĐÂY
ADMIN_EMAIL = "phantichcrypto@gmail.com"

def render_2fa_verify_screen(email, existing_secret):
    """Màn hình chặn xác thực 2 lớp (Chỉ hiện khi Admin ĐÃ BẬT 2FA)."""
    st.subheader("🔒 Xác thực bảo mật 2 lớp (2FA)")
    st.info("Tài khoản của bạn đang được bảo vệ bởi 2FA. Vui lòng nhập mã OTP để vào hệ thống.")
    
    otp_input = st.text_input("Nhập mã 6 số từ ứng dụng Authy/Google Authenticator:")
    
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("Xác thực", type="primary", use_container_width=True):
            if verify_totp(existing_secret, otp_input):
                # Lưu xác thực gắn liền với phiên đăng nhập hiện tại
                st.session_state.admin_2fa_verified_for = email
                st.rerun()
            else:
                st.error("❌ Mã không hợp lệ hoặc đã hết hạn!")
    with col2:
        if st.button("Hủy & Đăng xuất", use_container_width=True):
            st.session_state.clear()
            st.rerun()

def render_2fa_setup_tool():
    """Giao diện Cài đặt 2FA (Chỉ dành cho Admin)."""
    st.subheader("🔐 Quản lý Bảo mật 2 lớp (2FA)")
    
    email = st.session_state.get("utool_user_email")
    existing_secret = get_user_totp_secret(email)
    
    if existing_secret:
        st.success("✅ Tính năng xác thực 2 bước (2FA) **ĐANG BẬT**.")
        st.warning("Hệ thống sẽ yêu cầu mã xác thực từ điện thoại mỗi khi bạn đăng nhập.")
        
        if st.button("Tắt tính năng 2FA", type="secondary"):
            set_user_totp_secret(email, None)
            st.session_state.pop("admin_2fa_verified_for", None) 
            st.success("Đã tắt 2FA! Tài khoản của bạn hiện chỉ được bảo vệ bằng mật khẩu.")
            st.rerun()
    else:
        st.info("⚠️ Tài khoản của bạn chưa bật 2FA. Nên thiết lập ngay để bảo vệ cấu hình hệ thống.")
        
        if "temp_secret" not in st.session_state:
            st.session_state.temp_secret = generate_totp_secret()
            
        st.markdown("### Hướng dẫn thiết lập:")
        st.markdown("1. Mở ứng dụng **Authy** hoặc **Google Authenticator** trên điện thoại.")
        st.markdown("2. Quét mã QR dưới đây:")
        
        qr_b64 = get_totp_qr_code_base64(email, st.session_state.temp_secret)
        st.markdown(
            f'<div style="margin: 20px 0;"><img src="data:image/png;base64,{qr_b64}" width="220" style="border: 2px solid #ddd; border-radius: 8px;"></div>', 
            unsafe_allow_html=True
        )
        st.markdown(f"*(Hoặc nhập mã thủ công: **`{st.session_state.temp_secret}`**)*")
        
        st.markdown("3. Nhập mã 6 số hiện trên ứng dụng để xác nhận kích hoạt:")
        otp_input = st.text_input("Mã xác nhận (6 số):", key="setup_otp")
        
        if st.button("Kích hoạt 2FA", type="primary"):
            if verify_totp(st.session_state.temp_secret, otp_input):
                set_user_totp_secret(email, st.session_state.temp_secret)
                st.success("🎉 Bật 2FA thành công! Cài đặt đã được lưu lại.")
                st.rerun()
            else:
                st.error("❌ Mã không hợp lệ, vui lòng kiểm tra lại!")

def render_change_password_tool(email):
    """Giao diện Đổi mật khẩu dành cho mọi User."""
    st.subheader("🔑 Đổi mật khẩu")
    old_pw = st.text_input("Mật khẩu hiện tại:", type="password")
    new_pw = st.text_input("Mật khẩu mới:", type="password")
    confirm_pw = st.text_input("Xác nhận mật khẩu mới:", type="password")
    
    if st.button("Lưu thay đổi", type="primary"):
        if not verify_user(email, old_pw):
            st.error("Mật khẩu hiện tại không chính xác!")
        elif new_pw != confirm_pw:
            st.error("Mật khẩu xác nhận không khớp!")
        elif len(new_pw) < 6:
            st.error("Mật khẩu mới phải có ít nhất 6 ký tự.")
        else:
            update_password(email, new_pw)
            st.success("Đổi mật khẩu thành công! Các lần đăng nhập sau vui lòng dùng mật khẩu mới.")

def reset_view_state():
    """Hàm tự động ẩn giao diện Cài đặt khi người dùng bấm chọn một Công cụ chính."""
    if "show_settings" in st.session_state:
        st.session_state.show_settings = None

def main():
    apply_custom_styles()
    init_db()
    
    # 1. Đăng nhập bằng mật khẩu như bình thường
    global_auth_guard()
    
    current_user_email = st.session_state.get("utool_user_email", "")
    
    # 2. BỘ CHẶN 2FA: Chỉ chạy đoạn này nếu người dùng đã vượt qua login và là Admin
    if current_user_email == ADMIN_EMAIL:
        existing_secret = get_user_totp_secret(current_user_email)
        if existing_secret and st.session_state.get("admin_2fa_verified_for") != current_user_email:
            render_2fa_verify_screen(current_user_email, existing_secret)
            st.stop() # Ẩn menu và ngăn không cho truy cập các công cụ
            
    # ==========================================================
    # KHU VỰC CÔNG CỤ & MENU (Chỉ load nếu không bị st.stop() ở trên)
    # ==========================================================
    st.sidebar.title("🎛️ Personal Toolbox")
    st.sidebar.caption("Workspace Platform")
    
    tools_registry = {
        "📄 Chuyển đổi DOCX sang Excel": render_docx_converter_tool,
        "📑 Chuyển PDF/Scan sang Word (OCR)": render_pdf_to_word_tool,
        "📋 Checklist Pro (Đối soát tiêu chí)": render_checklist_pro_tool,
        "🔏 Đóng dấu giáp lai PDF": render_stamp_pdf_tool,
        "🔬 Đối soát Chỉ tiêu Kỹ thuật & Datasheet": render_spec_auditor_tool,
        "🔍 Kiểm tra nguồn hàng BOM": render_bom_checker_tool,
    }
    
    if current_user_email == ADMIN_EMAIL:
        tools_registry["☁️ G-Drive Secure Box (Admin)"] = render_gdrive_secure_tool
    
    selected_tool = st.sidebar.radio(
        "Lựa chọn công cụ:",
        options=list(tools_registry.keys()),
        index=0,
        key="main_tools_radio",
        on_change=reset_view_state # Tự động thoát giao diện cài đặt khi chuyển tool
    )
    
    # ==========================================================
    # KHU VỰC CÀI ĐẶT HỆ THỐNG
    # ==========================================================
    st.sidebar.divider()
    st.sidebar.subheader("⚙️ Cài đặt hệ thống")
    
    # Nút đổi mật khẩu cho mọi User
    if st.sidebar.button("🔑 Đổi mật khẩu", use_container_width=True):
        st.session_state.show_settings = "change_password"
        
    # Nút 2FA riêng cho Admin
    if current_user_email == ADMIN_EMAIL:
        if st.sidebar.button("🔐 Quản lý Bảo mật (2FA)", use_container_width=True):
            st.session_state.show_settings = "2fa"
            
    st.sidebar.divider()
    st.sidebar.markdown(f"**Tải trọng VPS:** ` {get_active_users_count()}/{MAX_CONCURRENT_USERS} ` 🟢")
    
    # Nút Đăng xuất
    if st.sidebar.button("Đăng xuất", type="secondary", use_container_width=True):
        st.session_state.clear()
        st.rerun()
    
    # ==========================================================
    # ĐIỀU HƯỚNG HIỂN THỊ GIAO DIỆN CHÍNH
    # ==========================================================
    current_setting = st.session_state.get("show_settings")
    if current_setting == "2fa" and current_user_email == ADMIN_EMAIL:
        render_2fa_setup_tool()
    elif current_setting == "change_password":
        render_change_password_tool(current_user_email)
    else:
        # Hiển thị công cụ nghiệp vụ
        if selected_tool in tools_registry:
            tools_registry[selected_tool]()

if __name__ == "__main__":
    main()