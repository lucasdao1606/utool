import io
import random
import fitz  # PyMuPDF
from PIL import Image


def split_stamp_parts(stamp_bytes: bytes, parts: int) -> list[Image.Image]:
    """Cắt con dấu theo chiều dọc làm nhiều phần bằng nhau."""
    img = Image.open(io.BytesIO(stamp_bytes)).convert("RGBA")
    width, height = img.size
    part_width = width / parts
    parts_list = []

    for i in range(parts):
        left = int(round(i * part_width))
        right = int(round((i + 1) * part_width)) if i < parts - 1 else width
        crop = img.crop((left, 0, right, height))
        parts_list.append(crop)

    return parts_list


def process_stamp_angle(img: Image.Image) -> Image.Image:
    """Tạo góc nghiêng ngẫu nhiên nhẹ để giống dấu đóng thực tế."""
    angle = random.uniform(-1.5, 1.5)
    return img.rotate(angle, expand=True, resample=Image.BICUBIC)


def apply_stamp_to_pdf(
    pdf_bytes: bytes,
    stamp_bytes: bytes,
    scale_factor: float = 1.0,
    base_mm: float = 14.0,
    side: str = "Phải",
) -> bytes:
    """Đóng dấu giáp lai vào tài liệu PDF và trả về bytes của file hoàn thiện."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(doc)
    if total_pages == 0:
        raise ValueError("File PDF không có trang nào.")

    # Cắt dấu thành số phần tương ứng với số trang
    stamp_parts = split_stamp_parts(stamp_bytes, total_pages)

    MM_TO_PT = 2.83465
    target_height_pt = base_mm * MM_TO_PT * scale_factor

    for i in range(total_pages):
        page = doc[i]
        rect = page.rect

        # Xoay ngẫu nhiên mảnh dấu
        part_img = process_stamp_angle(stamp_parts[i])

        # Chuyển đổi mảnh dấu sang PNG bytes
        img_buffer = io.BytesIO()
        part_img.save(img_buffer, format="PNG")
        img_bytes = img_buffer.getvalue()

        # Tính toán kích thước theo tỉ lệ
        w, h = part_img.size
        scale = target_height_pt / h
        target_width_pt = w * scale

        # Độ rung ngẫu nhiên của thợ đóng dấu (±2 pt)
        offset_x = random.uniform(-2, 2)
        offset_y = random.uniform(-2, 2)

        # Tính toán tọa độ đặt dấu (Mép phải hoặc mép trái)
        if side == "Phải":
            x1 = rect.width - 2 + offset_x
            x0 = x1 - target_width_pt
        else:
            x0 = 2 + offset_x
            x1 = x0 + target_width_pt

        y0 = (rect.height - target_height_pt) / 2 + offset_y
        y1 = y0 + target_height_pt

        # Chèn mảnh dấu vào trang
        page.insert_image(
            fitz.Rect(x0, y0, x1, y1),
            stream=img_bytes,
            overlay=True,
        )

    output_buffer = io.BytesIO()
    doc.save(output_buffer)
    doc.close()
    return output_buffer.getvalue()