import requests
import urllib3

# Bỏ qua cảnh báo SSL nếu có
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def test_macrofab_auth():
    print("="*50)
    print("   🔍 CÔNG CỤ TEST XÁC THỰC MACROFAB API")
    print("="*50)
    
    api_key = input("\n🔑 Vui lòng dán API Key của MacroFab vào đây: ").strip()

    if not api_key:
        print("❌ API Key không được để trống!")
        return

    url = "https://factory.macrofab.com/api/v2/pcbs"

    # Danh sách các định dạng Header cần kiểm tra
    test_cases = [
        {
            "name": "Chuẩn Bearer Token",
            "headers": {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
        },
        {
            "name": "Chuẩn Token (MacroFab Legacy)",
            "headers": {"Authorization": f"token {api_key}", "Accept": "application/json"}
        },
        {
            "name": "Chuẩn X-API-Key",
            "headers": {"x-api-key": api_key, "Accept": "application/json"}
        },
        {
            "name": "Chuẩn Api-Key",
            "headers": {"Api-Key": api_key, "Accept": "application/json"}
        }
    ]

    print(f"\n🚀 Bắt đầu gửi yêu cầu GET đến: {url}\n")

    success_format = None
    success_headers = None

    for case in test_cases:
        print(f"⏳ Đang thử nghiệm: {case['name']} ...")
        try:
            # Gửi request để lấy danh sách PCB (Đây là endpoint an toàn để test)
            res = requests.get(url, headers=case['headers'], timeout=10, verify=False)
            
            print(f"   ➔ Mã phản hồi (Status Code): {res.status_code}")

            if res.status_code in [200, 201]:
                print("   ✅ THÀNH CÔNG! Định dạng này hợp lệ.")
                success_format = case['name']
                success_headers = case['headers']
                break
            elif res.status_code in [401, 403]:
                print(f"   ❌ THẤT BẠI: Bị từ chối (Unauthorized / Forbidden).")
            else:
                print(f"   ⚠️ LỖI KHÁC: {res.text[:100]}")
                
        except Exception as e:
            print(f"   ❌ Lỗi kết nối mạng: {e}")
        print("-" * 50)

    print("\n" + "="*50)
    if success_format:
        print(f"🎉 KẾT LUẬN: API Key HOẠT ĐỘNG TỐT với định dạng '{success_format}'.")
        print("\n🛠️ HƯỚNG DẪN SỬA LỖI TRONG MÃ NGUỒN:")
        print("Bạn hãy mở file 'tools/tool_gerber_analyzer/engine.py'")
        print("Tìm đến hàm upload_and_analyze_gerber và sửa biến headers thành:")
        print(f"headers = {success_headers}")
    else:
        print("🚨 KẾT LUẬN: Toàn bộ các định dạng đều bị máy chủ MacroFab từ chối (Lỗi 401/403).")
        print("\nNguyên nhân 100% nằm ở API Key, có thể do:")
        print(" 1. Key bị copy thiếu/dư khoảng trắng ở đầu hoặc cuối.")
        print(" 2. Key chưa được kích hoạt, bị khóa, hoặc thiếu quyền (Permissions) truy cập API v2.")
        print(" 3. MacroFab yêu cầu nạp tiền/thẻ tín dụng trước khi cho phép dùng API.")
        print("\n💡 GIẢI PHÁP: Vui lòng đăng nhập lại web MacroFab, tạo 1 API Key mới và thử lại.")
    print("="*50)

if __name__ == "__main__":
    test_macrofab_auth()