from dataclasses import dataclass
from typing import List, Optional

@dataclass
class SpecTargetItem:
    row_idx: int
    tt: int
    name: str
    req_text: str
    sub_specs: List[str]
    ctcb: str
    manufacturer: str
    part_number: str

@dataclass
class ItemAuditResult:
    tt: int
    row_idx: int
    name: str
    part_number: str
    datasheet_file: str
    thong_so_ky_thuat: str     # Ghi vào C?t 7
    nhan_xet: str              # Ghi vào C?t 8
    tham_chieu: str            # Ghi vào C?t 9
    ghi_chu: str               # Ghi vào C?t 10
    de_xuat: str               # Ghi vào C?t 11
    status: str                # PASS | FAIL | WARNING | MISSING_DOC