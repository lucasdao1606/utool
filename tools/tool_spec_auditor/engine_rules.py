import re
from typing import Optional, Tuple

def extract_numeric(val_str: str) -> Optional[float]:
    """Rut trich gia tri so dau tien tu chuoi."""
    if not val_str:
        return None
    match = re.search(r"[-+]?\d*\.?\d+", val_str.replace(",", "."))
    return float(match.group(0)) if match else None

def evaluate_threshold(required: str, actual_num: float) -> Tuple[bool, str]:
    """Kiem tra nguong so sanh: >=, <=, >, <, khoang min-max."""
    req_clean = required.replace(" ", "").replace(",", ".")

    # Truong hop >= hoac >=
    if ">=" in req_clean or "≥" in req_clean:
        num = extract_numeric(req_clean)
        if num is not None:
            return (actual_num >= num, f"Yeu cau: >= {num}, Thuc te: {actual_num}")

    # Truong hop <= hoac <=
    if "<=" in req_clean or "≤" in req_clean:
        num = extract_numeric(req_clean)
        if num is not None:
            return (actual_num <= num, f"Yeu cau: <= {num}, Thuc te: {actual_num}")

    # Truong hop >
    if ">" in req_clean:
        num = extract_numeric(req_clean)
        if num is not None:
            return (actual_num > num, f"Yeu cau: > {num}, Thuc te: {actual_num}")

    # Truong hop <
    if "<" in req_clean:
        num = extract_numeric(req_clean)
        if num is not None:
            return (actual_num < num, f"Yeu cau: < {num}, Thuc te: {actual_num}")

    # Khoang min - max (vd: 10 - 20)
    range_match = re.search(r"(\d+\.?\d*)\s*[-~]\s*(\d+\.?\d*)", req_clean)
    if range_match:
        min_v = float(range_match.group(1))
        max_v = float(range_match.group(2))
        is_ok = min_v <= actual_num <= max_v
        return (is_ok, f"Yeu cau trong khoang [{min_v}, {max_v}], Thuc te: {actual_num}")

    # So sanh xap xi sai so 5%
    req_num = extract_numeric(req_clean)
    if req_num is not None:
        is_ok = abs(actual_num - req_num) <= (0.05 * req_num)
        return (is_ok, f"So sanh xap xi: {req_num} vs {actual_num}")

    return (True, "Khong trich xuat duoc nguong so sanh cu the")