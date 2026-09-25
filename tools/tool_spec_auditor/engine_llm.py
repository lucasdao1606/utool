import json
import re
import os
from typing import List, Dict
from .models import SpecTargetItem, ItemAuditResult

def audit_single_item_fallback(item: SpecTargetItem, pdf_name: str, pdf_text: str) -> ItemAuditResult:
    """Chế độ fallback offline khi không có LLM API key."""
    if not pdf_text:
        return ItemAuditResult(
            tt=item.tt, row_idx=item.row_idx, name=item.name, part_number=item.part_number,
            datasheet_file=pdf_name or "Không có", thong_so_ky_thuat="Không có nội dung datasheet để đối soát",
            nhan_xet="Chưa có tài liệu", tham_chieu="-", ghi_chu="Thiếu file PDF datasheet",
            de_xuat="Không có cơ sở để đề xuất do thiếu tài liệu.", status="MISSING_DOC"
        )

    pdf_lower = pdf_text.lower()
    missing_specs = []
    
    mfg_found = item.manufacturer.lower() in pdf_lower if item.manufacturer else True
    pn_found = item.part_number.lower() in pdf_lower if item.part_number else True
    
    thong_so_list = []
    tham_chieu_list = []
    de_xuat_list = []
    
    if item.manufacturer:
        if mfg_found:
            tham_chieu_list.append(f"- Nhà SX ({item.manufacturer}): Khớp ({pdf_name})")
            de_xuat_list.append(f"- Nhà sản xuất: {item.manufacturer}")
        else:
            missing_specs.append(f"Không tìm thấy Nhà sản xuất '{item.manufacturer}'")
            de_xuat_list.append(f"- Nhà sản xuất: Cập nhật theo datasheet thực tế")
            
    if item.part_number:
        if pn_found:
            tham_chieu_list.append(f"- Mã NSX ({item.part_number}): Khớp ({pdf_name})")
            de_xuat_list.append(f"- Mã NSX: {item.part_number}")
        else:
            missing_specs.append(f"Không tìm thấy Mã NSX '{item.part_number}'")
            de_xuat_list.append(f"- Mã NSX: Cập nhật theo datasheet thực tế")

    for spec in item.sub_specs:
        keywords = [k for k in re.split(r"[:,\s/]+", spec.lower()) if len(k) > 2]
        found_page = None
        for page_num, page_text in re.findall(r"--- TRANG (\d+) ---\n(.*?)(?=\n--- TRANG|\Z)", pdf_text, re.DOTALL):
            if any(kw in page_text.lower() for kw in keywords):
                found_page = page_num
                break
                
        if found_page:
            thong_so_list.append(f"- {spec}")
            tham_chieu_list.append(f"- {spec[:20]}...: {pdf_name}/trang {found_page}")
            de_xuat_list.append(f"- {spec}")
        else:
            missing_specs.append(spec)
            de_xuat_list.append(f"- {spec} (Lưu ý: Không tìm thấy trong datasheet, cần xác minh lại số liệu)")

    is_all_pass = len(missing_specs) == 0
    nhan_xet = "Đạt" if is_all_pass else "Không đạt"
    ghi_chu = "" if is_all_pass else f"Thiếu/Không khớp: {'; '.join(missing_specs)}"

    return ItemAuditResult(
        tt=item.tt, row_idx=item.row_idx, name=item.name, part_number=item.part_number, datasheet_file=pdf_name,
        thong_so_ky_thuat="\n".join(thong_so_list) if thong_so_list else "Chưa bóc tách được thông số",
        nhan_xet=nhan_xet, tham_chieu="\n".join(tham_chieu_list), ghi_chu=ghi_chu, de_xuat="\n".join(de_xuat_list),
        status="PASS" if is_all_pass else "FAIL"
    )

