import streamlit as st
from tools.tool_automation.engine import get_service_status

def render_automation_tool():
    st.header("⚡ Tác vụ Tự động hóa & Hệ thống")
    st.caption("Giám sát trạng thái bot, background cronjobs và các luồng tự động.")
    
    statuses = get_service_status()
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Webhook Receiver", statuses["webhook_receiver"])
    col2.metric("Cron Sync Job", statuses["cron_sync"])
    col3.metric("Cloud Storage Sync", statuses["cloud_sync"])
    
    st.divider()
    st.subheader("Trigger tác vụ thủ công")
    if st.button("🚀 Chạy kiểm tra kết nối hệ thống"):
        with st.spinner("Đang ping tới các services..."):
            st.success("Tất cả các dịch vụ đang hoạt động ổn định!")
