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

# Thử import thư viện quét DFM nội bộ (pcb-tools)
try:
    import gerber
    from gerber.primitives import Line
    PCB_TOOLS_AVAILABLE = True
except ImportError:
    PCB_TOOLS_AVAILABLE = False

PILImage.MAX_IMAGE_PIXELS = None

def scan_track_width(copper_file_path, min_width_mm=0.15):
    """Quét các đường mạch có độ rộng nhỏ hơn ngưỡng cho phép."""
    violations = []
    if not PCB_TOOLS_AVAILABLE:
        return violations
        
    try:
        cam_file = gerber.read(copper_file_path)
        for primitive in cam_file.primitives:
            if isinstance(primitive, Line):
                width = primitive.aperture.shape[0] if isinstance(primitive.aperture.shape, tuple) else primitive.aperture.shape
                unit_multiplier = 25.4 if cam_file.units == 'inch' else 1.0
                width_mm = width * unit_multiplier
                
                if width_mm < min_width_mm:
                    mid_x = (primitive.start[0] + primitive.end[0]) / 2
                    mid_y = (primitive.start[1] + primitive.end[1]) / 2
                    
                    x_inch = mid_x if cam_file.units == 'inch' else mid_x / 25.4
                    y_inch = mid_y if cam_file.units == 'inch' else mid_y / 25.4
                    
                    violations.append({
                        "x_inch": x_inch,
                        "y_inch": y_inch,
                        "msg": f"Lỗi Track Width: {width_mm:.3f}mm < {min_width_mm}mm"
                    })
    except Exception:
        pass
    return violations

