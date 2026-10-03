import streamlit as st
import os
import pandas as pd
from tools.tool_gerber_analyzer.engine import (
    group_uploaded_files, 
    prepare_gerber_zip, 
    upload_and_analyze_gerber,
    generate_pcb_report_excel
)

def render_gerber_analyzer_tool():
    st.subheader("🎛️ Phân tích & Đánh giá Gerber PCB (Đa Mạch)")
    st.caption("Công cụ tự động upload hàng loạt cấu trúc Gerber để trích xuất chuyên sâu toàn bộ tham số kỹ thuật và DFM.")

    # Quản lý trạng thái reset uploader
    if "gerber_uploader_key" not in st.session_state:
        st.session_state.gerber_uploader_key = 0

    col_upload, col_clear = st.columns([4, 1])
    
    with col_upload:
        allowed_extensions = [
            "zip", "rar", "gbr", "drl", "xln", "txt", 
            "gko", "gm1", "gm2", "gtl", "gbl", "gto", "gbo", "gts", "gbs"
        ]
        uploaded_files = st.file_uploader(
            "Tải lên các file Gerber (Hỗ trợ upload hàng loạt .zip, .rar hoặc file rời)", 
            type=allowed_extensions,
            accept_multiple_files=True,
            key=f"gerber_uploader_{st.session_state.gerber_uploader_key}",
            label_visibility="collapsed"
        )
        
    with col_clear:
        if st.button("🗑️ Xóa toàn bộ file", use_container_width=True):
            st.session_state.gerber_uploader_key += 1
            st.session_state.pop("gerber_results", None)
            st.rerun()

    if uploaded_files:
        if st.button("🚀 Bắt đầu Quét Hệ thống & Đánh giá DFM", type="primary", use_container_width=True):
            
            api_key = st.secrets.get("macrofab", {}).get("api_key") or os.environ.get("MACROFAB_API_KEY", "DUMMY_KEY")
            jobs = group_uploaded_files(uploaded_files)
            
            st.info(f"Đã phân loại thành **{len(jobs)}** dự án PCB độc lập.")
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            results = []
            
            try:
                for idx, job in enumerate(jobs):
                    status_text.text(f"Đang xử lý [{idx+1}/{len(jobs)}]: {job['name']} ...")
                    
                    # 1. Đóng gói file cho job hiện tại
                    zip_data = prepare_gerber_zip(job['files'])
                    
                    # 2. Gọi API
                    res = upload_and_analyze_gerber(api_key, job['name'], zip_data)
                    results.append(res)
                    
                    progress_bar.progress((idx + 1) / len(jobs))
                    
                status_text.success("🎉 Hoàn tất kiểm tra kỹ thuật toàn bộ bo mạch!")
                st.session_state["gerber_results"] = results
                
            except Exception as e:
                st.error(f"❌ Có lỗi trong quá trình phân tích: {e}")

    # --- KHU VỰC HIỂN THỊ KẾT QUẢ & XUẤT EXCEL ---
    if "gerber_results" in st.session_state and st.session_state["gerber_results"]:
        results = st.session_state["gerber_results"]
        
        st.divider()
        col_title, col_export = st.columns([3, 1])
        col_title.markdown("### 📋 Báo Cáo Thông Số & DFM")
        
        excel_bytes = generate_pcb_report_excel(results)
        col_export.download_button(
            label="📥 Xuất Excel (Báo Cáo Chuẩn)",
            data=excel_bytes,
            file_name="PCB_DFM_Audit_Report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True
        )

        for res in results:
            name = res.get("pcb_name")
            params = res.get("parameters", {})
            warnings = res.get("dfm_warnings", [])
            
            icon = "🔴" if warnings else "🟢"
            with st.expander(f"{icon} Khối mạch: {name}", expanded=True):
                
                # Hiển thị tham số dạng bảng lưới 2 cột
                df_params = pd.DataFrame(list(params.items()), columns=["Thuộc Tính Kỹ Thuật", "Giá Trị Khảo Sát"])
                
                c_params, c_warnings = st.columns([1.5, 1])
                
                with c_params:
                    st.dataframe(df_params, use_container_width=True, hide_index=True, height=350)
                    
                with c_warnings:
                    if warnings:
                        st.error("⚠️ **Cảnh báo DFM & Rủi ro sản xuất:**")
                        for w in warnings:
                            st.markdown(f"- {w}")
                    else:
                        st.success("✅ **DFM Passed:** Không phát hiện bất thường.")
                        st.caption("Bo mạch đáp ứng tiêu chuẩn sản xuất cơ bản.")