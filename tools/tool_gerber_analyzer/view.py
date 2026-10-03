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
    st.caption("Công cụ tự động upload hàng loạt cấu trúc Gerber để trích xuất tham số kỹ thuật, đánh giá DFM và xuất hình ảnh tự động cắt viền nền trắng.")

    if "gerber_uploader_key" not in st.session_state:
        st.session_state.gerber_uploader_key = 0

    col_upload, col_clear = st.columns([4, 1])
    
    with col_upload:
        allowed_extensions = [
            "zip", "rar", "gbr", "art", "drl", "xln", "txt", 
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
            st.session_state.pop("gerber_debug_logs", None)
            st.rerun()

    if uploaded_files:
        if st.button("🚀 Bắt đầu Quét Hệ thống & Đánh giá DFM", type="primary", use_container_width=True):
            
            api_key = st.secrets.get("macrofab", {}).get("api_key") or os.environ.get("MACROFAB_API_KEY", "DUMMY_KEY")
            jobs = group_uploaded_files(uploaded_files)
            
            st.info(f"Đã phân loại thành **{len(jobs)}** dự án PCB độc lập.")
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            results = []
            debug_logs = []
            
            try:
                for idx, job in enumerate(jobs):
                    status_text.text(f"Đang xử lý [{idx+1}/{len(jobs)}]: {job['name']} ...")
                    zip_data = prepare_gerber_zip(job['files'], debug_logs)
                    res = upload_and_analyze_gerber(api_key, job['name'], zip_data, debug_logs)
                    results.append(res)
                    progress_bar.progress((idx + 1) / len(jobs))
                    
                status_text.success("🎉 Hoàn tất kiểm tra kỹ thuật và kết xuất hình ảnh toàn bộ bo mạch!")
                st.session_state["gerber_results"] = results
                st.session_state["gerber_debug_logs"] = debug_logs
                
            except Exception as e:
                st.error(f"❌ Có lỗi trong quá trình phân tích: {e}")
                debug_logs.append(f"❌ NGOẠI LỆ NGHIÊM TRỌNG: {e}")
                st.session_state["gerber_debug_logs"] = debug_logs

    # --- KHU VỰC HIỂN THỊ KẾT QUẢ & XUẤT EXCEL ---
    if "gerber_results" in st.session_state and st.session_state["gerber_results"]:
        results = st.session_state["gerber_results"]
        
        st.divider()
        col_title, col_export = st.columns([3, 1])
        col_title.markdown("### 📋 Báo Cáo Thông Số & DFM")
        
        excel_bytes = generate_pcb_report_excel(results)
        col_export.download_button(
            label="📥 Xuất Excel (Báo Cáo + Ảnh Lớp)",
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
            layer_images = res.get("layer_images", [])
            
            icon = "🔴" if warnings else "🟢"
            with st.expander(f"{icon} Khối mạch: {name}", expanded=True):
                
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

                if layer_images:
                    st.markdown("#### 🖼️ Bản vẽ trực quan (Gerber Preview)")
                    img_cols = st.columns(2)
                    for i, img_info in enumerate(layer_images):
                        with img_cols[i % 2]:
                            st.image(
                                img_info["data"], 
                                caption=f"Lớp: {img_info['name']} ({img_info['filename']})", 
                                use_container_width=True
                            )

    # Bảng Log hệ thống giúp Debug
    if "gerber_debug_logs" in st.session_state and st.session_state["gerber_debug_logs"]:
        st.divider()
        with st.expander("🛠️ Xem nhật ký hệ thống (Debug Logs)", expanded=False):
            st.code("\n".join(st.session_state["gerber_debug_logs"]), language="text")