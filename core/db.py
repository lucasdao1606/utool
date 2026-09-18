"""Ket noi Google Sheets / Database."""
import streamlit as st

@st.cache_resource
def init_db_connection():
    """Khoi tao connection pool hoac gspread client dung chung."""
    # Vi du:
    # import gspread
    # gc = gspread.service_account(filename="credentials.json")
    # return gc
    return None
