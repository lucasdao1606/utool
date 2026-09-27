import streamlit as st
from core.db import (
    verify_user, add_user, 
    generate_and_save_reset_otp, verify_reset_otp, 
    update_password, clear_reset_otp
)
from core.mailer import send_reset_email

def global_auth_guard():
    if "utool_user_email" not in st.session_state:
        st.session_state.utool_user_email = ""
    if "auth_mode" not in st.session_state:
        st.session_state.auth_mode = "login" # Các trạng thái: 'login', 'register', 'forgot', 'reset'
        
    if st.session_state.utool_user_email:
        return # Đã đăng nhập thành công, cho phép đi tiếp vào app.py

    st.markdown("<h2 style='text-align: center;'>Utool Workspace</h2>", unsafe_allow_html=True)
    
    # Tạo khung hiển thị ở giữa màn hình
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        # ==========================================
        # 1. MÀN HÌNH ĐĂNG NHẬP
        # ==========================================
        if st.session_state.auth_mode == "login":
            st.subheader("Đăng nhập")
            with st.form("login_form"):
                email = st.text_input("Tài khoản / Email").strip()
                password = st.text_input("Mật khẩu", type="password")
                
                submitted_login = st.form_submit_button("Đăng nhập", type="primary", use_container_width=True)
                
                if submitted_login:
                    if verify_user(email, password):
                        st.session_state.utool_user_email = email
                        st.rerun()
                    else:
                        st.error("❌ Sai tài khoản hoặc mật khẩu!")
                        
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Đăng ký tài khoản", use_container_width=True):
                    st.session_state.auth_mode = "register"
                    st.rerun()
            with c2:
                if st.button("Quên mật khẩu?", use_container_width=True):
                    st.session_state.auth_mode = "forgot"
                    st.rerun()

        # ==========================================
        # 2. MÀN HÌNH ĐĂNG KÝ (Xác nhận MK 2 lần)
        # ==========================================
        elif st.session_state.auth_mode == "register":
            st.subheader("Đăng ký tài khoản mới")
            with st.form("register_form"):
                reg_email = st.text_input("Email đăng ký").strip()
                reg_pw = st.text_input("Mật khẩu", type="password")
                reg_pw_confirm = st.text_input("Xác nhận lại mật khẩu", type="password")
                
                submitted_register = st.form_submit_button("Đăng ký", type="primary", use_container_width=True)
                
                if submitted_register:
                    if not reg_email or not reg_pw:
                        st.error("⚠️ Vui lòng điền đầy đủ thông tin!")
                    elif len(reg_pw) < 6:
                        st.error("⚠️ Mật khẩu phải từ 6 ký tự trở lên!")
                    elif reg_pw != reg_pw_confirm:
                        st.error("❌ Mật khẩu xác nhận không khớp!")
                    else:
                        if add_user(reg_email, reg_pw):
                            st.success("✅ Đăng ký thành công! Vui lòng đăng nhập.")
                            st.session_state.auth_mode = "login"
                            st.rerun()
                        else:
                            st.error("⚠️ Email này đã tồn tại trong hệ thống!")
                            
            if st.button("Quay lại Đăng nhập", use_container_width=True):
                st.session_state.auth_mode = "login"
                st.rerun()

        # ==========================================
        # 3. MÀN HÌNH QUÊN MẬT KHẨU (Gửi OTP)
        # ==========================================
        elif st.session_state.auth_mode == "forgot":
            st.subheader("Khôi phục mật khẩu")
            with st.form("forgot_form"):
                reset_email = st.text_input("Nhập email tài khoản của bạn:").strip()
                
                submitted_forgot = st.form_submit_button("Gửi mã OTP", type="primary", use_container_width=True)
                
                if submitted_forgot:
                    if not reset_email:
                        st.error("⚠️ Vui lòng nhập email!")
                    else:
                        otp = generate_and_save_reset_otp(reset_email)
                        if otp:
                            if send_reset_email(reset_email, otp):
                                st.session_state.reset_email_target = reset_email
                                st.session_state.auth_mode = "reset"
                                st.rerun()
                            else:
                                st.error("❌ Lỗi gửi email. Kiểm tra lại cấu hình SMTP.")
                        else:
                            st.error("⚠️ Email không tồn tại trong hệ thống!")
                            
            if st.button("Quay lại", use_container_width=True):
                st.session_state.auth_mode = "login"
                st.rerun()
                    
        # ==========================================
        # 4. MÀN HÌNH ĐẶT LẠI MẬT KHẨU (Nhập OTP)
        # ==========================================
        elif st.session_state.auth_mode == "reset":
            st.subheader("Đặt lại mật khẩu")
            target_email = st.session_state.get("reset_email_target", "")
            st.success(f"📧 Mã OTP đã được gửi đến: **{target_email}**")
            
            with st.form("reset_form"):
                otp_code = st.text_input("Mã OTP (6 số từ email):")
                new_pw = st.text_input("Mật khẩu mới:", type="password")
                new_pw_confirm = st.text_input("Xác nhận mật khẩu mới:", type="password")
                
                submitted_reset = st.form_submit_button("Đổi mật khẩu", type="primary", use_container_width=True)
                
                if submitted_reset:
                    if new_pw != new_pw_confirm:
                        st.error("❌ Mật khẩu xác nhận không khớp!")
                    elif len(new_pw) < 6:
                        st.error("⚠️ Mật khẩu phải từ 6 ký tự trở lên!")
                    elif verify_reset_otp(target_email, otp_code):
                        update_password(target_email, new_pw)
                        clear_reset_otp(target_email)
                        st.session_state.auth_mode = "login"
                        st.success("✅ Đổi mật khẩu thành công! Vui lòng đăng nhập lại.")
                        st.rerun()
                    else:
                        st.error("❌ Mã OTP không hợp lệ hoặc đã hết hạn!")
                        
            if st.button("Hủy bỏ", use_container_width=True):
                st.session_state.auth_mode = "login"
                st.rerun()

    # Dừng luồng Streamlit tại đây, chặn không cho render nội dung bên dưới (app.py)
    st.stop()