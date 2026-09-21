import io
import re
import time
import base64
import requests
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ==========================================
# 1. TẠO FILE BOM TEMPLATE CHUẨN MẪU
# ==========================================
def generate_sample_bom_template() -> bytes:
    data = [
        {"STT": 1, "Designator": "U1", "MPN": "STM32F407VGT6", "Quantity": 500, "Manufacturer": "STMicroelectronics", "Description": "MCU 32-bit ARM Cortex-M4 1MB Flash LQFP-100", "Footprint": "LQFP-100"},
        {"STT": 2, "Designator": "U2", "MPN": "ESP32-WROOM-32E", "Quantity": 1000, "Manufacturer": "Espressif Systems", "Description": "Module Wi-Fi + BLE 4MB Flash SMD", "Footprint": "MODULE-SMD"},
        {"STT": 3, "Designator": "U3", "MPN": "ATMEGA328P-AU", "Quantity": 200, "Manufacturer": "Microchip", "Description": "MCU 8-bit AVR 32KB Flash TQFP-32", "Footprint": "TQFP-32"},
        {"STT": 4, "Designator": "U4", "MPN": "AMS1117-3.3", "Quantity": 2000, "Manufacturer": "Advanced Monolithic", "Description": "IC LDO Reg 3.3V 1A SOT-223", "Footprint": "SOT-223"},
        {"STT": 5, "Designator": "U5", "MPN": "CH340G", "Quantity": 500, "Manufacturer": "WCH", "Description": "USB to Serial Bridge Controller SOP-16", "Footprint": "SOP-16"},
        {"STT": 6, "Designator": "U6", "MPN": "LM358DR", "Quantity": 800, "Manufacturer": "Texas Instruments", "Description": "Dual Op-Amp 1MHz SOIC-8", "Footprint": "SOIC-8"},
        {"STT": 7, "Designator": "R1, R2", "MPN": "0603WAF1002T5E", "Quantity": 5000, "Manufacturer": "UniOhm", "Description": "SMD Resistor 10k Ohm 1% 1/10W 0603", "Footprint": "0603"},
        {"STT": 8, "Designator": "C1, C2", "MPN": "CL10A106KP8NNNC", "Quantity": 5000, "Manufacturer": "Samsung Electro-Mechanics", "Description": "SMD Capacitor 10uF 10V X5R 0603", "Footprint": "0603"}
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
    """Lọc bỏ toàn bộ thông tin đóng gói, chứng chỉ để trích xuất thông số cốt lõi"""
    if not desc or desc == "-":
        return ""
    
    # Danh sách từ gây nhiễu
    noise_words = [
        "rohs", "rohs3", "pb free", "lead free", "pb-free", "compliant",
        "reel", "tape", "cut tape", "digi-reel", "tube", "tray", "bulk",
        "ic", "smd", "smt", "through hole", "tht", "standard", "generic",
        "original", "brand new", "package", "series", "commercial"
    ]
    
    text = desc.lower()
    for w in noise_words:
        text = re.sub(rf"\b{re.escape(w)}\b", " ", text)
    
    # Loại bỏ ký tự đặc biệt không cần thiết
    text = re.sub(r"[,;:/\\()\[\]{}*+]", " ", text)
    tokens = [w.strip() for w in text.split() if len(w.strip()) > 1]
    
    # Giữ lại tối đa 4 từ khóa thông số kỹ thuật cốt lõi nhất
    return " ".join(tokens[:4])


def is_different_manufacturer(mfg1: str, mfg2: str) -> bool:
    """Kiểm tra 2 nhà sản xuất có khác nhau không (loại bỏ biến thể tên công ty)"""
    if not mfg1 or not mfg2 or mfg1 == "-" or mfg2 == "-":
        return True
    
    clean_1 = re.sub(r"(inc|corp|corporation|ltd|limited|llc|co|electronics|systems|microelectronics|semiconductor)", "", mfg1.lower()).strip()
    clean_2 = re.sub(r"(inc|corp|corporation|ltd|limited|llc|co|electronics|systems|microelectronics|semiconductor)", "", mfg2.lower()).strip()
    
    if not clean_1 or not clean_2:
        return mfg1.lower().strip() != mfg2.lower().strip()
        
    return clean_1 not in clean_2 and clean_2 not in clean_1


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
            err_details = res.text[:200]
            if debug_logs is not None:
                debug_logs.append(f"❌ [DigiKey Auth Lỗi {res.status_code}]: {err_details}")
            return None

        d = res.json()
        _DIGIKEY_CACHE["token"] = d.get("access_token")
        _DIGIKEY_CACHE["expires_at"] = now + d.get("expires_in", 86400) - 120
        if debug_logs is not None:
            debug_logs.append("🔑 [DigiKey] Cấp phát Access Token thành công.")
        return _DIGIKEY_CACHE["token"]
    except Exception as e:
        if debug_logs is not None:
            debug_logs.append(f"❌ [DigiKey Auth Exception]: {e}")
        return None


def search_digikey_alternates_by_keyword(client_id: str, client_secret: str, keyword: str, exclude_mpn: str, exclude_mfg: str, target_qty: int) -> list:
    """Tìm mã tương đương trên DigiKey: khác nhà sản xuất, ưu tiên còn hàng"""
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
            
            # Bắt buộc: Khác nhà sản xuất với mã gốc
            if not is_different_manufacturer(exclude_mfg, mfg_name):
                continue
                
            stock = p.get("QuantityAvailable", 0) or 0
            
            # Parse đơn giá
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
                "source": "DigiKey"
            })
            
        # Sắp xếp ưu tiên: Còn stock trước -> Tồn kho giảm dần
        candidates.sort(key=lambda x: (x["stock"] <= 0, -x["stock"]))
        return candidates
    except Exception:
        return []


