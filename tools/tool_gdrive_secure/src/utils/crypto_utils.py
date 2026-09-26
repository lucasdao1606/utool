import streamlit as st
from cryptography.fernet import Fernet

def get_fernet():
    """Lấy khóa mã hóa từ secrets.toml và khởi tạo bộ mã hóa."""
    key = st.secrets["encryption"]["secret_key"].encode()
    return Fernet(key)

def encrypt_data(file_bytes):
    """Mã hóa dữ liệu bytes của file."""
    fernet = get_fernet()
    return fernet.encrypt(file_bytes)
  
def decrypt_data(encrypted_bytes):
    """Giải mã dữ liệu bằng khóa hiện tại."""
    fernet = get_fernet()
    # Nếu khóa sai hoặc dữ liệu bị hỏng, hàm này sẽ báo lỗi
    return fernet.decrypt(encrypted_bytes)