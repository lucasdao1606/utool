import os
import re
import tempfile
import unicodedata
import warnings
from io import BytesIO
import pymupdf
import cv2
import numpy as np
from PIL import Image
from bs4 import BeautifulSoup
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import nsdecls, qn
from google import genai

warnings.filterwarnings("ignore")

# ==========================================
# 1. CẤU HÌNH CLIENT VÀ TỰ ĐỘNG CHỌN MODEL
# ==========================================
_CACHED_AVAILABLE_MODEL = None

def _get_genai_client(api_key: str = None):
    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        try:
            import streamlit as st
            key = st.secrets.get("GEMINI_API_KEY")
        except Exception:
            pass

    if not key:
        raise ValueError("Chưa tìm thấy GEMINI_API_KEY. Vui lòng cấu hình API Key.")
    return genai.Client(api_key=key)

def _get_active_model(client):
    """
    Tự động truy vấn ModelService từ API để lấy model Flash đang hoạt động,
    tránh lỗi 404 do model cũ bị tắt hoặc đổi tên.
    """
    global _CACHED_AVAILABLE_MODEL
    if _CACHED_AVAILABLE_MODEL:
        return _CACHED_AVAILABLE_MODEL

    preferred_keywords = [
        "gemini-3.8-flash",
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-flash"
    ]

    try:
        available_models = [
            m.name.replace("models/", "") 
            for m in client.models.list() 
            if hasattr(m, 'name') and 'flash' in m.name.lower()
        ]

        for pref in preferred_keywords:
            for act in available_models:
                if pref in act:
                    _CACHED_AVAILABLE_MODEL = act
                    return _CACHED_AVAILABLE_MODEL

        if available_models:
            _CACHED_AVAILABLE_MODEL = available_models[0]
            return _CACHED_AVAILABLE_MODEL

    except Exception:
        pass

    _CACHED_AVAILABLE_MODEL = "gemini-3.6-flash"
    return _CACHED_AVAILABLE_MODEL

def _generate_with_fallback(client, pil_image, prompt):
    active_model = _get_active_model(client)
    
    fallback_chain = [
        active_model,
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite"
    ]
    unique_models = list(dict.fromkeys(fallback_chain))

    last_error = None
    for model_name in unique_models:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[pil_image, prompt],
            )
            if response and response.text:
                return response.text
        except Exception as err:
            last_error = err
            continue

    raise RuntimeError(f"Tất cả các model thử nghiệm đều thất bại: {last_error}")

