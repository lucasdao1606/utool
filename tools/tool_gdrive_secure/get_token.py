from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/drive.file']

def main():
    print("Đang mở trình duyệt để đăng nhập...")
    # Đọc file credentials.json bạn vừa tải về
    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
    creds = flow.run_local_server(port=0)
    
    print("\n" + "="*50)
    print("🎉 HÃY COPY TOÀN BỘ ĐOẠN DƯỚI ĐÂY VÀ DÁN VÀO FILE .streamlit/secrets.toml:\n")
    print("[gcp_oauth]")
    print(f'token = "{creds.token}"')
    print(f'refresh_token = "{creds.refresh_token}"')
    print(f'token_uri = "{creds.token_uri}"')
    print(f'client_id = "{creds.client_id}"')
    print(f'client_secret = "{creds.client_secret}"')
    print("="*50)

if __name__ == '__main__':
    main()