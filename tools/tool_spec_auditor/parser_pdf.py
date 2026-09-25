import os
import re
import warnings
from io import BytesIO
from typing import List, Dict

import pymupdf
from PIL import Image

warnings.filterwarnings("ignore")

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
        return None
    try:
        from google import genai
        return genai.Client(api_key=key)
    except ImportError:
        return None

def _get_active_model(client):
    global _CACHED_AVAILABLE_MODEL
    if _CACHED_AVAILABLE_MODEL:
        return _CACHED_AVAILABLE_MODEL

    preferred_keywords = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
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

    _CACHED_AVAILABLE_MODEL = "gemini-1.5-flash"
    return _CACHED_AVAILABLE_MODEL

def _ocr_page_image_with_gemini(client, pil_image) -> str:
    """OCR và trích xuất bảng kỹ thuật từ ảnh trang PDF sang text/markdown chuẩn."""
    prompt = (
        "Bạn là chuyên gia phân tích và bóc tách tài liệu datasheet kỹ thuật.\n"
        "Hãy trích xuất toàn bộ nội dung từ hình ảnh này thành văn bản rõ ràng:\n"
        "1. Với BẢNG BIỂU THÔNG SỐ (Specifications/Pinout/Ratings): Hãy giữ nguyên cấu trúc dạng bảng Markdown hoặc thẻ <table> rõ ràng.\n"
        "2. Với các thông số kỹ thuật (Điện áp, tần số, kích thước, nhiệt độ, chân cắm...): Giữ nguyên số liệu, ký hiệu, đơn vị đo và dung sai.\n"
        "3. Giữ nguyên toàn bộ mã linh kiện (Part Numbers) và tên hãng sản xuất.\n"
        "Chỉ trả về nội dung trích xuất, không thêm lời chào hay giải thích mở đầu/kết thúc."
    )
    active_model = _get_active_model(client)
    fallback_chain = [active_model, "gemini-1.5-flash", "gemini-2.0-flash"]
    unique_models = list(dict.fromkeys(fallback_chain))

    for model_name in unique_models:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[pil_image, prompt],
            )
            if response and response.text:
                return response.text
        except Exception:
            continue
    return ""

def extract_pdf_pages(file_bytes: bytes, api_key: str = None, log_callback=None) -> List[Dict[str, any]]:
    """
    Trích xuất nội dung từng trang PDF:
    - Nếu trang có sẵn text layer -> Đọc trực tiếp tốc độ cao bằng PyMuPDF.
    - Nếu trang là bản scan / ít chữ -> Tự động render ảnh 2x DPI và dùng Vision API OCR.
    """
    pages_data = []
    doc_pdf = pymupdf.open(stream=file_bytes, filetype="pdf")
    client = _get_genai_client(api_key=api_key)

    total_pages = len(doc_pdf)

    for page_idx in range(total_pages):
        page_num = page_idx + 1
        page = doc_pdf[page_idx]

        # 1. Thử đọc Text Layer số hóa trực tiếp
        direct_text = page.get_text() or ""
        clean_text = direct_text.strip()

        # Kiểm tra nếu trang là bản scan (dưới 80 ký tự) và có cấu hình Gemini API
        if len(clean_text) < 80 and client is not None:
            if log_callback:
                log_callback(f"🔍 Trang {page_num}: Phát hiện dạng ảnh/scan. Đang kích hoạt Vision OCR...")

            # Render ảnh độ phân giải cao 2x DPI
            mat = pymupdf.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_data = pix.tobytes("png")
            pil_image = Image.open(BytesIO(img_data))

            ocr_result = _ocr_page_image_with_gemini(client, pil_image)
            final_text = ocr_result if ocr_result else clean_text
        else:
            final_text = clean_text

        pages_data.append({
            "page_num": page_num,
            "text": final_text
        })

    doc_pdf.close()
    return pages_data