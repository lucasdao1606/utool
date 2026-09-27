import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import streamlit as st

def send_reset_email(to_email, otp_code):
    try:
        # Lấy thông tin từ section [email] trong secrets.toml
        email_conf = st.secrets["email"]
        smtp_user = email_conf["smtp_user"]
        smtp_password = email_conf["smtp_password"]
        
        # Mặc định sử dụng server của Gmail
        smtp_server = "smtp.gmail.com"
        smtp_port = 465

        msg = MIMEMultipart()
        msg['Subject'] = 'Khôi phục mật khẩu - Utool'
        msg['From'] = smtp_user
        msg['To'] = to_email

        body = f"""
Xin chào,

Bạn đã yêu cầu khôi phục mật khẩu trên hệ thống Utool.
Mã xác nhận (OTP) của bạn là: {otp_code}

Mã này có hiệu lực trong vòng 15 phút.
Nếu bạn không yêu cầu thay đổi mật khẩu, vui lòng bỏ qua email này.
        """
        msg.attach(MIMEText(body, 'plain'))

        # Kết nối và gửi email qua SSL
        server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        server.login(smtp_user, smtp_password)
        server.send_message(msg)
        server.quit()
        
        return True
    except Exception as e:
        print(f"Lỗi gửi mail: {e}")
        return False