def query_digikey(client_id: str, client_secret: str, mpn: str, target_qty: int, debug_logs: list = None) -> dict:
    cid = client_id.strip()
    csec = client_secret.strip()
    if not cid or not csec:
        if debug_logs is not None:
            debug_logs.append("ℹ️ [DigiKey] Bỏ qua vì chưa cấu hình Client ID/Secret.")
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
            if debug_logs is not None:
                debug_logs.append(f"ℹ️ [DigiKey] Không tìm thấy mã '{clean_mpn}' -> Chuyển Mouser.")
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
            debug_logs.append(f"✅ [DigiKey Primary] '{clean_mpn}': Kho {stock} | Giá {p_log}")

        return {
            "description": desc,
            "manufacturer": mfg,
            "lifecycle": "Active",
            "datasheet": best_p.get("DatasheetUrl", ""),
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
        if debug_logs is not None:
            debug_logs.append(f"⚠️ [DigiKey Exception] '{clean_mpn}': {e} -> Chuyển Mouser.")
        return {}


# ==========================================
# 4. MOUSER SEARCH ENGINES (ĐỐI SÁNH & CROSS-REF BỔ TRỢ)
# ==========================================
def search_mouser_alternates_by_keyword(api_key: str, keyword: str, exclude_mpn: str, exclude_mfg: str, target_qty: int) -> list:
    """Tìm mã tương đương trên Mouser: khác nhà sản xuất, ưu tiên còn hàng"""
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
                "source": "Mouser"
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
            if debug_logs is not None:
                debug_logs.append(f"⚠️ [Mouser HTTP {res.status_code}] '{clean_mpn}'.")
            return {}
        data = res.json()
        parts = data.get("SearchResults", {}).get("Parts", [])
        if not parts:
            if debug_logs is not None:
                debug_logs.append(f"ℹ️ [Mouser] Không tìm thấy mã '{clean_mpn}'.")
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
            debug_logs.append(f"✅ [Mouser Secondary] '{clean_mpn}': Kho {stock} | Giá {p_log}")

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
    except Exception as e:
        if debug_logs is not None:
            debug_logs.append(f"⚠️ [Mouser Exception] '{clean_mpn}': {e}")
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
        if debug_logs is not None and offers:
            debug_logs.append(f"✅ [OEMsecrets] '{clean_mpn}': Nhận {len(offers)} báo giá.")
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
    """Thuật toán tìm mã tương đương: Lọc mô tả -> DigiKey -> Fallback sang Mouser"""
    if not keyword:
        return []
        
    alternates = []
    seen_mpns = {exclude_mpn.lower()}
    seen_mfgs = set()

    # 1. Quét trước trên DigiKey
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

    # 2. Nếu DigiKey chưa đủ 2 mã khác hãng, gọi tiếp Mouser để bổ sung
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


def process_bom_data(df: pd.DataFrame, mpn_col: str, qty_col: str, des_col: str, config: dict, progress_bar=None, status_text=None, debug_logs: list = None) -> list:
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

        # ====================================================
        # BƯỚC 1: TRUY VẤN DIGIKEY (ƯU TIÊN 1 - CHUẨN THAM CHIẾU)
        # ====================================================
        dk_res = query_digikey(config.get("digikey_id", ""), config.get("digikey_secret", ""), mpn, qty, debug_logs)
        if dk_res:
            description = dk_res.get("description") or description
            mfg = dk_res.get("manufacturer") or mfg
            lifecycle = dk_res.get("lifecycle") or lifecycle
            datasheet = dk_res.get("datasheet") or datasheet
            all_offers.extend(dk_res.get("offers", []))

        # ====================================================
        # BƯỚC 2: TRUY VẤN MOUSER (ƯU TIÊN 2 - ĐỐI SÁNH GIÁ)
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
        # BƯỚC 3: TÌM MÃ TƯƠNG ĐƯƠNG (KHÁC NSX, ƯU TIÊN CÒN KHO)
        # ====================================================
        clean_kw = clean_description_for_search(description)
        alternates = fetch_cross_references(clean_kw, mpn, mfg, qty, config)

        if debug_logs is not None:
            if alternates:
                alt_names = [f"{a['mpn']} ({a['manufacturer']} | Kho: {a['stock']})" for a in alternates]
                debug_logs.append(f"💡 [Cross-Ref] Tìm thấy {len(alternates)} mã thay thế khác hãng: {', '.join(alt_names)}")
            else:
                debug_logs.append("ℹ️ [Cross-Ref] Không tìm thấy mã tương đương khác hãng phù hợp.")

        # ====================================================
        # BƯỚC 4: OEMSECRETS & NEXAR (DỰ PHÒNG KHI CẦN)
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

        # Tách riêng Mã tương đương 2 & 3
        alt_2 = alternates[0] if len(alternates) > 0 else {}
        alt_3 = alternates[1] if len(alternates) > 1 else {}

        # Sắp xếp ưu tiên: Sẵn đủ hàng trước -> Đơn giá thấp nhất
        all_offers.sort(key=lambda x: (not x["is_stock_enough"], x["price"] if x["price"] is not None else 999999))

        # Chọn Top 2 NCC độc lập (NCC 1 tối ưu và NCC 2)
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
            "Nhà Sản Xuất": mfg,
            "Vòng Đời": lifecycle,
            "SL Mua": qty,
            "Tổng Tồn Kho": total_stock,
            "Trạng Thái Cung Ứng": status,
            "Ước Tính Tổng Tiền": total_cost_str,

            # Báo giá NCC 1 (Tối ưu nhất giữa DigiKey và Mouser)
            "NCC 1 (Tối ưu)": d1["distributor"] if d1 else "-",
            "Đơn Giá 1": price_display,
            "Kho NCC 1": d1["stock"] if d1 else 0,
            "Lead Time 1": d1["lead_time"] if d1 else "-",

            # Báo giá NCC 2 (Để so sánh trực tiếp)
            "NCC 2": d2["distributor"] if d2 else "-",
            "Đơn Giá 2": f"{d2['price']} {d2['currency']}" if d2 and d2["price"] is not None else "-",
            "Kho NCC 2": d2["stock"] if d2 else 0,
            "Lead Time 2": d2["lead_time"] if d2 else "-",

            # TÁCH RIÊNG: MÃ TƯƠNG ĐƯƠNG 2 (KHÁC NSX, CÓ SẴN HÀNG)
            "Mã Tương Đương 2": alt_2.get("mpn", "-"),
            "NSX Mã 2": alt_2.get("manufacturer", "-"),
            "Kho Mã 2": alt_2.get("stock", 0),
            "Đơn Giá Mã 2": alt_2.get("price", "-"),

            # TÁCH RIÊNG: MÃ TƯƠNG ĐƯƠNG 3 (KHÁC NSX, CÓ SẴN HÀNG)
            "Mã Tương Đương 3": alt_3.get("mpn", "-"),
            "NSX Mã 3": alt_3.get("manufacturer", "-"),
            "Kho Mã 3": alt_3.get("stock", 0),
            "Đơn Giá Mã 3": alt_3.get("price", "-"),

            "Datasheet": datasheet
        })

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
        for cell in col:
            val_str = str(cell.value or '')
            if len(val_str) > max_len:
                max_len = len(val_str)
        ws.column_dimensions[col_letter].width = min(max(max_len + 4, 12), 40)


def generate_styled_excel(results: list) -> bytes:
    df_out = pd.DataFrame(results)
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_out.to_excel(writer, index=False, sheet_name="BOM_Procurement_Master")
        ws = writer.sheets["BOM_Procurement_Master"]
        _style_excel_sheet(ws, is_template=False)

    return output.getvalue()