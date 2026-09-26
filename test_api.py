import os
import tomllib
from google import genai

def test_gemini_api():
    # 1. Tự động dò tìm và đọc file secrets.toml của Streamlit
    secrets_path = os.path.join(os.getcwd(), ".streamlit", "secrets.toml")
    
    if not os.path.exists(secrets_path):
        print(f"❌ Không tìm thấy file cấu hình tại: {secrets_path}")
        return
        
    try:
        with open(secrets_path, "rb") as f:
            secrets = tomllib.load(f)
            api_key = secrets.get("GEMINI_API_KEY")
            
        if not api_key:
            print("❌ File secrets.toml tồn tại nhưng không có biến GEMINI_API_KEY.")
            return
            
        # Ẩn bớt key để bảo mật khi in ra màn hình
        masked_key = f"{api_key[:8]}...{api_key[-4:]}"
        print(f"✅ Đã đọc thành công API Key: {masked_key}")
        
    except Exception as e:
        print(f"❌ Lỗi khi đọc file secrets.toml: {e}")
        return

    # 2. Bắt đầu test kết nối API
    try:
        print("🔄 Đang kết nối tới Google Gemini API...")
        client = genai.Client(api_key=api_key)
        
        # Kiểm tra danh sách model khả dụng
        print("\n🔍 Đang quét danh sách các Model khả dụng cho tài khoản này...")
        models = list(client.models.list())
        
        # Lọc ra các model có chữ 'flash'
        flash_models = [m.name for m in models if hasattr(m, 'name') and 'flash' in m.name.lower()]
        
        if flash_models:
            print(f"✅ Tài khoản của bạn được phép truy cập {len(flash_models)} model Flash:")
            for name in flash_models:
                print(f"  - {name}")
        else:
            print("⚠️ CẢNH BÁO: Tài khoản của bạn KHÔNG TÌM THẤY model Flash nào.")

        # Test năng lực sinh văn bản (chọn model chuẩn nhất hiện tại)
        test_model = 'gemini-1.5-flash'
        print(f"\n💬 Đang gửi tin nhắn thử nghiệm tới [{test_model}]...")
        
        response = client.models.generate_content(
            model=test_model,
            contents="Hãy trả lời ngắn gọn đúng 4 chữ: 'API hoạt động tốt'"
        )
        print(f"🎉 Phản hồi từ AI: {response.text.strip()}")
        
    except Exception as e:
        print(f"\n❌ LỖI KẾT NỐI API:\n{str(e)}")
        print("\n💡 GỢI Ý XỬ LÝ:")
        error_msg = str(e).lower()
        if "404" in error_msg:
            print("- Lỗi 404: Tên model không tồn tại hoặc tài khoản chưa được cấp quyền dùng model này.")
        elif "429" in error_msg or "quota" in error_msg:
            print("- Lỗi 429: API Key đã bị hết lượt sử dụng (Hết Quota) hoặc bạn đang gọi quá nhanh.")
        elif "400" in error_msg or "key" in error_msg:
            print("- Lỗi 400: API Key không hợp lệ. Hãy kiểm tra lại file secrets.toml.")

if __name__ == "__main__":
    test_gemini_api()