def generate_error_gerber(violations, output_path):
    """Tạo một file Gerber 'Ảo' chứa các điểm chấm đỏ (Lỗi DFM)."""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("%INCH*%\n")  # Hệ inch
        f.write("%FSLAX25Y25*%\n") # Format 2.5 chuẩn
        f.write("%ADD10C,0.0300*%\n") # Aperture D10: Vòng tròn 30 mil để đánh dấu lỗi
        f.write("D10*\n") 
        for v in violations:
            # Chuyển đổi tọa độ inch sang số nguyên format 2.5
            x_val = int(round(v["x_inch"] * 100000))
            y_val = int(round(v["y_inch"] * 100000))
            f.write(f"X{x_val}Y{y_val}D03*\n") 
        f.write("M02*\n") # EOF

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
    
    if ext in ['.gbr', '.ger', '.art', '.pho']:
        if name_no_ext in ['TOP', 'L01', 'L1', 'LAYER1', 'FRONT', 'F_CU', 'COMP', 'CMP']: return 'Top_Copper'
        if name_no_ext in ['BOTTOM', 'BOT', 'L12', 'L16', 'LAYER12', 'BACK', 'B_CU', 'SOLD', 'SOL']: return 'Bottom_Copper'
        if re.match(r'^L\d+', name_no_ext) or any(k in name_lower for k in ['gnd', 'pwr', 'vcc', 'in1', 'in2', 'inner']): return f"Inner_Copper_{name_no_ext}"
        if any(k in name_lower for k in ['smask', 'mask', 'smt', 'smb', 'stc', 'sts', 'soldermask']):
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
    ai_context_assets = [] 
    
    if os.name == 'nt':
        current_dir = os.path.dirname(os.path.abspath(__file__))
        root_dir = os.path.abspath(os.path.join(current_dir, "..", ".."))
        gerbv_cmd = os.path.join(root_dir, "gerbv", "bin", "gerbv.exe")
    else:
        gerbv_cmd = "gerbv"
        
    temp_dir = tempfile.mkdtemp()
    node_temp_dir = tempfile.mkdtemp()
    seen_layers = set()
    
    tracespace_ext_map = {
        'Top_Copper': 'gtl', 'Bottom_Copper': 'gbl',
        'Top_Solder_Mask': 'gts', 'Bottom_Solder_Mask': 'gbs',
        'Top_Silkscreen': 'gto', 'Bottom_Silkscreen': 'gbo',
        'Board_Outline': 'gko'
    }
    has_node_files = False
    
    try:
        with zipfile.ZipFile(io.BytesIO(zip_data), "r") as zip_ref:
            zip_ref.extractall(temp_dir)
            
        if status_callback: status_callback("Đang phân tích vector và phân loại dữ liệu lớp mạch...")
        
        top_copper_file = None
        bot_copper_file = None
        copper_count = 0
        
        for root, _, files in os.walk(temp_dir):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                input_path = os.path.join(root, file)
                
                # Bóc tách Text/PDF cho AI
                if ext in ['.txt', '.log', '.rpt', '.inf']:
                    try:
                        with open(input_path, 'r', encoding='utf-8', errors='ignore') as f:
                            ai_context_assets.append(f"--- Nội dung file {file} ---\n{f.read()[:5000]}")
                    except: pass
                elif ext == '.pdf':
                    try:
                        import fitz 
                        doc = fitz.open(input_path)
                        extracted_text = ""
                        for i in range(min(len(doc), 10)): extracted_text += doc[i].get_text() + "\n"
                        if len(extracted_text.strip()) > 50:
                            ai_context_assets.append(f"--- Nội dung PDF {file} ---\n{extracted_text}")
                        else:
                            for i in range(min(len(doc), 3)):
                                pix = doc[i].get_pixmap(dpi=150)
                                img_pil = PILImage.open(io.BytesIO(pix.tobytes("png")))
                                ai_context_assets.append(img_pil)
                    except: pass

                # Gửi file Drill cho Node.js Tracespace
                if ext in ['.drl', '.xln']:
                    shutil.copy2(input_path, os.path.join(node_temp_dir, f"drill.xln"))
                    has_node_files = True

                layer_name = get_layer_name(file)
                if layer_name:
                    if layer_name in tracespace_ext_map:
                        std_ext = tracespace_ext_map[layer_name]
                        shutil.copy2(input_path, os.path.join(node_temp_dir, f"layer_{layer_name}.{std_ext}"))
                        has_node_files = True
                        
                    if "Copper" in layer_name and layer_name not in seen_layers:
                        copper_count += 1
                        
                    if layer_name not in seen_layers:
                        seen_layers.add(layer_name)
                        if layer_name == "Top_Copper": top_copper_file = input_path
                        elif layer_name == "Bottom_Copper": bot_copper_file = input_path

                        # GERBV RENDER ẢNH PNG TĨNH LÊN UI
                        output_png = os.path.join(temp_dir, f"{layer_name}_{random.randint(1000,9999)}.png")
                        try:
                            if os.path.exists(gerbv_cmd) or os.name != 'nt':
                                subprocess.run([gerbv_cmd, "-x", "png", "-a", "-o", output_png, "--dpi=150", "--background=#FFFFFF", "--foreground=#005500", input_path], check=True, capture_output=True)
                                if os.path.exists(output_png):
                                    with PILImage.open(output_png) as img:
                                        if img.width > 2000 or img.height > 2000:
                                            img.thumbnail((2000, 2000), PILImage.Resampling.LANCZOS)
                                            img.save(output_png, format="PNG")
                                    with open(output_png, "rb") as f:
                                        layer_images.append({"name": layer_name, "filename": file, "data": f.read(), "type": "png"})
                        except: pass

        internal_params["layer_count"] = copper_count if copper_count > 0 else 2
        
        # =================================================================
        # 1. GỌI NODE.JS (TRACESPACE) RENDER ẢNH PHOTOREALISTIC
        # =================================================================
        if has_node_files:
            if status_callback: status_callback("Đang kích hoạt Node.js kết xuất ảnh bo mạch chân thực (Photorealistic)...")
            current_dir = os.path.dirname(os.path.abspath(__file__))
            root_dir = os.path.abspath(os.path.join(current_dir, "..", "..")) 
            node_script = os.path.join(current_dir, "tracespace_render.js")
            if not os.path.exists(node_script):
                node_script = os.path.join(root_dir, "tracespace_render.js")
                
            if os.path.exists(node_script):
                try:
                    node_cmd = ["node", node_script, node_temp_dir]
                    result = subprocess.run(node_cmd, capture_output=True, text=True)
                    json_match = re.search(r'\{.*\}', result.stdout, re.DOTALL)
                    
                    if json_match:
                        board_data = json.loads(json_match.group(0))
                        if board_data.get("status") == "success":
                            for side_key, side_name in [('top_svg', 'Bo mạch Siêu thực (Mặt Top)'), ('bottom_svg', 'Bo mạch Siêu thực (Mặt Bot)')]:
                                svg_path = board_data.get(side_key)
                                if svg_path and os.path.exists(svg_path):
                                    with open(svg_path, 'r', encoding='utf-8') as f:
                                        layer_images.append({
                                            "name": side_name, 
                                            "filename": "tracespace_render.svg", 
                                            "data": f.read().encode('utf-8'),
                                            "type": "svg"
                                        })
                            debug_logs.append("✅ Kết xuất ảnh SVG Photorealistic bằng Tracespace thành công!")
                except Exception as e:
                    debug_logs.append(f"❌ Lỗi chạy Node.js Render: {e}")

        # =================================================================
        # 2. DFM HEATMAP: GERBV RENDER LAYER ĐỒNG VÀ LAYER LỖI ẢO TÁCH BIỆT
        # =================================================================
        if top_copper_file or bot_copper_file:
            if status_callback: status_callback("Đang phân tích rủi ro DFM Track Width và kết xuất Vector...")
            
            def process_dfm_side(copper_file, side_name, side_key):
                if not copper_file: return
                violations = scan_track_width(copper_file)
                error_gbr_path = os.path.join(temp_dir, f"{side_key}_errors.gbr")
                dfm_svg_path = os.path.join(temp_dir, f"{side_key}_dfm.svg")
                
                if violations:
                    generate_error_gerber(violations, error_gbr_path)
                    debug_logs.append(f"⚠️ Đã tạo layer Gerber Ảo chứa {len(violations)} chấm báo lỗi cho {side_name}.")
                    try:
                        if os.path.exists(gerbv_cmd) or os.name != 'nt':
                            cmd = [gerbv_cmd, "-b", "#FFFFFF", "-f", "#005500", copper_file, "-f", "#FF0000", error_gbr_path, "-x", "svg", "-a", "-o", dfm_svg_path]
                            subprocess.run(cmd, check=True, capture_output=True)
                    except Exception as e:
                        debug_logs.append(f"❌ Lỗi chạy gerbv SVG DFM {side_key}: {e}")
                else:
                    try:
                        if os.path.exists(gerbv_cmd) or os.name != 'nt':
                            cmd = [gerbv_cmd, "-b", "#FFFFFF", "-f", "#005500", copper_file, "-x", "svg", "-a", "-o", dfm_svg_path]
                            subprocess.run(cmd, check=True, capture_output=True)
                    except: pass

                if os.path.exists(dfm_svg_path):
                    with open(dfm_svg_path, 'r', encoding='utf-8') as f:
                        layer_images.append({
                            "name": f"Bản đồ Lỗi Kỹ thuật ({side_name})",
                            "filename": f"{side_key}_dfm_heatmap.svg",
                            "data": f.read().encode('utf-8'),
                            "type": "svg"
                        })
            
            process_dfm_side(top_copper_file, "Mặt Top", "top")
            process_dfm_side(bot_copper_file, "Mặt Bottom", "bot")
            debug_logs.append("✅ Kết xuất Bản đồ Vector DFM Tách mặt (Top/Bot) bằng gerbv hoàn tất!")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        shutil.rmtree(node_temp_dir, ignore_errors=True)
        
    return layer_images, internal_params, ai_context_assets

