import io
import zipfile
import tempfile
import os
import time
import random
import re
import shutil
import subprocess
import requests
import json
import pandas as pd
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.drawing.image import Image as OpenpyxlImage
from PIL import Image as PILImage, ImageDraw

import google.generativeai as genai

PILImage.MAX_IMAGE_PIXELS = None

def get_layer_name(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    name_no_ext = os.path.splitext(filename)[0].upper()
    name_lower = filename.lower()
    
    ext_map = {
        '.gtl': 'Top_Copper', '.gbl': 'Bottom_Copper',
        '.gto': 'Top_Silkscreen', '.gbo': 'Bottom_Silkscreen',
        '.gts': 'Top_Solder_Mask', '.gbs': 'Bottom_Solder_Mask',
        '.gtp': 'Top_Solder_Paste', '.gbp': 'Bottom_Solder_Paste',
        '.gko': 'Board_Outline', '.gm1': 'Mechanical_1'
    }
    if ext in ext_map: return ext_map[ext]
    
    if ext in ['.gbr', '.ger', '.art']:
        if any(k in name_lower for k in ['smask', 'mask', 'smt', 'smb', 'stc', 'sts']):
            if any(k in name_lower for k in ['top', 'f_', 'smt', 'stc', 'front']): return 'Top_Solder_Mask'
            if any(k in name_lower for k in ['bot', 'b_', 'smb', 'sts', 'back']): return 'Bottom_Solder_Mask'
            return 'Solder_Mask'
            
        if any(k in name_lower for k in ['silk', 'sst', 'ssb', 'plc', 'pls']):
            if any(k in name_lower for k in ['top', 'f_', 'sst', 'plc', 'front']): return 'Top_Silkscreen'
            if any(k in name_lower for k in ['bot', 'b_', 'ssb', 'pls', 'back']): return 'Bottom_Silkscreen'
            return 'Silkscreen'

        if any(k in name_lower for k in ['paste', 'spt', 'spb']):
            if any(k in name_lower for k in ['top', 'f_', 'spt', 'front']): return 'Top_Solder_Paste'
            if any(k in name_lower for k in ['bot', 'b_', 'spb', 'back']): return 'Bottom_Solder_Paste'
            return 'Solder_Paste'
            
        if any(k in name_lower for k in ['edge', 'outline', 'board', 'mech', 'dim']): return 'Board_Outline'
        
        if name_no_ext in ['TOP', 'COMP', 'CMP'] or 'f_cu' in name_lower: return 'Top_Copper'
        if name_no_ext in ['BOTTOM', 'SOLD', 'SOL'] or 'b_cu' in name_lower: return 'Bottom_Copper'
        
        if re.match(r'^L\d+', name_no_ext) or any(k in name_lower for k in ['gnd', 'pwr', 'vcc', 'in1', 'in2', 'inner']):
            return f"Inner_Copper_{name_no_ext}"
            
        return f"Other_{name_no_ext}"
    return None

def group_uploaded_files(uploaded_files) -> list:
    jobs = []
    loose_files = []
    for file in uploaded_files:
        ext = file.name.split('.')[-1].lower()
        if ext in ['zip', 'rar']:
            jobs.append({"name": file.name, "files": [file], "type": "archive"})
        else:
            loose_files.append(file)
    if loose_files:
        jobs.append({"name": "Loose_Gerber_Files.zip", "files": loose_files, "type": "loose"})
    return jobs

def prepare_gerber_zip(job_files, debug_logs: list = None, status_callback=None) -> bytes:
    if debug_logs is None: debug_logs = []
    if status_callback: status_callback("Đang xử lý và chuẩn bị cấu trúc gói dữ liệu...")
    
    if len(job_files) == 1:
        file = job_files[0]
        ext = file.name.split('.')[-1].lower()
        if ext == 'zip': return file.getvalue()
        elif ext == 'rar':
            if status_callback: status_callback("Đang bung nén tệp RAR để tái cấu trúc...")
            try:
                import rarfile
                if os.name == 'nt':
                    current_dir = os.path.dirname(os.path.abspath(__file__))
                    root_dir = os.path.abspath(os.path.join(current_dir, "..", "..")) 
                    unrar_path = os.path.join(root_dir, "UnRAR.exe")
                    rarfile.UNRAR_TOOL = unrar_path
                with tempfile.NamedTemporaryFile(delete=False, suffix=".rar") as temp_rar:
                    temp_rar.write(file.getvalue())
                    temp_rar_path = temp_rar.name
                zip_buffer = io.BytesIO()
                try:
                    with rarfile.RarFile(temp_rar_path) as rf:
                        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                            for f in rf.infolist():
                                if not f.is_dir(): zip_file.writestr(f.filename, rf.read(f))
                finally:
                    if os.path.exists(temp_rar_path): os.remove(temp_rar_path)
                return zip_buffer.getvalue()
            except Exception as e:
                debug_logs.append(f"❌ Lỗi giải nén RAR: {e}")
                raise ValueError(f"Không thể giải nén file RAR: {e}")
        else:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                zip_file.writestr(file.name, file.getvalue())
            return zip_buffer.getvalue()

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        for file in job_files: zip_file.writestr(file.name, file.getvalue())
    return zip_buffer.getvalue()

def render_gerber_images_and_calc(zip_data: bytes, debug_logs: list = None, status_callback=None) -> tuple:
    if debug_logs is None: debug_logs = []
    layer_images = []
    internal_params = {"layer_count": 0, "width_mm": 0.0, "height_mm": 0.0}
    ai_context_assets = [] # Chứa hỗn hợp cả Text (String) và Hình ảnh PDF (PIL.Image)
    
    if os.name == 'nt':
        current_dir = os.path.dirname(os.path.abspath(__file__))
        root_dir = os.path.abspath(os.path.join(current_dir, "..", ".."))
        gerbv_cmd = os.path.join(root_dir, "gerbv", "bin", "gerbv.exe")
        if not os.path.exists(gerbv_cmd): return [], internal_params, []
    else:
        gerbv_cmd = "gerbv"
        
    temp_dir = tempfile.mkdtemp()
    copper_count = 0
    smask_files = []
    copper_files = []
    seen_layers = set()
    
    try:
        with zipfile.ZipFile(io.BytesIO(zip_data), "r") as zip_ref:
            zip_ref.extractall(temp_dir)
            
        if status_callback: status_callback("Đang phân tích vector và bóc tách dữ liệu Đa phương thức (Text/Logs/PDF)...")
        
        for root, _, files in os.walk(temp_dir):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                input_path = os.path.join(root, file)
                
                # --- XỬ LÝ TEXT THÔNG THƯỜNG ---
                if ext in ['.txt', '.log', '.rpt', '.drl', '.rou', '.inf']:
                    try:
                        with open(input_path, 'r', encoding='utf-8', errors='ignore') as f:
                            ai_context_assets.append(f"--- Nội dung file {file} ---\n{f.read()[:5000]}")
                            debug_logs.append(f"📝 Đã thu thập text từ file: {file}")
                    except: pass
                    
                # --- XỬ LÝ PDF (TEXT HOẶC OCR VISION) ---
                elif ext == '.pdf':
                    try:
                        import fitz  # PyMuPDF
                        doc = fitz.open(input_path)
                        extracted_text = ""
                        # Ưu tiên lấy Text trước (Tối đa 10 trang)
                        for i in range(min(len(doc), 10)): 
                            extracted_text += doc[i].get_text() + "\n"
                            
                        if len(extracted_text.strip()) > 50:
                            ai_context_assets.append(f"--- Nội dung PDF {file} ---\n{extracted_text}")
                            debug_logs.append(f"📑 Đã bóc tách thành công text từ PDF: {file}")
                        else:
                            # PDF không chứa Text (Ảnh Scan) -> Render hình ảnh nạp cho Gemini Vision
                            debug_logs.append(f"👁️ Phát hiện PDF dạng ảnh Scan ({file}). Đang kích hoạt kết xuất ảnh cho AI Vision...")
                            ai_context_assets.append(f"--- Hình ảnh Scan từ tài liệu PDF: {file} ---")
                            
                            # Cắt tối đa 3 trang đầu dưới dạng ảnh sắc nét (DPI 150)
                            for i in range(min(len(doc), 3)):
                                pix = doc[i].get_pixmap(dpi=150)
                                img_data = pix.tobytes("png")
                                img_pil = PILImage.open(io.BytesIO(img_data))
                                ai_context_assets.append(img_pil)
                                
                    except ImportError:
                        debug_logs.append(f"⚠️ Không thể đọc PDF {file}. Hệ thống thiếu thư viện PyMuPDF. Hãy chạy: pip install PyMuPDF")
                    except Exception as e:
                        debug_logs.append(f"⚠️ Lỗi trong quá trình xử lý PDF {file}: {e}")

                # --- XỬ LÝ GERBER VECTOR ---
                layer_name = get_layer_name(file)
                if layer_name:
                    if layer_name in seen_layers: continue
                    seen_layers.add(layer_name)
                    
                    if "Copper" in layer_name:
                        copper_count += 1
                        copper_files.append(input_path)
                    elif "Solder_Mask" in layer_name:
                        smask_files.append(input_path)
                        
                    output_png = os.path.join(temp_dir, f"{layer_name}_{random.randint(1000,9999)}.png")
                    try:
                        subprocess.run([gerbv_cmd, "-x", "png", "-a", "-o", output_png, "--dpi=150", "--background=#FFFFFF", "--foreground=#005500", input_path], check=True, capture_output=True)
                        if os.path.exists(output_png):
                            with PILImage.open(output_png) as img:
                                if img.width > 2000 or img.height > 2000:
                                    img.thumbnail((2000, 2000), PILImage.Resampling.LANCZOS)
                                    img.save(output_png, format="PNG")
                            with open(output_png, "rb") as f:
                                layer_images.append({"name": layer_name, "filename": file, "data": f.read()})
                    except: pass
                        
        internal_params["layer_count"] = copper_count if copper_count > 0 else 2
        
        target_files = smask_files if smask_files else copper_files
        if target_files:
            try:
                svg_path = os.path.join(temp_dir, "calc_dim.svg")
                subprocess.run([gerbv_cmd, "-x", "svg", "-a", "-o", svg_path] + target_files, check=True, capture_output=True)
                if os.path.exists(svg_path):
                    with open(svg_path, 'r', encoding='utf-8') as f: svg_str = f.read()
                    match_w = re.search(r'width="([\d.]+)([a-zA-Z]*)"', svg_str)
                    match_h = re.search(r'height="([\d.]+)([a-zA-Z]*)"', svg_str)
                    if match_w and match_h:
                        def to_mm(val, unit):
                            if unit == 'in': return val * 25.4
                            if unit == 'pt': return val * 25.4 / 72.0
                            if unit == 'cm': return val * 10.0
                            if unit == 'px' or not unit: return val * 25.4 / 96.0
                            return val
                        internal_params["width_mm"] = round(to_mm(float(match_w.group(1)), match_w.group(2).lower()), 2)
                        internal_params["height_mm"] = round(to_mm(float(match_h.group(1)), match_h.group(2).lower()), 2)
                        debug_logs.append(f"✅ gerbv đo đạc vector xong: X={internal_params['width_mm']}mm, Y={internal_params['height_mm']}mm")
            except: pass

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        
    layer_images.sort(key=lambda x: ("Top" not in x["name"], "Bottom" not in x["name"], x["name"]))
    return layer_images, internal_params, ai_context_assets

def analyze_with_gemini_ai(ai_context_assets: list, internal_params: dict, mf_params: dict, gemini_api_keys: list, debug_logs: list, status_callback=None) -> dict:
    if not gemini_api_keys:
        debug_logs.append("⚠️ Không có cấu hình GEMINI_API_KEYS. Bỏ qua luồng phân tích AI.")
        return None
    
    if status_callback: status_callback("🧠 Kích hoạt Gemini AI: Đang phân tích Chuyên sâu (Vision & Text) tài liệu sản xuất...")
    
    keys_to_try = list(gemini_api_keys)
    random.shuffle(keys_to_try)
    
    instruction_text = f"""
    Bạn là một kỹ sư chuyên gia về CAM (Computer-Aided Manufacturing) và DFM cho bo mạch PCB.
    Tôi đang xử lý một dự án PCB và thu thập được các số liệu từ máy móc như sau:
    
    1. Số liệu do công cụ vector nội bộ đo được:
    - Số lớp đồng đếm được: {internal_params.get('layer_count')}
    - Kích thước đo đạc: {internal_params.get('width_mm')} mm x {internal_params.get('height_mm')} mm
    
    2. Số liệu từ API máy chủ sản xuất MacroFab trả về:
    {json.dumps(mf_params, ensure_ascii=False) if mf_params else "API không trả về thông tin hợp lệ."}
    
    Dưới đây là NỘI DUNG VĂN BẢN VÀ HÌNH ẢNH TRÍCH XUẤT TỪ CÁC TÀI LIỆU LOG, PDF KÈM THEO:
    """

    task_text = """
    NHIỆM VỤ CỦA BẠN:
    Phân tích nội dung tài liệu (cả chữ và ảnh) kết hợp với số đo của máy móc để đưa ra kết luận THỰC TẾ VÀ CHÍNH XÁC NHẤT về bo mạch. 
    Nếu các file Log hoặc bản PDF ghi rõ thông số, hãy ưu tiên các tài liệu này.
    
    BẠN BẮT BUỘC CHỈ TRẢ VỀ DUY NHẤT 1 CHUỖI JSON THEO CẤU TRÚC SAU:
    {
        "layer_count": "số nguyên hoặc chuỗi ghi rõ khác biệt",
        "dimensions_mm": "chuỗi, ví dụ: 120.5 x 85.2 mm",
        "board_thickness": "chuỗi, ví dụ: 1.6 mm",
        "material": "chuỗi vật liệu, ví dụ: FR-4",
        "surface_finish": "chuỗi bề mặt, ví dụ: ENIG hoặc HASL",
        "copper_weight": "chuỗi độ dày đồng, vd: 1 oz",
        "smt_technology": "chuỗi, SMT hoặc THT",
        "total_holes": "số nguyên",
        "plated_holes": "số nguyên",
        "non_plated_holes": "số nguyên",
        "ipc_errors": "số nguyên",
        "ipc_warnings": "số nguyên",
        "ai_reasoning": "Một câu giải thích ngắn gọn bằng tiếng Việt về cơ sở chốt số liệu."
    }
    """
    
    # Hợp nhất Dữ liệu Đa phương thức (Text String + Hình ảnh PIL)
    prompt = [instruction_text]
    prompt.extend(ai_context_assets)
    prompt.append(task_text)
    
    for attempt, key in enumerate(keys_to_try):
        try:
            debug_logs.append(f"\n🔄 [KEY {attempt+1}/{len(keys_to_try)}] Đang mở kết nối Gemini AI...")
            genai.configure(api_key=key)
            
            available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods and 'gemini' in m.name.lower()]
            if not available_models:
                debug_logs.append(f"⚠️ Key {attempt+1} hợp lệ nhưng không được cấp quyền chạy Model nào.")
                continue

            def model_sort_key(m_name):
                nums = re.findall(r'\d+\.\d+', m_name)
                version = float(nums[0]) if nums else 0.0
                
                stability = 3
                if 'preview' in m_name.lower() or 'exp' in m_name.lower(): stability = 1
                elif 'latest' in m_name.lower(): stability = 2
                
                tier = 2 if 'flash' in m_name.lower() else 1
                
                return (version, stability, tier, m_name)

            available_models.sort(key=model_sort_key, reverse=True)
            top_5_models = available_models[:5]
            
            debug_logs.append(f"🔍 Top 5 Model được xếp hạng: {', '.join([m.replace('models/', '') for m in top_5_models])}")
            
            for model_idx, selected_model in enumerate(top_5_models):
                debug_logs.append(f"⚡ Đang nạp Model [{model_idx+1}/5]: {selected_model}")
                try:
                    generation_config = genai.types.GenerationConfig(response_mime_type="application/json")
                    model = genai.GenerativeModel(model_name=selected_model, generation_config=generation_config)
                    
                    max_retries = 3
                    for retry in range(max_retries):
                        try:
                            if status_callback: status_callback(f"AI đang phân tích DFM chuyên sâu bằng {selected_model.replace('models/', '')} (Thử lần {retry+1})...")
                            
                            response = model.generate_content(prompt)
                            raw_text = response.text.replace('```json', '').replace('```', '').strip()
                            parsed_json = json.loads(raw_text)
                            
                            debug_logs.append(f"✅ AI phân tích thành công! Lời phê: {parsed_json.get('ai_reasoning')}")
                            return parsed_json
                            
                        except Exception as inner_e:
                            error_str = str(inner_e).lower()
                            if "429" in error_str or "quota" in error_str or "exhausted" in error_str or "404" in error_str:
                                debug_logs.append(f"⚠️ Model {selected_model} bị giới hạn Quota hoặc không cấp quyền. Chuyển Model khác...")
                                break 
                                
                            debug_logs.append(f"⚠️ Lỗi mạng tạm thời: {inner_e}")
                            if retry < max_retries - 1: time.sleep(3)
                            else: debug_logs.append(f"❌ Bỏ qua Model {selected_model} do đứt kết nối.")
                except Exception as me:
                    debug_logs.append(f"⚠️ Lỗi nạp Model {selected_model}: {me}")
                    
            debug_logs.append(f"❌ Toàn bộ 5 Model siêu việt nhất trên Key {attempt+1} đều từ chối yêu cầu do cạn Quota. Chuyển API Key...")
            
        except Exception as e:
            debug_logs.append(f"⚠️ Lỗi cấu hình tại Key thứ {attempt+1}: {e}")
            
    debug_logs.append("🚨 TẤT CẢ API KEYS ĐỀU ĐÃ SỤP ĐỔ (Cạn Quota). Hệ thống sẽ dùng số liệu tính toán nội bộ.")
    return None

