# Module BOM Checker
import io
import re
import time
import base64
import random
import urllib.parse
import requests
import pandas as pd
import openpyxl
from bs4 import BeautifulSoup
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from google import genai

# ==========================================
# 1. TẠO FILE BOM TEMPLATE CHUẨN MẪU
# ==========================================
def generate_sample_bom_template() -> bytes:
    # Tối giản template chỉ giữ lại 2 cột thiết yếu
    data = [
        {"MPN": "STM32F407VGT6", "Quantity": 500},
        {"MPN": "ESP32-WROOM-32E", "Quantity": 1000},
        {"MPN": "ATMEGA328P-AU", "Quantity": 200},
        {"MPN": "AMS1117-3.3", "Quantity": 2000},
        {"MPN": "CH340G", "Quantity": 500},
        {"MPN": "LM358DR", "Quantity": 800},
        {"MPN": "0603WAF1002T5E", "Quantity": 5000},
        {"MPN": "CL10A106KP8NNNC", "Quantity": 5000}
    ]
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="BOM_Standard_Template")
        ws = writer.sheets["BOM_Standard_Template"]
        _style_excel_sheet(ws, is_template=True)
    return output.getvalue()


# ==========================================
# 2. BỘ LỌC TỪ KHÓA MÔ TẢ TỐI ƯU
# ==========================================
def clean_description_for_search(desc: str) -> str:
    if not desc or desc == "-":
        return ""
    
    noise_words = [
        "rohs", "rohs3", "pb free", "lead free", "pb-free", "compliant",
        "reel", "tape", "cut tape", "digi-reel", "tube", "tray", "bulk",
        "ic", "smd", "smt", "through hole", "tht", "standard", "generic",
        "original", "brand new", "package", "series", "commercial"
    ]
    
    text = desc.lower()
    for w in noise_words:
        text = re.sub(rf"\b{re.escape(w)}\b", " ", text)
    
    text = re.sub(r"[,;:/\\()\[\]{}*+]", " ", text)
    tokens = [w.strip() for w in text.split() if len(w.strip()) > 1]
    
    return " ".join(tokens[:4])


def is_different_manufacturer(mfg1: str, mfg2: str) -> bool:
    if not mfg1 or not mfg2 or mfg1 == "-" or mfg2 == "-":
        return True
    
    clean_1 = re.sub(r"(inc|corp|corporation|ltd|limited|llc|co|electronics|systems|microelectronics|semiconductor)", "", mfg1.lower()).strip()
    clean_2 = re.sub(r"(inc|corp|corporation|ltd|limited|llc|co|electronics|systems|microelectronics|semiconductor)", "", mfg2.lower()).strip()
    
    if not clean_1 or not clean_2:
        return mfg1.lower().strip() != mfg2.lower().strip()
        
    return clean_1 not in clean_2 and clean_2 not in clean_1


# ==========================================
# 2.5 HÀM TRỢ GIÚP TRÍCH XUẤT & TỔNG HỢP SPEC BẰNG GEMINI
# ==========================================
def _extract_parameters(product_data: dict) -> dict:
    params = product_data.get("Parameters", [])
    if not params: 
        return {}
    return {p.get("ParameterText", ""): p.get("ValueText", "") for p in params}

_AVAILABLE_MODELS = [
    'gemini-3.8-flash',
    'gemini-3.7-flash',
    'gemini-3.6-flash',
    'gemini-3.5-flash',
    'gemini-2.5-flash',
    'gemini-flash-latest'
]

def search_and_scrape_google_for_spec(api_key: str, cx: str, mpn: str, debug_logs: list = None) -> str:
    if not api_key or not cx:
        return ""
    
    query = urllib.parse.quote(f"{mpn} datasheet specifications features")
    url = f"https://www.googleapis.com/customsearch/v1?q={query}&key={api_key}&cx={cx}"
    
    try:
        res = requests.get(url, timeout=10)
        if res.status_code != 200:
            if debug_logs is not None:
                debug_logs.append(f"❌ [Google Search] Lỗi {res.status_code}: {res.text[:100]}")
            return ""
        
        items = res.json().get("items", [])
        if not items:
            return ""
            
        scraped_text = ""
        for item in items[:2]:
            link = item.get("link")
            try:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                page_res = requests.get(link, headers=headers, timeout=8)
                if page_res.status_code == 200:
                    soup = BeautifulSoup(page_res.text, 'html.parser')
                    text = soup.get_text(separator=' ', strip=True)
                    scraped_text += f"\nNguồn: {link}\n{text[:1500]}\n---"
            except Exception as e:
                if debug_logs is not None:
                    debug_logs.append(f"⚠️ [Google Scrape] Lỗi đọc {link}: {e}")
                
        return scraped_text
    except Exception as e:
        if debug_logs is not None:
            debug_logs.append(f"❌ [Google Search] Exception: {e}")
        return ""

