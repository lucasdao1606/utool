import io
import httplib2
import streamlit as st
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from google_auth_httplib2 import AuthorizedHttp
from tools.tool_gdrive_secure.src.utils.config import SCOPES, DRIVE_FOLDER_ID

@st.cache_resource
def authenticate_gdrive():
    oauth_info = st.secrets["gcp_oauth"]
    
    creds = Credentials(
        token=oauth_info["token"],
        refresh_token=oauth_info["refresh_token"],
        token_uri=oauth_info["token_uri"],
        client_id=oauth_info["client_id"],
        client_secret=oauth_info["client_secret"],
        scopes=SCOPES
    )
    
    # Kéo dài thời gian chờ mạng lên 120 giây để tránh nghẽn kết nối trên VPS
    http = httplib2.Http(timeout=120)
    authed_http = AuthorizedHttp(creds, http=http)
    
    # Truyền http object đã cấu hình timeout vào service
    return build('drive', 'v3', http=authed_http)

def upload_to_drive(file_obj, filename):
    service = authenticate_gdrive()
    
    file_metadata = {
        'name': filename,
        'parents': [DRIVE_FOLDER_ID]
    }
    
    media = MediaIoBaseUpload(file_obj, mimetype='application/octet-stream', resumable=True)
    
    uploaded_file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id'
    ).execute()
    
    return uploaded_file.get('id')

def list_encrypted_files():
    """Lấy danh sách các file .enc kèm theo dung lượng và thời gian tạo."""
    service = authenticate_gdrive()
    query = f"'{DRIVE_FOLDER_ID}' in parents and trashed=false and name contains '.enc'"
    
    results = service.files().list(
        q=query, 
        fields="files(id, name, createdTime, size)",
        pageSize=100
    ).execute()
    
    return results.get('files', [])

def download_from_drive(file_id):
    service = authenticate_gdrive()
    request = service.files().get_media(fileId=file_id)
    
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
        
    return fh.getvalue()

def delete_from_drive(file_id):
    service = authenticate_gdrive()
    try:
        service.files().delete(fileId=file_id).execute()
        return True
    except Exception as e:
        raise Exception(f"Không thể xóa file: {e}")