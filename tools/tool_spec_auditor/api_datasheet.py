import os
import time
import base64
import random
import requests
from typing import Optional, List

_DIGIKEY_CACHE = {"token": None, "expires_at": 0}

def get_digikey_token(client_id: str, client_secret: str) -> str:
    now = time.time()
    if _DIGIKEY_CACHE["token"] and _DIGIKEY_CACHE["expires_at"] > now:
        return _DIGIKEY_CACHE["token"]

    cid = client_id.strip().replace('"', '').replace("'", "")
    csec = client_secret.strip().replace('"', '').replace("'", "")
    
    if not cid or not csec:
        print(" -> [DigiKey] Bỏ qua vì chưa có Client ID / Secret.")
        return None

    url = "https://api.digikey.com/v1/oauth2/token"
    b64_creds = base64.b64encode(f"{cid}:{csec}".encode("utf-8")).decode("utf-8")
    
    headers = {
        "Authorization": f"Basic {b64_creds}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    try:
        res = requests.post(url, data={"grant_type": "client_credentials"}, headers=headers, timeout=10)
        if res.status_code == 200:
            d = res.json()
            _DIGIKEY_CACHE["token"] = d.get("access_token")
            _DIGIKEY_CACHE["expires_at"] = now + d.get("expires_in", 86400) - 120
            return _DIGIKEY_CACHE["token"]
    except Exception as e:
        print(f" -> [DigiKey Auth Exception] {e}")
    return None

def get_digikey_datasheet_url(keyword: str, client_id: str, client_secret: str) -> Optional[str]:
    token = get_digikey_token(client_id, client_secret)
    if not token: return None

    search_url = "https://api.digikey.com/products/v4/search/keyword"
    headers = {
        "Authorization": f"Bearer {token}",
        "X-DIGIKEY-Client-Id": client_id.strip(),
        "Content-Type": "application/json"
    }
    payload = {"Keywords": keyword, "Limit": 5, "Offset": 0}
    
    try:
        res = requests.post(search_url, headers=headers, json=payload, timeout=10)
        if res.status_code == 200:
            products = res.json().get("Products", [])
            for p in products:
                ds_url = p.get("DatasheetUrl")
                if ds_url: 
                    if ds_url.startswith("//"):
                        ds_url = "https:" + ds_url
                    return ds_url
    except Exception as e:
        print(f" -> [DigiKey Search Exception] {e}")
    return None

def get_mouser_datasheet_url(keyword: str, api_key: str) -> Optional[str]:
    clean_key = str(api_key).strip().replace('"', '').replace("'", "")
    if not clean_key: 
        return None
    
    url = "https://api.mouser.com/api/v1/search/keyword"
    payload = {
        "SearchByKeywordRequest": {
            "keyword": keyword,
            "records": 5,
            "startingRecord": 0,
            "searchOptions": "InStock"
        }
    }
    headers = {"Content-Type": "application/json"}
    
    try:
        res = requests.post(url, params={"apiKey": clean_key}, json=payload, headers=headers, timeout=10)
        if res.status_code == 200:
            parts = res.json().get("SearchResults", {}).get("Parts", [])
            for p in parts:
                ds_url = p.get("DataSheetUrl")
                if ds_url: return ds_url
    except Exception as e:
        print(f" -> [Mouser Search Exception] {e}")
    return None

def get_fallback_datasheet_url(keyword: str) -> Optional[str]:
    """Sử dụng thư viện ddgs (DuckDuckGo mới)"""
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
    except ImportError:
        print(" -> [Web Search] THẤT BẠI: Chưa cài thư viện `ddgs`.")
        return None

    query = f'{keyword} datasheet filetype:pdf'
    try:
        time.sleep(1.5) 
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
            for res in results:
                url = res.get('href', '')
                if 'pdf' in url.lower() or 'download' in url.lower() or 'doc' in url.lower():
                    return url
    except Exception as e:
        print(f" -> [Web Search Lỗi] {e}")
    return None

def download_pdf(url: str, save_path: str) -> bool:
    if not url: return False
    try:
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
        ]
        headers = {
            'User-Agent': random.choice(user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/pdf,*/*;q=0.9',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive'
        }
        r = requests.get(url, headers=headers, stream=True, timeout=15, allow_redirects=True)
        
        c_type = r.headers.get('Content-Type', '').lower()
        # Nới lỏng: Cho phép tải nếu server không khai báo rõ là HTML
        if r.status_code == 200 and 'text/html' not in c_type:
            with open(save_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            if os.path.exists(save_path) and os.path.getsize(save_path) > 2048:
                return True
            else:
                os.remove(save_path)
    except Exception as e:
        print(f" -> [Lỗi Tải File từ URL: {url}] {e}")
    return False

def generate_search_variants(part_number: str) -> List[str]:
    pn = part_number.strip()
    if not pn or pn == "-": return []
    
    variants = [pn]
    
    if '(' in pn:
        clean_paren = pn.split('(')[0].strip()
        if clean_paren not in variants: variants.append(clean_paren)
    else:
        clean_paren = pn
        
    delimiters = [i for i, c in enumerate(clean_paren) if c in '-/']
    for i in reversed(delimiters):
        if i >= 4:
            base_kw = clean_paren[:i]
            if base_kw not in variants: variants.append(base_kw)
            
    return variants

def auto_fetch_datasheet(part_number: str, tt: int, save_dir: str, 
                         mouser_key: str = "", dk_client: str = "", dk_secret: str = "") -> Optional[str]:
    variants = generate_search_variants(part_number)
    if not variants: return None
    
    safe_name = "".join([c for c in str(part_number).strip() if c.isalnum() or c in ['-', '_']]).rstrip()
    save_filename = f"{tt}_{safe_name}.pdf"
    save_path = os.path.join(save_dir, save_filename)
    
    print(f"\n[{tt}] Bắt đầu quy trình quét Datasheet cho: '{part_number}'")

    for kw in variants:
        print(f" [*] Đang thử từ khóa: {kw}")
        
        ds_url = get_digikey_datasheet_url(kw, dk_client, dk_secret)
        if ds_url:
            print(f" -> Tìm thấy URL trên DigiKey: {ds_url}")
            if download_pdf(ds_url, save_path): return save_filename
            
        ds_url = get_mouser_datasheet_url(kw, mouser_key)
        if ds_url:
            print(f" -> Tìm thấy URL trên Mouser: {ds_url}")
            if download_pdf(ds_url, save_path): return save_filename
            
        ds_url = get_fallback_datasheet_url(kw)
        if ds_url:
            print(f" -> Tìm thấy URL qua Web Search: {ds_url}")
            if download_pdf(ds_url, save_path): return save_filename

    print(f" -> ❌ THẤT BẠI: Đã thử toàn bộ API và Web Search nhưng không lấy được file cho '{part_number}'.")
    return None