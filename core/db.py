import os
import sqlite3
import bcrypt
import pyotp
import qrcode
import io
import base64
import random
import string
from datetime import datetime, timedelta

# Lưu database ở thư mục core/
current_dir = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(current_dir, 'utool_global.db')

# CẤU HÌNH GIỚI HẠN: Số người dùng đồng thời tối đa VPS có thể chịu tải
MAX_CONCURRENT_USERS = 3
SESSION_TIMEOUT_MINUTES = 30 

def init_db():
    conn = sqlite3.connect(DB_FILE, timeout=5.0)
    c = conn.cursor()
    # Bảng người dùng
    c.execute('''CREATE TABLE IF NOT EXISTS users (email TEXT PRIMARY KEY, password_hash TEXT)''')
    
    # Kiểm tra và thêm cột totp_secret cho 2FA (nếu DB cũ chưa có)
    c.execute("PRAGMA table_info(users)")
    columns = [info[1] for info in c.fetchall()]
    if 'totp_secret' not in columns:
        c.execute("ALTER TABLE users ADD COLUMN totp_secret TEXT")
        
    # Bảng quản lý phiên (Session)
    c.execute('''CREATE TABLE IF NOT EXISTS active_sessions (session_id TEXT PRIMARY KEY, email TEXT, last_seen TIMESTAMP)''')
    
    # Bảng quản lý mã OTP khôi phục mật khẩu
    c.execute('''CREATE TABLE IF NOT EXISTS password_resets (email TEXT PRIMARY KEY, otp TEXT, expires_at TIMESTAMP)''')
    
    conn.commit()
    conn.close()

def add_user(email, password):
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    conn = sqlite3.connect(DB_FILE, timeout=5.0)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)", (email, hashed))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def verify_user(email, password):
    conn = sqlite3.connect(DB_FILE, timeout=5.0)
    c = conn.cursor()
    c.execute("SELECT password_hash FROM users WHERE email=?", (email,))
    row = c.fetchone()
    conn.close()
    if row:
        return bcrypt.checkpw(password.encode('utf-8'), row[0])
    return False

# =====================================================================
# CÁC HÀM ĐỔI VÀ KHÔI PHỤC MẬT KHẨU
# =====================================================================

def update_password(email, new_password):
    """Cập nhật mật khẩu mới cho người dùng."""
    hashed = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
    conn = sqlite3.connect(DB_FILE, timeout=5.0)
    c = conn.cursor()
    c.execute("UPDATE users SET password_hash=? WHERE email=?", (hashed, email))
    conn.commit()
    conn.close()

def generate_and_save_reset_otp(email):
    """Tạo mã OTP 6 số ngẫu nhiên và lưu vào DB với hạn 15 phút."""
    otp = ''.join(random.choices(string.digits, k=6))
    expires_at = datetime.now() + timedelta(minutes=15)
    
    conn = sqlite3.connect(DB_FILE, timeout=5.0)
    c = conn.cursor()
    # Kiểm tra email có tồn tại không
    c.execute("SELECT email FROM users WHERE email=?", (email,))
    if not c.fetchone():
        conn.close()
        return None
        
    c.execute("REPLACE INTO password_resets (email, otp, expires_at) VALUES (?, ?, ?)", (email, otp, expires_at))
    conn.commit()
    conn.close()
    return otp

def verify_reset_otp(email, otp):
    """Kiểm tra mã OTP hợp lệ và chưa hết hạn."""
    conn = sqlite3.connect(DB_FILE, timeout=5.0)
    c = conn.cursor()
    c.execute("SELECT otp, expires_at FROM password_resets WHERE email=?", (email,))
    row = c.fetchone()
    conn.close()
    
    if row:
        stored_otp, expires_at = row
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        if stored_otp == otp and datetime.now() <= expires_at:
            return True
    return False