def _get_dynamic_models(genai) -> List[str]:
    """Tự động quét danh sách các model đang hoạt động từ tài khoản Google"""
    available_models = []
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            available_models.append(m.name)
            
    # Ưu tiên các model Flash (nhanh) -> sau đó đến Pro -> Các model còn lại
    flash_models = [m for m in available_models if 'flash' in m.lower()]
    pro_models = [m for m in available_models if 'pro' in m.lower() and m not in flash_models]
    others = [m for m in available_models if m not in flash_models and m not in pro_models]
    
    return flash_models + pro_models + others

def audit_single_item_llm(item: SpecTargetItem, pdf_name: str, pdf_text: str, api_key: str = None) -> ItemAuditResult:
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            try:
                import streamlit as st
                api_key = st.secrets.get("GEMINI_API_KEY")
            except Exception:
                pass

    if not api_key or not pdf_text:
        return audit_single_item_fallback(item, pdf_name, pdf_text)

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        
        # 1. Quét model động
        try:
            test_models = _get_dynamic_models(genai)
            if not test_models:
                raise Exception("API Key đúng nhưng không có quyền dùng model nào.")
        except Exception as auth_e:
            raise Exception(f"Lỗi API Key hoặc Mạng: {str(auth_e)}")

        text_truncated = pdf_text[:25000]
        prompt = f"""
Bạn là chuyên gia thẩm định hồ sơ kỹ thuật và vật tư thiết bị.
Nhiệm vụ: Đối soát danh sách yêu cầu kỹ thuật, Nhà sản xuất, Mã NSX của sản phẩm với nội dung Datasheet.

THÔNG TIN YÊU CẦU:
- Số thứ tự: {item.tt}
- Tên hạng mục: {item.name}
- Nhà sản xuất yêu cầu: {item.manufacturer}
- Mã NSX (Part Number) yêu cầu: {item.part_number}

CÁC CHỈ TIÊU KỸ THUẬT YÊU CẦU:
{json.dumps(item.sub_specs, ensure_ascii=False, indent=2)}

NỘI DUNG DATASHEET ({pdf_name}):
{text_truncated}

QUY TẮC ĐỐI SOÁT & TRÍCH DẪN (RẤT QUAN TRỌNG):
1. KIỂM TRA HÃNG & MÃ SẢN PHẨM: 
   - Nếu KHỚP: Tuyệt đối KHÔNG ghi vào ô "thong_so_ky_thuat". Chỉ ghi nhận vào ô "tham_chieu" (Ví dụ: "- Nhà SX ({item.manufacturer}): Khớp ({pdf_name})").
   - Nếu KHÔNG KHỚP / KHÔNG THẤY: Ghi chi tiết lỗi vào ô "ghi_chu".
2. ĐỐI SOÁT CHỈ TIÊU KỸ THUẬT: Tìm giá trị thực tế tương ứng với từng chỉ tiêu. Ô "thong_so_ky_thuat" BÂY GIỜ CHỈ CHỨA CÁC CHỈ TIÊU KỸ THUẬT.
3. TRÍCH DẪN CHI TIẾT THEO TRANG: Với MỖI nội dung tìm được, BẮT BUỘC chỉ rõ file nào, trang số mấy, mục nào. Ghi thẳng vào ô `tham_chieu`.
4. ĐÁNH GIÁ CHUYÊN GIA:
   - "Đạt": Nếu TẤT CẢ Nhà sản xuất + Mã NSX + Thông số kỹ thuật đều KHỚP.
   - "Không đạt" hoặc "Cần làm rõ": Nếu thiếu, sai lệch mã NSX, sai hãng, hoặc không đáp ứng thông số.
5. ĐỀ XUẤT HIỆU CHỈNH: Trình bày lại toàn bộ cấu hình thành một danh sách "Yêu cầu kỹ thuật đề xuất" mới.
   - Với nội dung ĐÃ KHỚP: Giữ nguyên đề xuất theo yêu cầu gốc.
   - Với nội dung CHƯA KHỚP: Lấy CHÍNH XÁC THÔNG SỐ THỰC TẾ trong datasheet để đưa vào phần đề xuất.

TRẢ VỀ DUY NHẤT JSON NHƯ SAU (KHÔNG BỌC CODE BLOCK):
{{
  "thong_so_ky_thuat": "- [Chỉ tiêu 1]: [Thực tế]\\n- [Chỉ tiêu 2]: [Thực tế]...",
  "nhan_xet": "Đạt" hoặc "Không đạt" hoặc "Cần làm rõ",
  "tham_chieu": "- Hãng/Mã NSX: Khớp ({pdf_name})\\n- [Chỉ tiêu 1]: {pdf_name}/trang Z, mục W...",
  "ghi_chu": "Ghi cụ thể các điểm không đạt/không có (Nếu Đạt thì để trống)",
  "de_xuat": "- Nhà SX: [Đề xuất chuẩn]\\n- Mã NSX: [Đề xuất chuẩn]\\n- [Chỉ tiêu 1]: [Đề xuất chuẩn]...",
  "status": "PASS" hoặc "FAIL"
}}
"""
        last_error = None
        for model_name in test_models:
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt)
                raw_text = response.text.strip()
                
                if raw_text.startswith("```json"): raw_text = raw_text[7:]
                if raw_text.startswith("```"): raw_text = raw_text[3:]
                if raw_text.endswith("```"): raw_text = raw_text[:-3]

                data = json.loads(raw_text.strip())
                return ItemAuditResult(
                    tt=item.tt, row_idx=item.row_idx, name=item.name, part_number=item.part_number, datasheet_file=pdf_name,
                    thong_so_ky_thuat=data.get("thong_so_ky_thuat", "").strip(),
                    nhan_xet=data.get("nhan_xet", "Không đạt").strip(),
                    tham_chieu=data.get("tham_chieu", "").strip(),
                    ghi_chu=data.get("ghi_chu", "").strip(),
                    de_xuat=data.get("de_xuat", "").strip(),
                    status=data.get("status", "FAIL").strip()
                )
            except Exception as e:
                last_error = f"{model_name}: {str(e)}"
                continue 
                
        res = audit_single_item_fallback(item, pdf_name, pdf_text)
        res.ghi_chu += f" (Đã thử {len(test_models)} models nhưng đều báo lỗi: {last_error})"
        return res

    except Exception as e:
        res = audit_single_item_fallback(item, pdf_name, pdf_text)
        res.ghi_chu += f" (Lỗi hệ thống AI: {str(e)})"
        return res

