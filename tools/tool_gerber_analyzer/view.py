import streamlit as st
import os
import pandas as pd
from PIL import Image as PILImage
from tools.tool_gerber_analyzer.engine import (
    group_uploaded_files, 
    prepare_gerber_zip, 
    upload_and_analyze_gerber,
    generate_pcb_report_excel
)

PILImage.MAX_IMAGE_PIXELS = None

def get_secret_safely(section: str, key: str, fallback_flat_key: str = "") -> str:
    try:
        if section in st.secrets and key in st.secrets[section]:
            val = str(st.secrets[section][key]).strip()
            if val: return val
    except Exception: pass
    try:
        if fallback_flat_key and fallback_flat_key in st.secrets:
            val = str(st.secrets[fallback_flat_key]).strip()
            if val: return val
    except Exception: pass
    env_val = os.environ.get(f"{section.upper()}_{key.upper()}", "") or os.environ.get(fallback_flat_key.upper(), "")
    return env_val.strip()

def get_secret_list_safely(section: str, key: str, fallback_flat_key: str = "") -> list:
    """Hàm trích xuất an toàn định dạng List Array từ secrets.toml"""
    keys = []
    try:
        if section in st.secrets and key in st.secrets[section]:
            val = st.secrets[section][key]
            if isinstance(val, list): keys.extend(val)
            elif isinstance(val, str) and val.strip(): keys.append(val.strip())
    except Exception: pass
    try:
        if fallback_flat_key and fallback_flat_key in st.secrets:
            val = st.secrets[fallback_flat_key]
            if isinstance(val, list): keys.extend(val)
            elif isinstance(val, str) and val.strip(): keys.append(val.strip())
    except Exception: pass
    
    # Hỗ trợ lấy từ biến môi trường (Environment Variable), phân tách nhau bằng dấu phẩy
    env_val = os.environ.get(f"{section.upper()}_{key.upper()}", "") or os.environ.get(fallback_flat_key.upper(), "")
    if env_val:
        keys.extend([k.strip() for k in env_val.split(",") if k.strip()])
        
    # Loại bỏ các key rỗng và key bị trùng lặp
    return list(dict.fromkeys(k for k in keys if k))

