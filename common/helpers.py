import pandas as pd

def export_df_to_excel_csv(df: pd.DataFrame) -> bytes:
    """Xuat DataFrame sang CSV UTF-8 co BOM de mo tren Excel khong loi font."""
    return df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")

def format_currency_vnd(amount: float) -> str:
    """Format so sang dinh dang VND."""
    try:
        return f"{amount:,.0f} ₫".replace(",", ".")
    except (ValueError, TypeError):
        return "0 ₫"

def format_percent(val: float, decimals: int = 2) -> str:
    """Format so sang phan tram."""
    try:
        return f"{val * 100:.{decimals}f}%"
    except (ValueError, TypeError):
        return "0.00%"