def analyze_with_gemini_ai(ai_context_assets: list, internal_params: dict, mf_params: dict, gemini_api_keys: list, debug_logs: list, status_callback=None) -> dict:
    if not gemini_api_keys: return None
    if status_callback: status_callback("🧠 Kích hoạt Gemini AI: Đang phân tích Chuyên sâu...")
    keys_to_try = list(gemini_api_keys)
    random.shuffle(keys_to_try)
    
    instruction_text = f"""Bạn là chuyên gia CAM và DFM PCB. Số liệu phần mềm quét: {internal_params.get('layer_count')} lớp. 
    Số liệu MacroFab API: {json.dumps(mf_params, ensure_ascii=False) if mf_params else 'N/A'}.
    Dưới đây là DỮ LIỆU TÀI LIỆU SẢN XUẤT THU THẬP:"""

    task_text = """TRẢ VỀ DUY NHẤT 1 CHUỖI JSON:
    {"layer_count": "chuỗi", "dimensions_mm": "chuỗi", "board_thickness": "chuỗi", "material": "chuỗi", "surface_finish": "chuỗi", "copper_weight": "chuỗi", "smt_technology": "chuỗi", "total_holes": "số", "plated_holes": "số", "non_plated_holes": "số", "ipc_errors": "số", "ipc_warnings": "số", "ai_reasoning": "chuỗi"}"""
    
    prompt = [instruction_text]
    prompt.extend(ai_context_assets)
    prompt.append(task_text)
    
    for attempt, key in enumerate(keys_to_try):
        try:
            genai.configure(api_key=key)
            available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods and 'gemini' in m.name.lower()]
            if not available_models: continue

            def model_sort_key(m_name):
                nums = re.findall(r'\d+\.\d+', m_name)
                version = float(nums[0]) if nums else 0.0
                stability = 2 if 'latest' in m_name.lower() else (1 if 'preview' in m_name.lower() or 'exp' in m_name.lower() else 3)
                tier = 2 if 'flash' in m_name.lower() else 1
                return (version, stability, tier, m_name)

            available_models.sort(key=model_sort_key, reverse=True)
            top_5_models = available_models[:5]
            
            for model_idx, selected_model in enumerate(top_5_models):
                try:
                    generation_config = genai.types.GenerationConfig(response_mime_type="application/json")
                    model = genai.GenerativeModel(model_name=selected_model, generation_config=generation_config)
                    for retry in range(3):
                        try:
                            response = model.generate_content(prompt)
                            raw_text = response.text.replace('```json', '').replace('```', '').strip()
                            parsed_json = json.loads(raw_text)
                            debug_logs.append(f"✅ AI phân tích thành công!")
                            return parsed_json
                        except Exception as inner_e:
                            error_str = str(inner_e).lower()
                            if "429" in error_str or "quota" in error_str or "exhausted" in error_str or "404" in error_str: break 
                            if retry < 2: time.sleep(3)
                except: pass
        except: pass
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
        mf_w = mf_params.get("width_mm", 0)
        mf_h = mf_params.get("height_mm", 0)

        merged_layers = f"{mf_layers} (API) / {int_layers} (Nội bộ)" if (mf_layers > 0 and int_layers > 0 and mf_layers != int_layers) else (mf_layers if mf_layers > 0 else int_layers)
        
        final_params = {
            "Số lớp Đồng (Layer Count)": merged_layers,
            "Kích thước X (Width - mm)": mf_w if mf_w > 0 else "N/A",
            "Kích thước Y (Height - mm)": mf_h if mf_h > 0 else "N/A",
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
            if safe_sheet_name in wb.sheetnames: safe_sheet_name = f"{safe_sheet_name[:26]}_{random.randint(100, 999)}"
                
            ws_img = wb.create_sheet(title=safe_sheet_name)
            ws_img.column_dimensions['A'].width = 80
            
            layer_images = res.get("layer_images", [])
            current_row = 1
            if not layer_images: continue
                
            for img_info in layer_images:
                if img_info.get("type") == "svg":
                    ws_img.cell(row=current_row, column=1, value=f"[Bản vẽ Vector phân giải cao - Có thể tải về từ Web]")
                    current_row += 2
                    continue
                    
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