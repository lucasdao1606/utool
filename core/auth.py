import streamlit as st
import uuid
from core.db import (
    verify_user, add_user, get_active_users_count, 
    MAX_CONCURRENT_USERS, register_session, remove_session, keep_alive_session
)

def global_auth_guard():
    """
    Hệ thống chốt chặn bảo mật và quản lý luồng.
    Trả về True nếu hợp lệ, chặn đứng mọi thứ (st.stop) nếu không hợp lệ.
    """
    # 1. Khởi tạo Session ID duy nhất cho trình duyệt này nếu chưa có
    if "utool_session_id" not in st.session_state:
        st.session_state.utool_session_id = str(uuid.uuid4())
        st.session_state.is_authenticated = False

    # 2. Xử lý trạng thái ĐÃ ĐĂNG NHẬP
    if st.session_state.is_authenticated:
        # Báo cáo với máy chủ là user này vẫn đang sống (click/chuyển tab)
        keep_alive_session(st.session_state.utool_session_id)
        
        st.sidebar.success(f"👤 {st.session_state.utool_user_email}")
        if st.sidebar.button("🚪 Đăng xuất", use_container_width=True):
            remove_session(st.session_state.utool_session_id)
            st.session_state.is_authenticated = False
            st.session_state.utool_user_email = ""
            st.rerun()
        return True

    # 3. Xử lý trạng thái CHƯA ĐĂNG NHẬP (Hiển thị Form)
    st.markdown("<h1 style='text-align: center;'>🛠️ UTOOL WORKSPACE</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Vui lòng đăng nhập để truy cập hệ thống công cụ.</p>", unsafe_allow_html=True)
    
    # Kiểm tra giới hạn tải của VPS ngay tại màn hình chờ
    active_count = get_active_users_count()
    if active_count >= MAX_CONCURRENT_USERS:
        st.error(f"⚠️ HỆ THỐNG ĐANG QUÁ TẢI. Hiện có {active_count}/{MAX_CONCURRENT_USERS} người dùng đang hoạt động.")
        st.warning("Để bảo vệ máy chủ VPS, đăng nhập tạm thời bị khóa. Vui lòng quay lại sau khoảng 10-15 phút khi có người dùng khác thoát ra.")
        st.stop() # Dừng vẽ giao diện tại đây, không cho phép nhập form

    # Nếu VPS còn trống chỗ, vẽ form đăng nhập
    tab1, tab2 = st.tabs(["🔐 Đăng nhập", "📝 Đăng ký"])
    
    with tab1:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Mật khẩu", type="password")
            if st.form_submit_button("Đăng nhập vào Hệ thống", type="primary", use_container_width=True):
                # Phải check lại count một lần nữa ngay lúc bấm nút (tránh việc nhiều người cùng bấm lúc form đang mở)
                if get_active_users_count() >= MAX_CONCURRENT_USERS:
                    st.error("Rất tiếc, đã có người khác vừa chiếm slot cuối cùng. Vui lòng thử lại sau.")
                elif verify_user(email, password):
                    st.session_state.is_authenticated = True
                    st.session_state.utool_user_email = email
                    register_session(st.session_state.utool_session_id, email)
                    st.rerun()
                else:
                    st.error("Sai email hoặc mật khẩu!")
                    
    with tab2:
        with st.form("register_form"):
            reg_email = st.text_input("Email")
            reg_password = st.text_input("Mật khẩu", type="password")
            if st.form_submit_button("Tạo tài khoản", use_container_width=True):
                if len(reg_password) < 6:
                    st.error("Mật khẩu phải từ 6 ký tự.")
                else:
                    if add_user(reg_email, reg_password):
                        st.success("Đăng ký thành công! Hãy chuyển sang tab Đăng nhập.")
                    else:
                        st.error("Email này đã tồn tại!")

    # Chặn không cho đoạn code phía sau (chứa công cụ) chạy khi chưa đăng nhập
    st.stop()