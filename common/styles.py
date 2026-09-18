import streamlit as st

def apply_custom_styles():
    """Custom CSS bo sung cho Streamlit UI."""
    st.markdown("""
        <style>
        .metric-card {
            background-color: #1E293B;
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 12px;
        }
        .stMetric {
            background: rgba(30, 41, 59, 0.5);
            padding: 10px 14px;
            border-radius: 6px;
            border: 1px solid #334155;
        }
        </style>
    """, unsafe_allow_html=True)