def clear_reset_otp(email):
    """Xóa mã OTP sau khi sử dụng thành công."""
    conn = sqlite3.connect(DB_FILE, timeout=5.0)
    c = conn.cursor()
    c.execute("DELETE FROM password_resets WHERE email=?", (email,))
    conn.commit()
    conn.close()

# =====================================================================
# CÁC HÀM XỬ LÝ 2FA (AUTHY / GOOGLE AUTHENTICATOR)
# =====================================================================

def generate_totp_secret():
    """Tạo ra một mã bí mật Base32 ngẫu nhiên cho tài khoản."""
    return pyotp.random_base32()

def get_totp_qr_code_base64(email, secret_key):
    """Tạo mã QR code chứa uri cấu hình TOTP và trả về chuỗi Base64 để hiển thị trên web."""
    totp_uri = pyotp.totp.TOTP(secret_key).provisioning_uri(
        name=email,
        issuer_name="Utool Technical Auditor"
    )
    img = qrcode.make(totp_uri)
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()

def set_user_totp_secret(email, secret_key):
    """Lưu mã bí mật TOTP vào cơ sở dữ liệu cho người dùng."""
    conn = sqlite3.connect(DB_FILE, timeout=5.0)
    c = conn.cursor()
    c.execute("UPDATE users SET totp_secret=? WHERE email=?", (secret_key, email))
    conn.commit()
    conn.close()

def get_user_totp_secret(email):
    """Lấy mã bí mật TOTP của người dùng từ cơ sở dữ liệu."""
    conn = sqlite3.connect(DB_FILE, timeout=5.0)
    c = conn.cursor()
    c.execute("SELECT totp_secret FROM users WHERE email=?", (email,))
    row = c.fetchone()
    conn.close()
    if row and row[0]:
        return row[0]
    return None

def verify_totp(secret_key, otp_code):
    """Xác thực mã 6 số nhập vào có khớp với mã sinh ra từ secret_key hay không."""
    totp = pyotp.TOTP(secret_key)
    return totp.verify(otp_code)

# =====================================================================
# CÁC HÀM QUẢN LÝ TẢI TRỌNG (CONCURRENCY)
# =====================================================================

def cleanup_stale_sessions():
    """Xóa các phiên đăng nhập đã đóng trình duyệt hoặc treo quá thời gian quy định."""
    conn = sqlite3.connect(DB_FILE, timeout=5.0)
    c = conn.cursor()
    timeout_threshold = datetime.now() - timedelta(minutes=SESSION_TIMEOUT_MINUTES)
    c.execute("DELETE FROM active_sessions WHERE last_seen < ?", (timeout_threshold,))
    conn.commit()
    conn.close()

def get_active_users_count():
    """Đếm số người đang sử dụng hệ thống lúc này."""
    cleanup_stale_sessions()
    conn = sqlite3.connect(DB_FILE, timeout=5.0)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM active_sessions")
    count = c.fetchone()[0]
    conn.close()
    return count

def register_session(session_id, email):
    """Ghi nhận một phiên đăng nhập mới."""
    conn = sqlite3.connect(DB_FILE, timeout=5.0)
    c = conn.cursor()
    now = datetime.now()
    c.execute("REPLACE INTO active_sessions (session_id, email, last_seen) VALUES (?, ?, ?)", (session_id, email, now))
    conn.commit()
    conn.close()

def remove_session(session_id):
    """Xóa phiên khi người dùng chủ động bấm Đăng xuất."""
    conn = sqlite3.connect(DB_FILE, timeout=5.0)
    c = conn.cursor()
    c.execute("DELETE FROM active_sessions WHERE session_id=?", (session_id,))
    conn.commit()
    conn.close()

def keep_alive_session(session_id):
    """Gia hạn thời gian hoạt động mỗi khi người dùng thao tác trên web."""
    conn = sqlite3.connect(DB_FILE, timeout=5.0)
    c = conn.cursor()
    now = datetime.now()
    c.execute("UPDATE active_sessions SET last_seen=? WHERE session_id=?", (now, session_id))
    conn.commit()
    conn.close()