def build_spec_baseline_with_gemini(api_keys: list, base_mpn: str, base_data: dict, alt1_data: dict, alt2_data: dict, scraped_context: str = "", debug_logs: list = None) -> str:
    if not api_keys:
        return "Vui lòng cấu hình Gemini API Key."
    
    prompt = f"""
    Bạn là một kỹ sư linh kiện điện tử (Component Engineer). 
    Hãy xây dựng "Bảng Yêu Cầu Kỹ Thuật (Spec Baseline)" làm tiêu chuẩn mua hàng.
    """
    
    if alt1_data or alt2_data:
        prompt += "Tiêu chuẩn phải BAO HÀM và ĐÁP ỨNG được tất cả các mã sau bằng quy tắc chặn trên/dưới (Min/Max):\n"
        prompt += f"1. Mã gốc: {base_mpn} | Thông số: {base_data.get('parameters', base_data.get('description', '-'))}\n"
        if alt1_data:
            prompt += f"2. Mã thay thế 1: {alt1_data.get('mpn')} | Thông số: {alt1_data.get('parameters', alt1_data.get('description', '-'))}\n"
        if alt2_data:
            prompt += f"3. Mã thay thế 2: {alt2_data.get('mpn')} | Thông số: {alt2_data.get('parameters', alt2_data.get('description', '-'))}\n"
    else:
        prompt += f"Dựa trên thông tin của duy nhất mã gốc sau đây, hãy trích xuất các thông số kỹ thuật cốt lõi để làm tiêu chuẩn mua hàng:\n"
        prompt += f"- Mã gốc: {base_mpn} | Thông số: {base_data.get('parameters', base_data.get('description', '-'))}\n"

    if scraped_context:
        prompt += f"\n(Lưu ý: Dữ liệu phân phối bị thiếu. Vui lòng tham khảo thêm thông tin cào được từ website sau đây để tổng hợp Spec):\n{scraped_context}\n"
        
    prompt += """
    YÊU CẦU ĐỊNH DẠNG NGHIÊM NGẶT:
    - Xuất trực tiếp dưới dạng danh sách gạch đầu dòng (bắt đầu bằng dấu trừ "-").
    - TUYỆT ĐỐI KHÔNG dùng ký hiệu in đậm (**).
    - TỐI ĐA HÓA việc sử dụng các ký hiệu toán học (≥, ≤, ~ hoặc -) thay vì dùng chữ (ví dụ: dùng "≥ 120 MHz" thay vì "tối thiểu 120 MHz").
    - Ngắn gọn, chuyên nghiệp, không giải thích thêm. Viết bằng tiếng Việt.
    """
    
    keys_to_try = list(api_keys)
    random.shuffle(keys_to_try)
    errors_log = []

    for key in keys_to_try:
        try:
            client = genai.Client(api_key=key)
        except Exception as e:
            errors_log.append(f"Lỗi khởi tạo Client (Key ...{key[-4:]}): {e}")
            continue

        for model_name in _AVAILABLE_MODELS:
            max_retries = 2
            retries = 0
            
            while retries <= max_retries:
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                    )
                    if response and response.text:
                        if debug_logs is not None:
                            debug_logs.append(f"🤖 [Gemini] Thành công tạo Spec với {model_name} (Key ...{key[-4:]})")
                        return response.text.strip()
                    else:
                        raise ValueError("Phản hồi rỗng hoặc bị Google chặn (Safety Block).")
                        
                except Exception as e:
                    error_msg = str(e).lower()
                    
                    if "429" in error_msg or "quota" in error_msg or "exhausted" in error_msg:
                        if retries < max_retries:
                            wait_time = 2 * (2 ** retries)
                            if debug_logs is not None:
                                debug_logs.append(f"⚠️ [API Rate Limit] {model_name} quá tải. Chờ {wait_time}s...")
                            time.sleep(wait_time)
                            retries += 1
                            continue 
                        else:
                            errors_log.append(f"{model_name} (Hết lượt truy cập 429)")
                            break 
                    
                    elif "404" in error_msg or "not found" in error_msg:
                        errors_log.append(f"{model_name} (Bị khóa/404)")
                        break 
                    else:
                        errors_log.append(f"{model_name} ({str(e)})")
                        break 
            
    if debug_logs is not None:
        debug_logs.append(f"❌ [Gemini Fail] Toàn bộ lỗi: {'; '.join(errors_log)}")
        
    return "Lỗi tạo Spec: Hệ thống AI hiện đang quá tải hoặc không khả dụng."