def generate_specs_llm(item: SpecTargetItem, pdf_name: str, pdf_text: str, api_key: str = None) -> ItemAuditResult:
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            try:
                import streamlit as st
                api_key = st.secrets.get("GEMINI_API_KEY")
            except Exception:
                pass

    if not api_key or not pdf_text:
        return ItemAuditResult(
            tt=item.tt, row_idx=item.row_idx, name=item.name, part_number=item.part_number,
            datasheet_file=pdf_name or "Không có", thong_so_ky_thuat="", nhan_xet="",
            tham_chieu="", ghi_chu="Thiếu API Key hoặc không có nội dung Datasheet",
            de_xuat="Không thể tạo cấu hình", status="MISSING_DOC"
        )

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        
        # 1. Quét model động
        try:
            test_models = _get_dynamic_models(genai)
            if not test_models:
                raise Exception("API Key đúng nhưng không có quyền dùng model nào.")
        except Exception as auth_e:
            raise Exception(f"Lỗi API Key hoặc Mạng: {str(auth_e)}")

        text_truncated = pdf_text[:25000]
        prompt = f"""
Bạn là một Kỹ sư cao cấp chuyên lập hồ sơ yêu cầu kỹ thuật vật tư thiết bị.
Nhiệm vụ: Đọc Datasheet và trích xuất các thông số kỹ thuật quan trọng nhất của đúng mã sản phẩm được yêu cầu để tự động tạo thành Bảng Yêu cầu kỹ thuật đấu thầu.

THÔNG TIN SẢN PHẨM CẦN LẬP CẤU HÌNH:
- Số TT: {item.tt}
- Tên vật tư: {item.name}
- Nhà sản xuất: {item.manufacturer}
- Mã NSX (Part Number): {item.part_number}

NỘI DUNG DATASHEET ({pdf_name}):
{text_truncated}

YÊU CẦU TRÍCH XUẤT (RẤT QUAN TRỌNG):
1. TÌM ĐÚNG MÃ SẢN PHẨM: File PDF có thể là catalog chứa hàng chục dòng sản phẩm khác nhau. BẠN PHẢI TÌM VÀ TRÍCH XUẤT CHÍNH XÁC THÔNG SỐ CỦA MÃ '{item.part_number}'.
2. CHỌN LỌC THÔNG SỐ CỐT LÕI: Chỉ trích xuất các thông số định lượng hoặc đặc tính kỹ thuật cốt lõi (Ví dụ: Kích thước, khối lượng, điện áp, dòng điện, công suất, dải nhiệt độ, IP/IK, chất liệu, tiêu chuẩn đáp ứng...). 
3. LỌC NHIỄU: Tuyệt đối bỏ qua các câu văn quảng cáo, giới thiệu công ty, tính năng chung chung.
4. ĐỊNH DẠNG CHUẨN: Trình bày thành một danh sách gạch đầu dòng chuyên nghiệp, ngắn gọn, mỗi dòng 1 thông số kèm đơn vị rõ ràng.

TRẢ VỀ DUY NHẤT JSON NHƯ SAU (KHÔNG BỌC CODE BLOCK):
{{
  "de_xuat": "- Thông số 1: Giá trị\\n- Thông số 2: Giá trị...",
  "ghi_chu": "Trống. (Chỉ ghi nếu mã sản phẩm không có trong datasheet, hoặc thiếu dữ liệu nghiêm trọng)"
}}
"""
        last_error = None
        for model_name in test_models:
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt)
                raw_text = response.text.strip()
                
                if raw_text.startswith("```json"): raw_text = raw_text[7:]
                if raw_text.startswith("```"): raw_text = raw_text[3:]
                if raw_text.endswith("```"): raw_text = raw_text[:-3]

                data = json.loads(raw_text.strip())
                
                return ItemAuditResult(
                    tt=item.tt, 
                    row_idx=item.row_idx, 
                    name=item.name, 
                    part_number=item.part_number, 
                    datasheet_file=pdf_name,
                    thong_so_ky_thuat="", 
                    nhan_xet="Tạo cấu hình thành công", 
                    tham_chieu="-", 
                    ghi_chu=data.get("ghi_chu", "").strip(),
                    de_xuat=data.get("de_xuat", "").strip(),
                    status="PASS"
                )
            except Exception as e:
                last_error = f"{model_name}: {str(e)}"
                continue

        return ItemAuditResult(
            tt=item.tt, row_idx=item.row_idx, name=item.name, part_number=item.part_number,
            datasheet_file=pdf_name, thong_so_ky_thuat="", nhan_xet="Lỗi AI",
            tham_chieu="", ghi_chu=f"Đã thử toàn bộ {len(test_models)} model hợp lệ nhưng thất bại. Lỗi cuối: {last_error}", de_xuat="", status="FAIL"
        )

    except Exception as e:
        return ItemAuditResult(
            tt=item.tt, row_idx=item.row_idx, name=item.name, part_number=item.part_number,
            datasheet_file=pdf_name, thong_so_ky_thuat="", nhan_xet="Lỗi cấu hình AI",
            tham_chieu="", ghi_chu=f"Lỗi khởi tạo hệ thống LLM: {str(e)}", de_xuat="", status="FAIL"
        )