def upload_and_analyze_gerber(mf_api_key: str, gemini_api_keys: list, pcb_name: str, zip_data: bytes, debug_logs: list = None, status_callback=None):
    if debug_logs is None: debug_logs = []
    
    layer_images, internal_params, ai_context_assets = render_gerber_images_and_calc(zip_data, debug_logs, status_callback)

    mf_params = {}
    if mf_api_key and mf_api_key != "DUMMY_KEY":
        if status_callback: status_callback("Đang kết nối API máy chủ MacroFab...")
        try:
            headers = {"Authorization": f"Bearer {mf_api_key}", "Accept": "application/json"}
            res_create = requests.post("https://factory.macrofab.com/api/v2/pcbs", json={"name": pcb_name}, headers=headers, timeout=15)
            if res_create.status_code in [200, 201]:
                pcb_id = res_create.json().get("PCB_id") or res_create.json().get("id")
                upload_url = f"https://factory.macrofab.com/api/v2/pcbs/{pcb_id}/archive"
                files = {'file': (f"{pcb_name}.zip", zip_data, 'application/zip')}
                res_upload = requests.post(upload_url, files=files, headers=headers, timeout=30)
                if res_upload.status_code in [200, 201]:
                    for attempt in range(4):
                        time.sleep(6) 
                        res_info = requests.get(f"https://factory.macrofab.com/api/v2/pcbs/{pcb_id}", headers=headers, timeout=15)
                        if res_info.status_code == 200:
                            pcb_data = res_info.json().get("pcb", res_info.json())
                            if pcb_data.get("layer_count", 0) > 0:
                                mf_params = {
                                    "layer_count": pcb_data.get("layer_count", 0),
                                    "width_mm": round(pcb_data.get("width", 0) * 0.0254, 2),
                                    "height_mm": round(pcb_data.get("height", 0) * 0.0254, 2),
                                    "thickness": pcb_data.get("thickness", "1.6 mm"),
                                    "smt": "SMT" if pcb_data.get("smt_sides") else "THT"
                                }
                                break
        except: pass

    ai_params = None
    if ai_context_assets:
        ai_params = analyze_with_gemini_ai(ai_context_assets, internal_params, mf_params, gemini_api_keys, debug_logs, status_callback)
    
    final_params = {}
    warnings = []
    
    if ai_params:
        final_params = {
            "Số lớp Đồng (Layer Count)": ai_params.get("layer_count"),
            "Kích thước X/Y": ai_params.get("dimensions_mm"),
            "Độ dày mạch (Board Thickness)": ai_params.get("board_thickness"),
            "Vật liệu nền (Material)": ai_params.get("material", "FR-4"),
            "Bề mặt (Surface Finish)": ai_params.get("surface_finish", "Không ghi nhận"),
            "Độ dày đồng (Copper Weight)": ai_params.get("copper_weight", "Không ghi nhận"),
            "Công nghệ hàn (Assembly)": ai_params.get("smt_technology"),
            "Tổng số lỗ khoan (Total Holes)": ai_params.get("total_holes"),
            "Lỗ mạ xuyên (Plated)": ai_params.get("plated_holes"),
            "Lỗ không mạ (Non-Plated)": ai_params.get("non_plated_holes"),
            "💡 Đánh giá của AI": ai_params.get("ai_reasoning")
        }
        if ai_params.get("ipc_warnings", 0) > 0 or ai_params.get("ipc_errors", 0) > 0:
            warnings.append(f"AI nhận diện IPC-D-356: {ai_params.get('ipc_errors')} lỗi và {ai_params.get('ipc_warnings')} cảnh báo.")
    else:
        int_layers = internal_params.get("layer_count", 0)
        mf_layers = mf_params.get("layer_count", 0)
        int_w = internal_params.get("width_mm", 0)
        int_h = internal_params.get("height_mm", 0)
        mf_w = mf_params.get("width_mm", 0)
        mf_h = mf_params.get("height_mm", 0)

        merged_layers = f"{mf_layers} (API) / {int_layers} (Nội bộ)" if (mf_layers > 0 and int_layers > 0 and mf_layers != int_layers) else (mf_layers if mf_layers > 0 else int_layers)
        merged_w = f"{mf_w} (API) / {int_w} (Nội bộ)" if (mf_w > 0 and int_w > 0 and abs(mf_w - int_w) > 2.0) else (mf_w if mf_w > 0 else (int_w if int_w > 0 else "N/A"))
        merged_h = f"{mf_h} (API) / {int_h} (Nội bộ)" if (mf_h > 0 and int_h > 0 and abs(mf_h - int_h) > 2.0) else (mf_h if mf_h > 0 else (int_h if int_h > 0 else "N/A"))
        
        final_params = {
            "Số lớp Đồng (Layer Count)": merged_layers,
            "Kích thước X (Width - mm)": merged_w,
            "Kích thước Y (Height - mm)": merged_h,
            "Độ dày mạch (Board Thickness)": mf_params.get("thickness", "1.6 mm"),
            "Công nghệ hàn (Assembly)": mf_params.get("smt", "Chưa xác định")
        }

    return {
        "status": "success",
        "pcb_name": pcb_name,
        "parameters": final_params,
        "dfm_warnings": warnings,
        "layer_images": layer_images
    }

