import os
import streamlit as st

def get_secret(key: str, default: str = "") -> str:
    """Lay gia tri tu st.secrets hoac bien moi truong."""
    try:
        keys = key.split(".")
        val = st.secrets
        for k in keys:
            val = val[k]
        return str(val)
    except Exception:
        return os.environ.get(key, default)
