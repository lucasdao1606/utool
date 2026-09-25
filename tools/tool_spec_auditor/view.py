import streamlit as st
import pandas as pd
import re
import os
import time
import zipfile
import io
import gc  # Thư viện thu gom rác giải phóng RAM
from datetime import datetime

from .parser_excel import parse_template_excel, save_audit_results_to_workbook
from .parser_pdf import extract_pdf_pages
from .engine_llm import audit_single_item_llm, generate_specs_llm
from .models import ItemAuditResult
from .api_datasheet import auto_fetch_datasheet

# Lấy đường dẫn tuyệt đối để người dùng dễ tìm thấy trên ổ cứng
DATASHEET_DIR = os.path.abspath(os.path.join(os.getcwd(), "datasheets"))
os.makedirs(DATASHEET_DIR, exist_ok=True)

def find_datasheet_name_for_tt(tt: int, folder_path: str):
    pattern = rf"^{tt}(?![0-9])"
    if not os.path.exists(folder_path):
        return None
    for filename in os.listdir(folder_path):
        if filename.lower().endswith('.pdf') and re.match(pattern, filename):
            return filename
    return None

def create_zip_of_datasheets(folder_path: str) -> bytes:
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        for file_name in os.listdir(folder_path):
            if file_name.lower().endswith('.pdf'):
                file_path = os.path.join(folder_path, file_name)
                zip_file.write(file_path, arcname=file_name)
    return zip_buffer.getvalue()