# ==========================================
# 2. XỬ LÝ HÌNH ẢNH: TRÍCH XUẤT DẤU ĐỎ & LOGO
# ==========================================
def _extract_seals_and_logos(cv2_img):
    h, w = cv2_img.shape[:2]
    hsv = cv2.cvtColor(cv2_img, cv2.COLOR_BGR2HSV)

    # Lọc dải màu mực đỏ (con dấu tròn / chữ ký đỏ)
    lower_red1 = np.array([0, 70, 50])
    upper_red1 = np.array([10, 255, 255])
    lower_red2 = np.array([160, 70, 50])
    upper_red2 = np.array([180, 255, 255])

    mask_r1 = cv2.inRange(hsv, lower_red1, upper_red1)
    mask_r2 = cv2.inRange(hsv, lower_red2, upper_red2)
    red_mask = cv2.bitwise_or(mask_r1, mask_r2)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    dilated_red = cv2.dilate(red_mask, kernel, iterations=3)

    contours, _ = cv2.findContours(dilated_red, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    extracted_seals = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if 1500 < area < 120000:
            x, y, cw, ch = cv2.boundingRect(cnt)
            aspect_ratio = float(cw) / max(ch, 1)
            if 0.5 <= aspect_ratio <= 2.8:
                pad = 10
                x1 = max(0, x - pad)
                y1 = max(0, y - pad)
                x2 = min(w, x + cw + pad)
                y2 = min(h, y + ch + pad)
                crop = cv2_img[y1:y2, x1:x2]
                crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                extracted_seals.append(Image.fromarray(crop_rgb))

    # Phát hiện Logo ở phần đầu văn bản (Top 18% chiều cao)
    top_region = cv2_img[0:int(h * 0.18), :]
    gray_top = cv2.cvtColor(top_region, cv2.COLOR_BGR2GRAY)
    _, thresh_top = cv2.threshold(gray_top, 240, 255, cv2.THRESH_BINARY_INV)

    logo_contours, _ = cv2.findContours(thresh_top, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    extracted_logos = []
    for cnt in logo_contours:
        area = cv2.contourArea(cnt)
        if 2000 < area < 80000:
            x, y, cw, ch = cv2.boundingRect(cnt)
            if (x < w * 0.35) or (x > w * 0.65):
                pad = 6
                x1 = max(0, x - pad)
                y1 = max(0, y - pad)
                x2 = min(w, x + cw + pad)
                y2 = min(int(h * 0.18), y + ch + pad)
                crop = top_region[y1:y2, x1:x2]
                crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                extracted_logos.append(Image.fromarray(crop_rgb))

    return extracted_logos[:1], extracted_seals[:2]

# ==========================================
# 3. ĐỊNH DẠNG TÀI LIỆU WORD & BẢNG BIỂU
# ==========================================
def _setup_docx_vietnamese_font(doc):
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Times New Roman'
    font.size = Pt(11)
    font.color.rgb = RGBColor(0x11, 0x11, 0x11)

    rPr = style.element.get_or_add_rPr()
    rFonts = OxmlElement('w:rFonts')
    rFonts.set(qn('w:ascii'), 'Times New Roman')
    rFonts.set(qn('w:hAnsi'), 'Times New Roman')
    rFonts.set(qn('w:cs'), 'Times New Roman')
    rPr.append(rFonts)

def _style_table_cell(cell, text, is_header=False):
    cell.text = text.strip()
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(
        f'<w:tcMar {nsdecls("w")}>'
        f'<w:top w:w="120" w:type="dxa"/>'
        f'<w:bottom w:w="120" w:type="dxa"/>'
        f'<w:left w:w="140" w:type="dxa"/>'
        f'<w:right w:w="140" w:type="dxa"/>'
        f'</w:tcMar>'
    )
    tcPr.append(tcMar)

    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    for run in p.runs:
        run.font.name = 'Times New Roman'
        run.font.size = Pt(9.5)
        if is_header:
            run.font.bold = True

    if is_header:
        tcPr.append(parse_xml(f'<w:shd {nsdecls("w")} w:fill="EAEAEA"/>'))

def _insert_html_table_to_docx(doc, html_table_str):
    soup = BeautifulSoup(html_table_str, 'html.parser')
    table_tag = soup.find('table')
    if not table_tag:
        return

    tr_tags = table_tag.find_all('tr')
    if not tr_tags:
        return

    matrix_cells = []
    max_cols = 0
    for tr in tr_tags:
        cells = tr.find_all(['td', 'th'])
        row_content = [c.get_text().strip() for c in cells]
        max_cols = max(max_cols, len(row_content))
        matrix_cells.append(row_content)

    if max_cols == 0:
        return

    table = doc.add_table(rows=len(matrix_cells), cols=max_cols)
    table.style = 'Table Grid'
    table.autofit = True

    for r_idx, row in enumerate(matrix_cells):
        is_th = (r_idx == 0)
        for c_idx in range(max_cols):
            cell_text = row[c_idx] if c_idx < len(row) else ""
            cell = table.cell(r_idx, c_idx)
            _style_table_cell(cell, cell_text, is_header=is_th)

    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(6)

def _insert_pil_image_to_docx(doc_or_section, pil_img, width_inches=1.6, is_header=False):
    img_stream = BytesIO()
    pil_img.save(img_stream, format='PNG')
    img_stream.seek(0)

    if is_header:
        p = doc_or_section.header.paragraphs[0]
        run = p.add_run()
        run.add_picture(img_stream, width=Inches(width_inches))
    else:
        p = doc_or_section.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        run = p.add_run()
        run.add_picture(img_stream, width=Inches(width_inches))

# ==========================================
# 4. TIẾN TRÌNH XỬ LÝ CHÍNH ĐƯỢC XUẤT (EXPORT)
# ==========================================
def process_pdf_to_docx(pdf_bytes, use_gpu=False, progress_callback=None, api_key: str = None):
    """
    Hàm xử lý chuyển đổi toàn bộ PDF thành DOCX qua Vision API,
    tái tạo đầy đủ Tiếng Việt, Bảng biểu HTML, Header/Footer, Logo và Con dấu đỏ.
    """
    client = _get_genai_client(api_key=api_key)

    doc_pdf = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    docx_doc = Document()
    _setup_docx_vietnamese_font(docx_doc)

    total_pages = len(doc_pdf)

    prompt = (
        "Bạn là chuyên gia số hóa tài liệu hành chính, kỹ thuật tiếng Việt. Hãy bóc tách nội dung hình ảnh này:\n"
        "1. Phân biệt rõ các thành phần bằng thẻ đánh dấu:\n"
        "   - Nếu có TIÊU ĐỀ ĐẦU TRANG (Header): Bọc trong thẻ <header>...</header>\n"
        "   - Nếu có CHÂN TRANG (Footer/Số trang): Bọc trong thẻ <footer>...</footer>\n"
        "   - Với BẢNG BIỂU: Bắt buộc chuyển đổi thành thẻ <table>...</table> với <tr>, <td>, <th>. Giữ nguyên ô gộp và cột rỗng.\n"
        "   - Với VĂN BẢN NỘI DUNG: Giữ nguyên văn bản tiếng Việt chuẩn, không thêm bớt, không tóm tắt.\n"
        "2. Chỉ trả về trực tiếp nội dung và thẻ HTML, không giải thích mở đầu hay kết thúc."
    )

    with tempfile.TemporaryDirectory():
        for page_idx in range(total_pages):
            if progress_callback:
                progress_callback(page_idx + 1, total_pages)

            page = doc_pdf[page_idx]

            mat = pymupdf.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_bytes = pix.tobytes("png")
            
            nparr = np.frombuffer(img_bytes, np.uint8)
            cv2_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            pil_image = Image.fromarray(cv2.cvtColor(cv2_img, cv2.COLOR_BGR2RGB))

            logos, seals = _extract_seals_and_logos(cv2_img)

            raw_text = _generate_with_fallback(client, pil_image, prompt)
            raw_text = re.sub(r'```(?:html)?', '', raw_text).strip()

            current_section = docx_doc.sections[-1]

            # Bóc tách Header
            header_match = re.search(r'<header>(.*?)</header>', raw_text, flags=re.DOTALL | re.IGNORECASE)
            if header_match:
                header_text = header_match.group(1).strip()
                if header_text:
                    current_section.header.paragraphs[0].text = header_text
                raw_text = re.sub(r'<header>.*?</header>', '', raw_text, flags=re.DOTALL | re.IGNORECASE)

            # Bóc tách Footer
            footer_match = re.search(r'<footer>(.*?)</footer>', raw_text, flags=re.DOTALL | re.IGNORECASE)
            if footer_match:
                footer_text = footer_match.group(1).strip()
                if footer_text:
                    current_section.footer.paragraphs[0].text = footer_text
                raw_text = re.sub(r'<footer>.*?</footer>', '', raw_text, flags=re.DOTALL | re.IGNORECASE)

            # Chèn Logo vào đầu trang
            for logo_img in logos:
                _insert_pil_image_to_docx(docx_doc, logo_img, width_inches=1.4)

            # Dựng nội dung văn bản và bảng biểu
            tokens = re.split(r'(<table.*?>.*?</table>)', raw_text, flags=re.DOTALL | re.IGNORECASE)
            for token in tokens:
                token_strip = token.strip()
                if not token_strip:
                    continue

                if token_strip.lower().startswith("<table") and token_strip.lower().endswith("</table>"):
                    _insert_html_table_to_docx(docx_doc, token_strip)
                else:
                    lines = token_strip.split('\n')
                    for line in lines:
                        clean_line = line.strip()
                        if clean_line:
                            p = docx_doc.add_paragraph(clean_line)
                            if any(clean_line.lower().startswith(kw) for kw in ['điều', 'kính gửi', 'báo giá', 'hợp đồng', 'cộng hòa']):
                                p.paragraph_format.space_after = Pt(4)

            # Chèn con dấu đỏ vào cuối trang
            for seal_img in seals:
                _insert_pil_image_to_docx(docx_doc, seal_img, width_inches=1.6)

            if page_idx < total_pages - 1:
                docx_doc.add_page_break()

    doc_pdf.close()

    temp_docx = tempfile.NamedTemporaryFile(delete=False, suffix=".docx")
    docx_doc.save(temp_docx.name)
    temp_docx.close()
    return temp_docx.name