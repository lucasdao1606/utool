import os
import sqlite3
import bcrypt
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
    # Bảng quản lý phiên (Session)
    c.execute('''CREATE TABLE IF NOT EXISTS active_sessions (session_id TEXT PRIMARY KEY, email TEXT, last_seen TIMESTAMP)''')
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

# --- CÁC HÀM QUẢN LÝ TẢI TRỌNG (CONCURRENCY) ---

def cleanup_stale_sessions():
    """Xóa các phiên đăng nhập đã đóng trình duyệt hoặc treo quá 30 phút."""
    conn = sqlite3.connect(DB_FILE, timeout=5.0)
    c = conn.cursor()
    timeout_threshold = datetime.now() - timedelta(minutes=SESSION_TIMEOUT_MINUTES)
    c.execute("DELETE FROM active_sessions WHERE last_seen < ?", (timeout_threshold,))
    conn.commit()
    conn.close()

def get_active_users_count():
    """Đếm số người đang sử dụng hệ thống lúc này."""
    cleanup_stale_sessions() # Dọn dẹp trước khi đếm cho chính xác
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