def render_spec_auditor_tool():
    st.subheader("🔬 Trợ lý Kỹ thuật: Đánh giá & Xây dựng Chỉ tiêu (AI)")
    
    # ---------------------------------------------------------------------
    # CƠ CHẾ DỪNG KHẨN CẤP (STOP FLAG)
    # ---------------------------------------------------------------------
    if "stop_process" not in st.session_state:
        st.session_state.stop_process = False

    try:
        gemini_api_key = st.secrets.get("GEMINI_API_KEY", "")
        mouser_section = st.secrets.get("mouser", {})
        mouser_api_key = mouser_section.get("api_key", "")
        digikey_section = st.secrets.get("digikey", {})
        digikey_client = digikey_section.get("client_id", "")
        digikey_secret = digikey_section.get("client_secret", "")
        
        with st.expander("🔍 KIỂM TRA TRẠNG THÁI API", expanded=False):
            col_k1, col_k2, col_k3 = st.columns(3)
            col_k1.write(f"- Gemini AI: {'✅ Đã nhận' if gemini_api_key else '❌ Trống'}")
            col_k2.write(f"- DigiKey: {'✅ Đã nhận' if (digikey_client and digikey_secret) else '❌ Trống'}")
            col_k3.write(f"- Mouser: {'✅ Đã nhận' if mouser_api_key else '❌ Trống'}")
    except Exception:
        gemini_api_key, mouser_api_key, digikey_client, digikey_secret = "", "", "", ""

    st.markdown("### 🎛️ Chọn Chế độ hoạt động")
    app_mode = st.radio(
        "Chế độ:",
        [
            "🔬 **Chế độ 1: Đánh giá chỉ tiêu kỹ thuật** (Cần file PDF tải sẵn, form CTKT_Temp_2)",
            "🪄 **Chế độ 2: Xây dựng chỉ tiêu kỹ thuật** (Cần file PDF tải sẵn, form CTKT_Temp_3)",
            "🌐 **Chế độ 3: Auto API Datasheet & Đánh giá** (Tự tìm PDF qua API, form CTKT_Temp_4)"
        ],
        index=0, label_visibility="collapsed"
    )
    
    if "Chế độ 1" in app_mode: mode_idx = 1
    elif "Chế độ 2" in app_mode: mode_idx = 2
    else: mode_idx = 3
    is_mode_audit = mode_idx in [1, 3]
    
    st.divider()

    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("#### 1. File Template (Excel)")
        template_filename = "CTKT_Temp_2.xlsx" if mode_idx == 1 else ("CTKT_Temp_3.xlsx" if mode_idx == 2 else "CTKT_Temp_4.xlsx")
        
        excel_file = st.file_uploader(f"Tải lên file {template_filename}:", type=["xlsx"], key=f"uploader_{mode_idx}")

    with col2:
        st.markdown("#### 2. Thư mục lưu Datasheet")
        st.info("📂 **Đường dẫn thực tế trên ổ cứng của bạn đang nằm ở đây:**")
        st.code(DATASHEET_DIR, language="bash") # Hiển thị đường dẫn rõ ràng để bạn copy dán vào Explorer

        current_files = [f for f in os.listdir(DATASHEET_DIR) if f.lower().endswith('.pdf')]
        total_pdfs = len(current_files)
        st.success(f"📦 Đang có sẵn **{total_pdfs}** file Datasheet đã được lưu.")
        
        if total_pdfs > 0:
            if st.button("🗑️ Xóa sạch thư mục Datasheet", use_container_width=True):
                for fname in current_files:
                    try: os.remove(os.path.join(DATASHEET_DIR, fname))
                    except: pass
                st.rerun()

    if not excel_file:
        return

    try:
        excel_bytes = excel_file.getvalue()
        wb, target_items = parse_template_excel(excel_bytes)
    except Exception as e:
        st.error(f"Lỗi đọc file Excel: {e}")
        return

    st.markdown("##### Phạm vi thực hiện")
    scope_options_list = ["Xử lý TOÀN BỘ hạng mục", "Chỉ chạy thử 5 mục đầu tiên"]
    if mode_idx != 3:
        scope_options_list.insert(0, "Chỉ xử lý các mục ĐÃ CÓ file Datasheet tải lên")
    scope_option = st.radio("Lựa chọn danh sách cần xử lý:", scope_options_list, index=0)

    items_to_process = []
    if "ĐÃ CÓ file" in scope_option:
        items_to_process = [it for it in target_items if find_datasheet_name_for_tt(it.tt, DATASHEET_DIR)]
    elif "Chạy thử 5 mục" in scope_option:
        items_to_process = target_items[:5]
    else:
        items_to_process = target_items

    # =====================================================================
    # NÚT BẤM BẮT ĐẦU VÀ DỪNG KHẨN CẤP
    # =====================================================================
    col_start, col_stop = st.columns(2)
    start_btn = col_start.button("🚀 BẮT ĐẦU TIẾN TRÌNH", type="primary", use_container_width=True)
    stop_btn = col_stop.button("🛑 DỪNG KHẨN CẤP & XUẤT FILE", type="secondary", use_container_width=True)

    if stop_btn:
        st.session_state.stop_process = True
        st.warning("Đã ghi nhận yêu cầu dừng. Hệ thống sẽ kết thúc sau khi hoàn thành mục hiện tại...")

    if start_btn:
        st.session_state.stop_process = False
        
        if not items_to_process:
            st.warning("Không có hạng mục nào thỏa mãn điều kiện.")
            return

        st.markdown("### ⏱ THEO DÕI THỜI GIAN THỰC")
        m1, m2, m3 = st.columns(3)
        ph_total = m1.empty()
        ph_downloaded = m2.empty()
        ph_processed = m3.empty()

        progress_bar = st.progress(0.0)
        status_box = st.empty()
        log_container = st.container(height=280, border=True)
        
        audit_results = []
        total_steps = len(items_to_process)
        
        # Biến đếm thời gian thực
        count_downloaded = 0
        count_processed = 0

        def log_msg(msg: str):
            ts = datetime.now().strftime("%H:%M:%S")
            log_container.markdown(f"`[{ts}]` {msg}")

        for idx, item in enumerate(items_to_process):
            # KIỂM TRA LỆNH DỪNG
            if st.session_state.stop_process:
                log_msg("🛑 ĐÃ NHẬN LỆNH DỪNG KHẨN CẤP TỪ NGƯỜI DÙNG!")
                break

            step_num = idx + 1
            progress_bar.progress(step_num / total_steps)
            status_box.markdown(f"**Đang xử lý [{step_num}/{total_steps}]:** TT {item.tt} - {item.name}")
            
            ph_total.metric("Tổng số mục", f"{step_num}/{total_steps}")

            pdf_name = find_datasheet_name_for_tt(item.tt, DATASHEET_DIR)

            # --- MODE 3: GỌI API LẤY FILE ---
            if not pdf_name and mode_idx == 3:
                log_msg(f"🌐 Đang quét API cho: '{item.part_number}'...")
                downloaded_name = auto_fetch_datasheet(
                    part_number=item.part_number, tt=item.tt, save_dir=DATASHEET_DIR,
                    mouser_key=mouser_api_key, dk_client=digikey_client, dk_secret=digikey_secret
                )
                if downloaded_name:
                    log_msg(f"✅ Đã tải & lưu vào ổ cứng: {downloaded_name}")
                    pdf_name = downloaded_name
                    count_downloaded += 1
                    ph_downloaded.metric("Đã tải thành công", count_downloaded)
                else:
                    log_msg(f"❌ Không tìm thấy file cho: '{item.part_number}'")

            if not pdf_name:
                res = ItemAuditResult(
                    tt=item.tt, row_idx=item.row_idx, name=item.name, part_number=item.part_number,
                    datasheet_file="Không có", thong_so_ky_thuat="Không có datasheet",
                    nhan_xet="Chưa có tài liệu", tham_chieu="-", ghi_chu="Thiếu file PDF",
                    de_xuat="Không có cơ sở đề xuất.", status="MISSING_DOC"
                )
                audit_results.append(res)
                continue

            # --- TRÍCH XUẤT VÀ PHÂN TÍCH AI ---
            pdf_path = os.path.join(DATASHEET_DIR, pdf_name)
            
            # Sử dụng with đảm bảo file được đóng ngay sau khi đọc
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()

            try:
                pages = extract_pdf_pages(file_bytes=pdf_bytes, api_key=gemini_api_key.strip(), log_callback=log_msg)
                pdf_full_text = "\n\n".join([f"--- TRANG {p['page_num']} ---\n{p['text']}" for p in pages])
            except Exception as e:
                pdf_full_text = ""
                
            # XÓA BIẾN VÀ BUỘC HỆ THỐNG DỌN DẸP RAM NGAY LẬP TỨC
            del pdf_bytes 
            del pages
            gc.collect()

            # LLM Engine
            if is_mode_audit:
                res = audit_single_item_llm(item=item, pdf_name=pdf_name, pdf_text=pdf_full_text, api_key=gemini_api_key.strip())
            else:
                res = generate_specs_llm(item=item, pdf_name=pdf_name, pdf_text=pdf_full_text, api_key=gemini_api_key.strip())

            # XÓA TIẾP TEXT PDF TRONG RAM
            del pdf_full_text
            gc.collect()

            audit_results.append(res)
            
            count_processed += 1
            ph_processed.metric("Đã phân tích AI", count_processed)

            # LƯU LŨY TIẾN (PROGRESSIVE SAVE): Đảm bảo dữ liệu không bao giờ mất
            st.session_state["audited_results_list"] = audit_results
            st.session_state["audited_excel_bytes"] = save_audit_results_to_workbook(wb, audit_results, is_mode_audit)
            st.session_state["last_mode_was_audit"] = is_mode_audit

            time.sleep(1)

        if st.session_state.stop_process:
            status_box.warning("⚠️ Tiến trình đã được dừng bởi người dùng. Bạn có thể tải kết quả các mục đã xử lý bên dưới.")
            st.session_state.stop_process = False
        else:
            status_box.success("🎉 Hoàn thành 100% tiến trình! Bạn có thể tải kết quả.")

    # =====================================================================
    # HIỂN THỊ KẾT QUẢ ĐÃ XỬ LÝ & TẢI FILE
    # =====================================================================
    if "audited_results_list" in st.session_state:
        results = st.session_state["audited_results_list"]
        st.markdown("### 📊 Tổng Hợp Kết Quả")
        
        miss_c = sum(1 for r in results if r.status == "MISSING_DOC")
        pass_c = sum(1 for r in results if r.nhan_xet == "Đạt")
        
        k1, k2, k3 = st.columns(3)
        k1.metric("Số mục đã lưu kết quả", len(results))
        k2.metric("Đạt yêu cầu / AI tạo thành công", pass_c if st.session_state.get("last_mode_was_audit") else sum(1 for r in results if r.status == "PASS"))
        k3.metric("Thiếu Datasheet", miss_c)

        st.markdown("#### 📥 Tải Dữ Liệu")
        col_btn1, col_btn2 = st.columns(2)
        
        with col_btn1:
            st.download_button(
                label="📊 Tải File Excel Kết Quả (Lưu tới mục hiện tại)",
                data=st.session_state["audited_excel_bytes"],
                file_name=f"KetQua_{excel_file.name}" if excel_file else "KetQua_CTKT.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True
            )
            
        with col_btn2:
            zip_data = create_zip_of_datasheets(DATASHEET_DIR)
            st.download_button(
                label="📚 Tải file nén toàn bộ Datasheet (ZIP)",
                data=zip_data,
                file_name=f"Datasheets_{datetime.now().strftime('%Y%m%d_%H%M')}.zip",
                mime="application/zip",
                use_container_width=True
            )