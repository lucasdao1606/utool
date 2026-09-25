import io
import openpyxl
from typing import List, Tuple
from .models import SpecTargetItem, ItemAuditResult

def parse_template_excel(file_bytes) -> Tuple[openpyxl.Workbook, List[SpecTargetItem]]:
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes))
    ws = wb.active

    items = []
    for r in range(3, ws.max_row + 1):
        val_tt = ws.cell(r, 1).value
        if val_tt is None:
            continue

        try:
            tt_int = int(str(val_tt).strip())
        except (ValueError, TypeError):
            continue

        name = str(ws.cell(r, 2).value or "").strip()
        req_text = str(ws.cell(r, 3).value or "").strip()
        ctcb = str(ws.cell(r, 4).value or "").strip()
        manufacturer = str(ws.cell(r, 5).value or "").strip()
        part_number = str(ws.cell(r, 6).value or "").strip()

        sub_specs = []
        for line in req_text.split("\n"):
            line_clean = line.strip().lstrip("-*+ \u2022").strip()
            if line_clean:
                sub_specs.append(line_clean)

        items.append(SpecTargetItem(
            row_idx=r,
            tt=tt_int,
            name=name,
            req_text=req_text,
            sub_specs=sub_specs,
            ctcb=ctcb,
            manufacturer=manufacturer,
            part_number=part_number
        ))

    return wb, items

def save_audit_results_to_workbook(wb: openpyxl.Workbook, results: List[ItemAuditResult]) -> bytes:
    ws = wb.active
    
    # Su dung ma Unicode de tranh loi bang ma (Encoding) tren Windows
    # Hien thi thuc te tren Excel van la: "Ð? xu?t hi?u ch?nh yêu c?u k? thu?t"
    ws.cell(2, 11).value = "\u0110\u1ec1 xu\u1ea5t hi\u1ec7u ch\u1ec9nh y\u00eau c\u1ea7u k\u1ef9 thu\u1eadt"

    for res in results:
        r = res.row_idx
        ws.cell(r, 7).value = res.thong_so_ky_thuat
        ws.cell(r, 8).value = res.nhan_xet
        ws.cell(r, 9).value = res.tham_chieu
        ws.cell(r, 10).value = res.ghi_chu
        ws.cell(r, 11).value = res.de_xuat

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()