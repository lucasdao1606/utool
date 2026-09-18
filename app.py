import streamlit as st
from common.styles import apply_custom_styles
from tools.tool_docx_converter.view import render_docx_converter_tool
from tools.tool_automation.view import render_automation_tool
from tools.tool_stamp_pdf.view import render as render_stamp_pdf_tool
from tools.tool_checklist_pro.view import render_checklist_pro_tool

st.set_page_config(
    page_title="Personal Toolbox",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="expanded"
)

def main():
    apply_custom_styles()
    
    st.sidebar.title("🎛️ Personal Toolbox")
    st.sidebar.caption("Workspace Platform")
    
    # Danh mục công cụ hoàn chỉnh
    tools_registry = {
        "📄 Chuyển đổi DOCX sang Excel": render_docx_converter_tool,
        "📋 Checklist Pro (Đối soát tiêu chí)": render_checklist_pro_tool,
        "🔏 Đóng dấu giáp lai PDF": render_stamp_pdf_tool,
        "⚡ Tác vụ & Tự động hóa": render_automation_tool,
    }
    
    selected_tool = st.sidebar.radio(
        "Lựa chọn công cụ:",
        options=list(tools_registry.keys()),
        index=0
    )
    
    st.sidebar.divider()
    st.sidebar.markdown("**Trạng thái hệ thống:** 🟢 Sẵn sàng")
    
    # Hiển thị tool được chọn
    tools_registry[selected_tool]()

if __name__ == "__main__":
    main()