def render_gerber_analyzer_tool():
    st.subheader("🎛️ Phân tích & Đánh giá Gerber PCB (Đa Mạch + Phân tích AI)")
    st.caption("Công cụ tự động đánh giá DFM, xử lý ảnh viền bo mạch và tích hợp Gemini AI đọc hiểu tài liệu sản xuất.")

    if "gerber_uploader_key" not in st.session_state:
        st.session_state.gerber_uploader_key = 0

    col_upload, col_clear = st.columns([4, 1])
    
    with col_upload:
        allowed_extensions = [
            "zip", "rar", "gbr", "art", "drl", "xln", "txt", "log", "rpt", "pdf", "inf",
            "gko", "gm1", "gm2", "gtl", "gbl", "gto", "gbo", "gts", "gbs"
        ]
        uploaded_files = st.file_uploader(
            "Tải lên các file Gerber (Khuyên dùng gói .zip, .rar có chứa file PDF/Log để AI phân tích tốt nhất)", 
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
        
        # --- BỐ CỤC 2 NÚT BẤM (START & STOP) ---
        col_start, col_stop = st.columns([3, 1])
        with col_start:
            start_btn = st.button("🚀 Bắt đầu Quét Hệ thống & Khởi động AI", type="primary", use_container_width=True)
        with col_stop:
            stop_btn = st.button("🛑 Dừng xử lý & Xuất file", use_container_width=True)

        if stop_btn:
            if "gerber_results" in st.session_state and len(st.session_state["gerber_results"]) > 0:
                st.warning("🛑 Đã nhận lệnh dừng! Dưới đây là kết quả của các bo mạch đã phân tích xong.")
            else:
                st.info("⚠️ Chưa có bo mạch nào được phân tích hoàn tất.")

        if start_btn:
            # Khởi tạo danh sách rỗng để lưu trữ tăng dần (Incremental Storage)
            st.session_state["gerber_results"] = []
            st.session_state["gerber_debug_logs"] = []
            
            mf_api_key = get_secret_safely("macrofab", "api_key", "MACROFAB_API_KEY")
            gemini_api_keys = get_secret_list_safely("gemini", "api_keys", "GEMINI_API_KEYS")
                
            jobs = group_uploaded_files(uploaded_files)
            st.info(f"Đã phân loại thành **{len(jobs)}** dự án PCB độc lập.")
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            try:
                for idx, job in enumerate(jobs):
                    def ui_status_update(msg):
                        status_text.info(f"⏳ **[{idx+1}/{len(jobs)}] Khối mạch {job['name']}** ➔ {msg}")

                    ui_status_update("Bắt đầu xử lý luồng công việc...")
                    
                    local_logs = []
                    zip_data = prepare_gerber_zip(job['files'], local_logs, status_callback=ui_status_update)
                    
                    res = upload_and_analyze_gerber(
                        mf_api_key=mf_api_key, 
                        gemini_api_keys=gemini_api_keys, 
                        pcb_name=job['name'], 
                        zip_data=zip_data, 
                        debug_logs=local_logs, 
                        status_callback=ui_status_update
                    )
                    
                    # QUAN TRỌNG: Lưu ngay lập tức vào Session State để tránh mất data khi người dùng bấm Stop
                    st.session_state["gerber_results"].append(res)
                    st.session_state["gerber_debug_logs"].extend(local_logs)
                    
                    progress_bar.progress((idx + 1) / len(jobs))
                    
                status_text.success("🎉 Quá trình phân tích hoàn tất!")
                
            except Exception as e:
                st.error(f"❌ Có lỗi trong quá trình phân tích: {e}")
                st.session_state["gerber_debug_logs"].append(f"❌ NGOẠI LỆ NGHIÊM TRỌNG: {e}")

    # --- KHU VỰC HIỂN THỊ KẾT QUẢ TỪ SESSION STATE ---
    if "gerber_results" in st.session_state and st.session_state["gerber_results"]:
        results = st.session_state["gerber_results"]
        
        st.divider()
        col_title, col_export = st.columns([3, 1])
        col_title.markdown("### 📋 Báo Cáo Thông Số & Đánh Giá AI")
        
        excel_bytes = generate_pcb_report_excel(results)
        col_export.download_button(
            label="📥 Xuất Báo Cáo Chuẩn (Excel)",
            data=excel_bytes,
            file_name="PCB_AI_Audit_Report.xlsx",
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
                
                df_params = pd.DataFrame(list(params.items()), columns=["Thuộc Tính (AI Combined)", "Giá Trị Báo Cáo"])
                c_params, c_warnings = st.columns([1.5, 1])
                
                with c_params:
                    st.dataframe(df_params, use_container_width=True, hide_index=True, height=450)
                    
                with c_warnings:
                    if warnings:
                        st.error("⚠️ **Cảnh báo DFM / Ý kiến của AI:**")
                        for w in warnings:
                            st.markdown(f"- {w}")
                    else:
                        st.success("✅ **Đánh giá Đạt:** Không có cảnh báo bất thường.")
                        st.caption("AI và Hệ thống đo đạc đồng thuận về thông số an toàn.")

                if layer_images:
                    st.markdown("#### 🖼️ Bản vẽ trực quan (Đã xử lý Autocrop)")
                    img_cols = st.columns(2)
                    for i, img_info in enumerate(layer_images):
                        with img_cols[i % 2]:
                            st.image(
                                img_info["data"], 
                                caption=f"Lớp: {img_info['name']} ({img_info['filename']})", 
                                use_container_width=True
                            )

    if "gerber_debug_logs" in st.session_state and st.session_state["gerber_debug_logs"]:
        st.divider()
        with st.expander("🛠️ Xem nhật ký hệ thống xử lý & AI (Debug Logs)", expanded=False):
            st.code("\n".join(st.session_state["gerber_debug_logs"]), language="text")