def generate_pcb_report_excel(results: list) -> bytes:
    if not results: return b""
    flat_data = []
    for idx, res in enumerate(results, 1):
        params = res.get("parameters", {})
        warnings = res.get("dfm_warnings", [])
        row = {
            "STT": idx,
            "Tên Bo Mạch (Gerber File)": res.get("pcb_name", "-"),
            "Trạng Thái DFM": "🔴 Cảnh báo" if warnings else "🟢 PASS",
            "Cảnh Báo & Rủi Ro DFM": "\n".join(warnings) if warnings else "Không có rủi ro",
        }
        for k, v in params.items(): row[k] = v
        flat_data.append(row)
        
    df = pd.DataFrame(flat_data)
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="DFM_Report")
        ws = writer.sheets["DFM_Report"]
        wb = writer.book
        
        font_header = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
        font_data = Font(name="Segoe UI", size=10)
        fill_header = PatternFill(start_color="203764", end_color="203764", fill_type="solid")
        fill_alt = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
        thin_border = Border(left=Side(style='thin', color="D9D9D9"), right=Side(style='thin', color="D9D9D9"), top=Side(style='thin', color="D9D9D9"), bottom=Side(style='thin', color="D9D9D9"))
        align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)
        align_left = Alignment(horizontal="left", vertical="center", wrap_text=True)
        
        ws.row_dimensions[1].height = 30
        for cell in ws[1]:
            cell.font = font_header
            cell.fill = fill_header
            cell.alignment = align_center
            cell.border = thin_border
            
        for row_idx, row in enumerate(ws.iter_rows(min_row=2), start=2):
            is_even = (row_idx % 2 == 0)
            ws.row_dimensions[row_idx].height = 45 if "\n" in str(row[3].value) else 25
            for col_idx, cell in enumerate(row, start=1):
                cell.font = font_data
                cell.border = thin_border
                cell.alignment = align_left if col_idx in [2, 4] else align_center
                if is_even: cell.fill = fill_alt
                    
        for col in ws.columns:
            col_letter = get_column_letter(col[0].column)
            header_name = str(col[0].value or "")
            if header_name == "STT": ws.column_dimensions[col_letter].width = 8
            elif header_name == "Tên Bo Mạch (Gerber File)": ws.column_dimensions[col_letter].width = 30
            elif header_name == "Cảnh Báo & Rủi Ro DFM": ws.column_dimensions[col_letter].width = 60
            elif "Đánh giá từ AI" in header_name: ws.column_dimensions[col_letter].width = 50
            else: ws.column_dimensions[col_letter].width = 25

        for res in results:
            pcb_name = res.get("pcb_name", "Unknown")
            safe_sheet_name = re.sub(r'[\\/*?:\[\]]', '_', pcb_name)[:30]
            if safe_sheet_name in wb.sheetnames:
                safe_sheet_name = f"{safe_sheet_name[:26]}_{random.randint(100, 999)}"
                
            ws_img = wb.create_sheet(title=safe_sheet_name)
            ws_img.column_dimensions['A'].width = 80
            
            layer_images = res.get("layer_images", [])
            current_row = 1
            if not layer_images:
                ws_img.cell(row=1, column=1, value="Không tìm thấy ảnh kết xuất cho bo mạch này.")
                continue
                
            for img_info in layer_images:
                layer_name = img_info["name"]
                orig_file = img_info["filename"]
                img_data = img_info["data"]
                
                title_cell = ws_img.cell(row=current_row, column=1, value=f"Hình ảnh: {layer_name} (File gốc: {orig_file})")
                title_cell.font = Font(name="Segoe UI", size=14, bold=True, color="203764")
                
                try:
                    img_stream = io.BytesIO(img_data)
                    xl_img = OpenpyxlImage(img_stream)
                    ratio = xl_img.width / xl_img.height
                    target_width = min(xl_img.width, 900)
                    xl_img.width = target_width
                    xl_img.height = int(target_width / ratio)
                    ws_img.add_image(xl_img, f"A{current_row + 1}")
                    current_row += int((xl_img.height / 20) + 3)
                except Exception:
                    ws_img.cell(row=current_row + 1, column=1, value="Lỗi nhúng ảnh vào Excel")
                    current_row += 3

    return output.getvalue()