# ==========================================
# 3. DIGIKEY SEARCH ENGINES (CHÍNH & CROSS-REF)
# ==========================================
_DIGIKEY_CACHE = {"token": None, "expires_at": 0}

def get_digikey_token(client_id: str, client_secret: str, debug_logs: list = None) -> str:
    now = time.time()
    if _DIGIKEY_CACHE["token"] and _DIGIKEY_CACHE["expires_at"] > now:
        return _DIGIKEY_CACHE["token"]

    cid = client_id.strip().replace('"', '').replace("'", "")
    csec = client_secret.strip().replace('"', '').replace("'", "")
    
    url = "https://api.digikey.com/v1/oauth2/token"
    credentials = f"{cid}:{csec}"
    b64_creds = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
    
    headers = {
        "Authorization": f"Basic {b64_creds}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    payload = {"grant_type": "client_credentials"}
    
    try:
        res = requests.post(url, data=payload, headers=headers, timeout=15)
        if res.status_code != 200:
            if debug_logs is not None:
                debug_logs.append(f"❌ [DigiKey Auth Lỗi {res.status_code}]: {res.text[:200]}")
            return None

        d = res.json()
        _DIGIKEY_CACHE["token"] = d.get("access_token")
        _DIGIKEY_CACHE["expires_at"] = now + d.get("expires_in", 86400) - 120
        return _DIGIKEY_CACHE["token"]
    except Exception as e:
        if debug_logs is not None:
            debug_logs.append(f"❌ [DigiKey Auth Exception]: {e}")
        return None


def search_digikey_alternates_by_keyword(client_id: str, client_secret: str, keyword: str, exclude_mpn: str, exclude_mfg: str, target_qty: int) -> list:
    if not client_id or not client_secret or not keyword:
        return []
    
    token = get_digikey_token(client_id, client_secret)
    if not token:
        return []
        
    headers = {
        "Authorization": f"Bearer {token}",
        "X-DIGIKEY-Client-Id": client_id.strip(),
        "Content-Type": "application/json"
    }
    search_url = "https://api.digikey.com/products/v4/search/keyword"
    payload = {"Keywords": keyword, "Limit": 15, "Offset": 0}
    
    try:
        res = requests.post(search_url, json=payload, headers=headers, timeout=12)
        if res.status_code != 200:
            return []
            
        products = res.json().get("Products", [])
        candidates = []
        
        for p in products:
            p_mpn = p.get("ManufacturerProductNumber", "") or p.get("ManufacturerPartNumber", "")
            if not p_mpn or p_mpn.lower() == exclude_mpn.lower():
                continue
                
            mfg_name = p.get("Manufacturer", {}).get("Name", "-") if isinstance(p.get("Manufacturer"), dict) else str(p.get("Manufacturer", "-"))
            
            if not is_different_manufacturer(exclude_mfg, mfg_name):
                continue
                
            stock = p.get("QuantityAvailable", 0) or 0
            
            matched_price = None
            pricing = p.get("ProductVariations", [{}])[0].get("StandardPricing", []) if p.get("ProductVariations") else []
            for pr in sorted(pricing, key=lambda x: x.get("BreakQuantity", 0)):
                if target_qty >= pr.get("BreakQuantity", 0):
                    matched_price = pr.get("UnitPrice")
            if not matched_price and pricing:
                matched_price = pricing[0].get("UnitPrice")
                
            candidates.append({
                "mpn": p_mpn,
                "manufacturer": mfg_name,
                "stock": stock,
                "price": f"{matched_price} USD" if matched_price else "Liên hệ",
                "source": "DigiKey",
                "description": p.get("ProductDescription", ""),
                "parameters": _extract_parameters(p)
            })
            
        candidates.sort(key=lambda x: (x["stock"] <= 0, -x["stock"]))
        return candidates
    except Exception:
        return []


def query_digikey(client_id: str, client_secret: str, mpn: str, target_qty: int, debug_logs: list = None) -> dict:
    cid = client_id.strip()
    csec = client_secret.strip()
    if not cid or not csec:
        return {}

    clean_mpn = str(mpn).strip()
    token = get_digikey_token(cid, csec, debug_logs)
    if not token:
        return {}

    headers = {
        "Authorization": f"Bearer {token}",
        "X-DIGIKEY-Client-Id": cid,
        "Content-Type": "application/json"
    }

    search_url = "https://api.digikey.com/products/v4/search/keyword"
    payload = {"Keywords": clean_mpn, "Limit": 6, "Offset": 0}

    try:
        res = requests.post(search_url, json=payload, headers=headers, timeout=12)
        products = []
        if res.status_code == 200:
            products = res.json().get("Products", [])

        if not products:
            detail_url = f"https://api.digikey.com/products/v4/search/{clean_mpn}/productdetails"
            res_det = requests.get(detail_url, headers=headers, timeout=12)
            if res_det.status_code == 200:
                p_item = res_det.json().get("Product")
                if p_item:
                    products = [p_item]

        if not products:
            return {}

        best_p = products[0]
        for p in products:
            p_mpn = p.get("ManufacturerProductNumber", "") or p.get("ManufacturerPartNumber", "")
            if p_mpn.lower() == clean_mpn.lower():
                best_p = p
                break

        stock = best_p.get("QuantityAvailable", 0) or 0
        std_lead = best_p.get("ManufacturerStandardLeadWeeks")
        lead_time = f"{std_lead} tuần" if std_lead else ("Sẵn kho" if stock > 0 else "Liên hệ")

        matched_price = None
        variations = best_p.get("ProductVariations", [])
        pricing = variations[0].get("StandardPricing", []) if variations else best_p.get("StandardPricing", [])

        for pr in sorted(pricing, key=lambda x: x.get("BreakQuantity", 0)):
            if target_qty >= pr.get("BreakQuantity", 0):
                matched_price = pr.get("UnitPrice")
        if not matched_price and pricing:
            matched_price = pricing[0].get("UnitPrice")

        desc = best_p.get("Description", {}).get("ProductDescription", "") if isinstance(best_p.get("Description"), dict) else str(best_p.get("Description", ""))
        mfg = best_p.get("Manufacturer", {}).get("Name", "") if isinstance(best_p.get("Manufacturer"), dict) else str(best_p.get("Manufacturer", ""))

        if debug_logs is not None:
            p_log = f"{matched_price} USD" if matched_price else "Liên hệ"
            debug_logs.append(f"✅ [DigiKey] '{clean_mpn}': Kho {stock} | Giá {p_log}")

        return {
            "description": desc,
            "manufacturer": mfg,
            "lifecycle": "Active",
            "datasheet": best_p.get("DatasheetUrl", ""),
            "parameters": _extract_parameters(best_p),
            "offers": [{
                "distributor": "DigiKey",
                "stock": stock,
                "lead_time": lead_time,
                "price": matched_price,
                "currency": "USD",
                "is_stock_enough": stock >= target_qty
            }]
        }
    except Exception as e:
        return {}


# ==========================================
# 4. MOUSER SEARCH ENGINES (ĐỐI SÁNH & CROSS-REF BỔ TRỢ)
# ==========================================
def search_mouser_alternates_by_keyword(api_key: str, keyword: str, exclude_mpn: str, exclude_mfg: str, target_qty: int) -> list:
    if not api_key or not keyword:
        return []
    clean_key = str(api_key).strip().replace('"', '').replace("'", "")
    url = "https://api.mouser.com/api/v1/search/keyword"
    params = {"apiKey": clean_key}
    payload = {
        "SearchByKeywordRequest": {
            "keyword": keyword,
            "records": 12,
            "startingRecord": 0,
            "searchOptions": "InStock"
        }
    }
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    try:
        res = requests.post(url, params=params, json=payload, headers=headers, timeout=12)
        if res.status_code != 200:
            return []
        parts = res.json().get("SearchResults", {}).get("Parts", [])
        candidates = []
        for p in parts:
            p_mpn = p.get("ManufacturerPartNumber", "").strip()
            if not p_mpn or p_mpn.lower() == exclude_mpn.lower():
                continue
                
            mfg_name = p.get("Manufacturer", "-")
            if not is_different_manufacturer(exclude_mfg, mfg_name):
                continue
                
            stock_raw = str(p.get("Availability", "0"))
            stock = int("".join([c for c in stock_raw if c.isdigit()]) or 0)
            
            price_val = None
            currency = "USD"
            for pb in p.get("PriceBreaks", []):
                try:
                    q = int(pb.get("Quantity", 0))
                    if target_qty >= q:
                        price_val = float(str(pb.get("Price", "0")).replace("$", "").replace(",", "").strip())
                        currency = pb.get("Currency", "USD")
                except Exception:
                    continue
                    
            candidates.append({
                "mpn": p_mpn,
                "manufacturer": mfg_name,
                "stock": stock,
                "price": f"{price_val} {currency}" if price_val else "Liên hệ",
                "source": "Mouser",
                "description": p.get("Description", ""),
                "parameters": {}
            })
            
        candidates.sort(key=lambda x: (x["stock"] <= 0, -x["stock"]))
        return candidates
    except Exception:
        return []


def query_mouser_part(api_key: str, mpn: str, target_qty: int, ref_desc: str = "", debug_logs: list = None) -> dict:
    clean_key = str(api_key).strip().replace('"', '').replace("'", "")
    if not clean_key:
        return {}
    clean_mpn = str(mpn).strip()
    url = "https://api.mouser.com/api/v1/search/partnumber"
    params = {"apiKey": clean_key}
    payload = {
        "SearchByPartRequest": {
            "mouserPartNumber": clean_mpn,
            "partSearchOptions": "Exact"
        }
    }
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    try:
        res = requests.post(url, params=params, json=payload, headers=headers, timeout=15)
        if res.status_code != 200:
            return {}
        data = res.json()
        parts = data.get("SearchResults", {}).get("Parts", [])
        if not parts:
            return {}

        primary = parts[0]
        stock_raw = str(primary.get("Availability", "0"))
        stock = int("".join([c for c in stock_raw if c.isdigit()]) or 0)
        lead_time = primary.get("LeadTime", "Sẵn kho") or "Sẵn kho"

        matched_price = None
        currency = "USD"
        breaks = []
        for pb in primary.get("PriceBreaks", []):
            try:
                q = int(pb.get("Quantity", 0))
                p = float(str(pb.get("Price", "0")).replace("$", "").replace(",", "").strip())
                breaks.append((q, p, pb.get("Currency", "USD")))
            except Exception:
                continue
        breaks.sort(key=lambda x: x[0])
        for q, p, c in breaks:
            if target_qty >= q:
                matched_price = p
                currency = c
        if not matched_price and breaks:
            matched_price = breaks[0][1]
            currency = breaks[0][2]

        desc = primary.get("Description", "") or ref_desc
        mfg = primary.get("Manufacturer", "")

        if debug_logs is not None:
            p_log = f"{matched_price} {currency}" if matched_price else "Liên hệ"
            debug_logs.append(f"✅ [Mouser] '{clean_mpn}': Kho {stock} | Giá {p_log}")

        return {
            "description": desc,
            "manufacturer": mfg,
            "lifecycle": primary.get("LifecycleStatus", "Active") or "Active",
            "datasheet": primary.get("DataSheetUrl", ""),
            "offers": [{
                "distributor": "Mouser",
                "stock": stock,
                "lead_time": lead_time,
                "price": matched_price,
                "currency": currency,
                "is_stock_enough": stock >= target_qty
            }]
        }
    except Exception:
        return {}


# ==========================================
# 5. PROVIDER 3: OEMSECRETS API
# ==========================================
def query_oemsecrets(api_key: str, mpn: str, target_qty: int, debug_logs: list = None) -> dict:
    clean_key = str(api_key).strip()
    if not clean_key:
        return {}
    clean_mpn = str(mpn).strip()
    try:
        url = f"https://sandbox.oemsecrets.com/api/partsearch?searchTerm={clean_mpn}&apiKey={clean_key}"
        res = requests.get(url, timeout=12)
        if res.status_code != 200:
            return {}
        parts = res.json().get("stock", [])
        offers = []
        for p in parts:
            dist = p.get("distributor", {}).get("distributor_name", "OEM Distributor")
            stock = int(p.get("quantity", 0) or 0)
            price_val = float(p.get("price")) if p.get("price") else None
            offers.append({
                "distributor": dist,
                "stock": stock,
                "lead_time": p.get("lead_time") or "Sẵn kho",
                "price": price_val,
                "currency": p.get("currency", "USD"),
                "is_stock_enough": stock >= target_qty
            })
        return {"offers": offers} if offers else {}
    except Exception:
        return {}


# ==========================================
# 6. PROVIDER 4: NEXAR GRAPHQL API
# ==========================================
_NEXAR_CACHE = {"token": None, "expires_at": 0}

def get_nexar_token(client_id: str, client_secret: str, debug_logs: list = None) -> str:
    now = time.time()
    if _NEXAR_CACHE["token"] and _NEXAR_CACHE["expires_at"] > now:
        return _NEXAR_CACHE["token"]
    url = "https://identity.nexar.com/connect/token"
    try:
        res = requests.post(
            url,
            data={"grant_type": "client_credentials", "client_id": client_id.strip(), "client_secret": client_secret.strip()},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=12
        )
        if res.status_code != 200:
            return None
        d = res.json()
        _NEXAR_CACHE["token"] = d.get("access_token")
        _NEXAR_CACHE["expires_at"] = now + d.get("expires_in", 86400) - 300
        return _NEXAR_CACHE["token"]
    except Exception:
        return None

def query_nexar(client_id: str, client_secret: str, mpn: str, target_qty: int, debug_logs: list = None) -> dict:
    if not client_id or not client_secret:
        return {}
    clean_mpn = str(mpn).strip()
    token = get_nexar_token(client_id, client_secret, debug_logs)
    if not token:
        return {}
    try:
        query = """
        query SearchSupply($q: String!) {
          supSearch(q: $q, limit: 1) {
            results {
              part {
                shortDescription
                sellers(authorizedOnly: true) {
                  company { name }
                  offers {
                    inventoryLevel
                    factoryLeadDays
                    prices { quantity price currency }
                  }
                }
              }
            }
          }
        }
        """
        res = requests.post(
            "https://api.nexar.com/graphql",
            json={"query": query, "variables": {"q": clean_mpn}},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=15
        )
        if res.status_code != 200 or "errors" in res.json():
            return {}
        results = res.json().get("data", {}).get("supSearch", {}).get("results", [])
        if not results:
            return {}
        part_node = results[0].get("part", {})
        sellers = part_node.get("sellers", [])
        offers = []
        for s in sellers:
            d_name = s.get("company", {}).get("name", "Unknown")
            for off in s.get("offers", []):
                stk = off.get("inventoryLevel", 0) or 0
                days = off.get("factoryLeadDays")
                lt = f"{round(days / 7)} tuần" if days else "Sẵn kho"
                matched_p = None
                curr = "USD"
                for p in sorted(off.get("prices") or [], key=lambda x: x.get("quantity", 0)):
                    if target_qty >= p.get("quantity", 0):
                        matched_p = p.get("price")
                        curr = p.get("currency", "USD")
                offers.append({
                    "distributor": d_name,
                    "stock": stk,
                    "lead_time": lt,
                    "price": matched_p,
                    "currency": curr,
                    "is_stock_enough": stk >= target_qty
                })
        return {"description": part_node.get("shortDescription", ""), "offers": offers}
    except Exception:
        return {}


# ==========================================
# 7. HÀM CHÍNH ĐIỀU PHỐI VÀ TÌM CROSS-REFERENCE
# ==========================================
def fetch_cross_references(keyword: str, exclude_mpn: str, exclude_mfg: str, target_qty: int, config: dict) -> list:
    if not keyword:
        return []
        
    alternates = []
    seen_mpns = {exclude_mpn.lower()}
    seen_mfgs = set()

    dk_alts = search_digikey_alternates_by_keyword(
        config.get("digikey_id", ""),
        config.get("digikey_secret", ""),
        keyword,
        exclude_mpn,
        exclude_mfg,
        target_qty
    )
    for a in dk_alts:
        m_key = a["mpn"].lower()
        mfg_key = a["manufacturer"].lower().strip()
        if m_key not in seen_mpns and mfg_key not in seen_mfgs:
            seen_mpns.add(m_key)
            seen_mfgs.add(mfg_key)
            alternates.append(a)
            if len(alternates) == 2:
                break

    if len(alternates) < 2 and config.get("mouser_key"):
        mouser_alts = search_mouser_alternates_by_keyword(
            config.get("mouser_key", ""),
            keyword,
            exclude_mpn,
            exclude_mfg,
            target_qty
        )
        for a in mouser_alts:
            m_key = a["mpn"].lower()
            mfg_key = a["manufacturer"].lower().strip()
            if m_key not in seen_mpns and mfg_key not in seen_mfgs:
                seen_mpns.add(m_key)
                seen_mfgs.add(mfg_key)
                alternates.append(a)
                if len(alternates) == 2:
                    break

    return alternates


def process_bom_data(df: pd.DataFrame, mpn_col: str, qty_col: str, des_col: str, config: dict, progress_bar=None, status_text=None, debug_logs: list = None, partial_callback=None) -> list:
    results = []
    total = len(df)

    for idx, (_, row) in enumerate(df.iterrows()):
        mpn = str(row[mpn_col]).strip() if pd.notna(row[mpn_col]) else ""
        if not mpn or mpn.lower() == "nan":
            continue

        try:
            qty = int(row[qty_col]) if pd.notna(row[qty_col]) else 1
        except (ValueError, TypeError):
            qty = 1

        designator = str(row[des_col]).strip() if des_col and des_col in row and pd.notna(row[des_col]) else f"U{idx+1}"

        if debug_logs is not None:
            debug_logs.append(f"--- Đang thẩm định mã [{idx+1}/{total}]: {mpn} (SL: {qty}) ---")

        all_offers = []
        description = str(row.get("Description", "")) if "Description" in row and pd.notna(row.get("Description")) else "-"
        mfg = str(row.get("Manufacturer", "")) if "Manufacturer" in row and pd.notna(row.get("Manufacturer")) else "-"
        lifecycle = "Active"
        datasheet = ""
        base_params = {}

        # ====================================================
        # BƯỚC 1: TRUY VẤN DIGIKEY
        # ====================================================
        dk_res = query_digikey(config.get("digikey_id", ""), config.get("digikey_secret", ""), mpn, qty, debug_logs)
        if dk_res:
            description = dk_res.get("description") or description
            mfg = dk_res.get("manufacturer") or mfg
            lifecycle = dk_res.get("lifecycle") or lifecycle
            datasheet = dk_res.get("datasheet") or datasheet
            base_params = dk_res.get("parameters", {})
            all_offers.extend(dk_res.get("offers", []))

        # ====================================================
        # BƯỚC 2: TRUY VẤN MOUSER
        # ====================================================
        mouser_res = query_mouser_part(config.get("mouser_key", ""), mpn, qty, ref_desc=description, debug_logs=debug_logs)
        if mouser_res:
            if description == "-":
                description = mouser_res.get("description") or "-"
            if mfg == "-":
                mfg = mouser_res.get("manufacturer") or "-"
            if not datasheet:
                datasheet = mouser_res.get("datasheet") or ""
            all_offers.extend(mouser_res.get("offers", []))

        # ====================================================
        # BƯỚC 3: TÌM MÃ TƯƠNG ĐƯƠNG
        # ====================================================
        clean_kw = clean_description_for_search(description)
        alternates = fetch_cross_references(clean_kw, mpn, mfg, qty, config)

        # ====================================================
        # BƯỚC 4: TỔNG HỢP SPEC BASELINE BẰNG GEMINI
        # ====================================================
        alt_2 = alternates[0] if len(alternates) > 0 else {}
        alt_3 = alternates[1] if len(alternates) > 1 else {}
        spec_baseline = ""
        
        gemini_keys = config.get("gemini_keys", [])
        
        has_valid_info = bool(base_params or (description and description != "-"))
        scraped_info = ""
        
        if not has_valid_info:
            g_api = config.get("google_api_key")
            g_cx = config.get("google_cx")
            if g_api and g_cx:
                if status_text:
                    status_text.caption(f"Đang tìm kiếm thông số kỹ thuật cho {mpn} trên Google...")
                scraped_info = search_and_scrape_google_for_spec(g_api, g_cx, mpn, debug_logs)
                if scraped_info and debug_logs is not None:
                    debug_logs.append(f"🌐 [Google Search] Đã lấy được dữ liệu web cho mã {mpn}.")

        if gemini_keys:
            if status_text:
                status_text.caption(f"Đang tổng hợp Bảng Yêu Cầu Kỹ Thuật cho: {mpn} bằng AI...")
            
            base_data_for_ai = {"parameters": base_params, "description": description}
            spec_baseline = build_spec_baseline_with_gemini(
                api_keys=gemini_keys,
                base_mpn=mpn,
                base_data=base_data_for_ai,
                alt1_data=alt_2,
                alt2_data=alt_3,
                scraped_context=scraped_info,
                debug_logs=debug_logs
            )

        # ====================================================
        # BƯỚC 5: OEMSECRETS & NEXAR
        # ====================================================
        oem_res = query_oemsecrets(config.get("oemsecrets_key", ""), mpn, qty, debug_logs)
        if oem_res:
            all_offers.extend(oem_res.get("offers", []))

        if not all_offers:
            nx_res = query_nexar(config.get("nexar_id", ""), config.get("nexar_secret", ""), mpn, qty, debug_logs)
            if nx_res:
                if description == "-":
                    description = nx_res.get("description") or "-"
                all_offers.extend(nx_res.get("offers", []))

        all_offers.sort(key=lambda x: (not x["is_stock_enough"], x["price"] if x["price"] is not None else 999999))

        unique_dists = []
        seen = set()
        for off in all_offers:
            if off["distributor"] not in seen:
                seen.add(off["distributor"])
                unique_dists.append(off)
                if len(unique_dists) == 2:
                    break

        d1 = unique_dists[0] if len(unique_dists) > 0 else None
        d2 = unique_dists[1] if len(unique_dists) > 1 else None

        total_stock = sum(o.get("stock", 0) for o in all_offers)

        if total_stock >= qty:
            status = "🟢 Sẵn hàng"
        elif total_stock > 0:
            status = "🟡 Thiếu hàng"
        else:
            status = "🔴 Hết hàng"

        if d1 and d1["price"] is not None:
            price_display = f"{d1['price']} {d1['currency']}"
            total_cost_str = f"{round(d1['price'] * qty, 2)} {d1['currency']}"
        else:
            price_display = "Liên hệ"
            total_cost_str = "Liên hệ"

        results.append({
            "STT": idx + 1,
            "Designator": designator,
            "Mã Gốc (MPN)": mpn,
            "Mô Tả Linh Kiện": description,
            "Yêu Cầu Kỹ Thuật (Chung)": spec_baseline,
            "Nhà Sản Xuất": mfg,
            "Vòng Đời": lifecycle,
            "SL Mua": qty,
            "Tổng Tồn Kho": total_stock,
            "Trạng Thái Cung Ứng": status,
            "Ước Tính Tổng Tiền": total_cost_str,

            "NCC 1 (Tối ưu)": d1["distributor"] if d1 else "-",
            "Đơn Giá 1": price_display,
            "Kho NCC 1": d1["stock"] if d1 else 0,
            "Lead Time 1": d1["lead_time"] if d1 else "-",

            "NCC 2": d2["distributor"] if d2 else "-",
            "Đơn Giá 2": f"{d2['price']} {d2['currency']}" if d2 and d2["price"] is not None else "-",
            "Kho NCC 2": d2["stock"] if d2 else 0,
            "Lead Time 2": d2["lead_time"] if d2 else "-",

            "Mã Tương Đương 2": alt_2.get("mpn", "-"),
            "NSX Mã 2": alt_2.get("manufacturer", "-"),
            "Kho Mã 2": alt_2.get("stock", 0),
            "Đơn Giá Mã 2": alt_2.get("price", "-"),

            "Mã Tương Đương 3": alt_3.get("mpn", "-"),
            "NSX Mã 3": alt_3.get("manufacturer", "-"),
            "Kho Mã 3": alt_3.get("stock", 0),
            "Đơn Giá Mã 3": alt_3.get("price", "-"),

            "Datasheet": datasheet
        })

        # Lưu dữ liệu phân đoạn vào phiên làm việc
        if partial_callback:
            partial_callback(results)

        processed = idx + 1
        if progress_bar:
            progress_bar.progress(processed / total)
        if status_text:
            status_text.caption(f"Đang thẩm định ({processed}/{total}): {mpn}")

    return results


# ==========================================
# 8. XUẤT FILE EXCEL CHUẨN ĐỊNH DẠNG BOM
# ==========================================
def _style_excel_sheet(ws, is_template=False):
    font_header = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
    font_data = Font(name="Segoe UI", size=9)
    font_bold_data = Font(name="Segoe UI", size=9, bold=True)

    fill_header = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    fill_alt = PatternFill(start_color="F9FAFB", end_color="F9FAFB", fill_type="solid")

    thin_border = Border(
        left=Side(style='thin', color="D9D9D9"),
        right=Side(style='thin', color="D9D9D9"),
        top=Side(style='thin', color="D9D9D9"),
        bottom=Side(style='thin', color="D9D9D9")
    )

    align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    align_left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    align_right = Alignment(horizontal="right", vertical="center")

    ws.row_dimensions[1].height = 28
    for cell in ws[1]:
        cell.font = font_header
        cell.fill = fill_header
        cell.alignment = align_center
        cell.border = thin_border

    for row_idx, row in enumerate(ws.iter_rows(min_row=2), start=2):
        ws.row_dimensions[row_idx].height = 22
        is_even = (row_idx % 2 == 0)
        for col_idx, cell in enumerate(row, start=1):
            cell.font = font_data
            cell.border = thin_border
            if is_even:
                cell.fill = fill_alt

            header_name = str(ws.cell(row=1, column=col_idx).value or "")
            if any(k in header_name for k in ["STT", "Designator", "Vòng Đời", "Trạng Thái", "Lead Time"]):
                cell.alignment = align_center
            elif any(k in header_name for k in ["SL", "Kho", "Giá", "Tiền", "Tồn"]):
                cell.alignment = align_right
                cell.font = font_bold_data
            else:
                cell.alignment = align_left

    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        header_name = str(col[0].value or "")
        
        for cell in col:
            val_str = str(cell.value or '')
            for line in val_str.split('\n'):
                if len(line) > max_len:
                    max_len = len(line)
                    
        if any(k in header_name for k in ["Yêu Cầu", "Mô Tả"]):
            ws.column_dimensions[col_letter].width = min(max(max_len + 4, 25), 65) 
        else:
            ws.column_dimensions[col_letter].width = min(max(max_len + 4, 12), 40)


def generate_styled_excel(results: list) -> bytes:
    df_out = pd.DataFrame(results)
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_out.to_excel(writer, index=False, sheet_name="BOM_Procurement_Master")
        ws = writer.sheets["BOM_Procurement_Master"]
        _style_excel_sheet(ws, is_template=False)

    return output.getvalue()