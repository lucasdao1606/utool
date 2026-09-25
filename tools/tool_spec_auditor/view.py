import streamlit as st
import pandas as pd
import re
import os
import time
from datetime import datetime

from .parser_excel import parse_template_excel, save_audit_results_to_workbook
from .parser_pdf import extract_pdf_pages
from .engine_llm import audit_single_item_llm, generate_specs_llm
from .models import ItemAuditResult

# Thư mục lưu trữ tĩnh trên ổ cứng VPS
DATASHEET_DIR = os.path.join(os.getcwd(), "datasheets")
os.makedirs(DATASHEET_DIR, exist_ok=True)

def find_datasheet_name_for_tt(tt: int, folder_path: str):
    """Chỉ tìm tên file để hiển thị (Không nạp vào RAM)"""
    pattern = rf"^{tt}(?![0-9])"
    if not os.path.exists(folder_path):
        return None
    for filename in os.listdir(folder_path):
        if filename.lower().endswith('.pdf') and re.match(pattern, filename):
            return filename
    return None

def render_spec_auditor_tool():
    st.subheader("🔬 Trợ lý Kỹ thuật: Đánh giá & Xây dựng Chỉ tiêu (AI)")
    st.caption("Công cụ tự động hóa đọc Datasheet, đánh giá thông số hoặc tự động xây dựng bảng Yêu cầu Kỹ thuật.")

    with st.expander("⚙️ Cấu hình API & Tùy chọn", expanded=False):
        gemini_api_key = st.text_input(
            "Gemini API Key (Tự động đọc từ secret nếu để trống)",
            type="password"
        )

    # 🎛️ Nút chọn chế độ hoạt động (DUAL MODE)
    st.markdown("### 🎛️ Chọn Chế độ hoạt động")
    app_mode = st.radio(
        "Chế độ:",
        [
            "🔬 **Chế độ 1: Đánh giá chỉ tiêu kỹ thuật** (Chấm điểm Đạt/Không đạt dựa trên YCKT đã có trong form)",
            "🪄 **Chế độ 2: Xây dựng chỉ tiêu kỹ thuật** (AI đọc PDF và tự động viết YCKT cho form trống)"
        ],
        index=0,
        label_visibility="collapsed"
    )
    
    # Nhận diện chế độ ngay lập tức để điều hướng
    is_mode_audit = "Chế độ 1" in app_mode
    
    st.divider()

    # Khởi tạo khóa động (Dynamic Key) để reset hộp tải file liên tục
    if "uploader_key" not in st.session_state:
        st.session_state.uploader_key = 0

    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown("#### 1. File Template (Excel)")
        
        # Luân chuyển template động dựa trên chế độ đang chọn
        template_filename = "CTKT_Temp_2.xlsx" if is_mode_audit else "CTKT_Temp_3.xlsx"
        template_path = os.path.join(os.path.dirname(__file__), template_filename)
        
        if os.path.exists(template_path):
            with open(template_path, "rb") as f:
                template_bytes = f.read()
            st.download_button(
                label=f"📥 Tải File Template Mẫu ({template_filename})",
                data=template_bytes,
                file_name=template_filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        else:
            st.error(f"⚠️ Hệ thống không tìm thấy file gốc `{template_filename}` trong thư mục mã nguồn!")

        # Dynamic Key: Ép Streamlit reset bộ nhớ hộp tải file khi chuyển chế độ
        dynamic_upload_key = f"audit_template_mode_{'1' if is_mode_audit else '2'}"
        excel_file = st.file_uploader(
            f"Tải lên file {template_filename} đã điền:", 
            type=["xlsx"], 
            key=dynamic_upload_key
        )
        
        if excel_file:
            st.success(f"Đã nạp file: **{excel_file.name}**")

    with col2:
        st.markdown("#### 2. Nạp Datasheet (PDF)")
        
        tab1, tab2 = st.tabs(["📤 Tải mẻ liên tục (An toàn RAM)", "📂 Quét thư mục VPS"])
        
        with tab1:
            st.info("💡 **Mẹo an toàn cho VPS:** Kéo thả từng mẻ 10-30 file. Hệ thống tự động chia nhỏ (Chunking) 64KB để bảo vệ RAM.")
            pdf_files = st.file_uploader(
                "Kéo thả Datasheet vào đây",
                type=["pdf"],
                accept_multiple_files=True,
                key=f"audit_datasheet_uploader_{st.session_state.uploader_key}"
            )
            
            if pdf_files:
                new_count = 0
                for f in pdf_files:
                    file_path = os.path.join(DATASHEET_DIR, f.name)
                    if not os.path.exists(file_path):
                        with open(file_path, "wb") as out_file:
                            while True:
                                chunk = f.read(65536)
                                if not chunk:
                                    break
                                out_file.write(chunk)
                        new_count += 1
                
                if new_count > 0:
                    st.session_state.uploader_key += 1
                    st.rerun()

        with tab2:
            st.caption("Dùng phần mềm như WinSCP copy file vào thư mục sau để nhanh nhất:")
            st.code(DATASHEET_DIR, language="bash")

        current_files = [f for f in os.listdir(DATASHEET_DIR) if f.lower().endswith('.pdf')]
        total_pdfs = len(current_files)
        
        if total_pdfs > 0:
            st.success(f"📦 **Kho dữ liệu (Ổ đĩa):** Đang có sẵn **{total_pdfs}** file Datasheet.")
            if st.button("🗑️ Xóa toàn bộ file trong ổ đĩa", use_container_width=True):
                for fname in current_files:
                    try:
                        os.remove(os.path.join(DATASHEET_DIR, fname))
                    except:
                        pass
                st.rerun()
        else:
            st.warning("📦 **Kho dữ liệu (Ổ đĩa):** Đang trống (0 file).")

    # KIỂM TRA ĐIỀU KIỆN ĐỂ HIỂN THỊ NÚT BẤM
    if not excel_file:
        st.info("👆 Vui lòng tải lên Bảng chỉ tiêu Excel ở Bước 1 để mở khóa tính năng Xử lý.")
        st.button("🚀 Bắt Đầu Tiến Trình AI", type="primary", use_container_width=True, disabled=True)
        return

    try:
        excel_bytes = excel_file.getvalue()
        wb, target_items = parse_template_excel(excel_bytes)
    except Exception as e:
        st.error(f"Lỗi khi đọc file Excel: {e}")
        st.button("🚀 Bắt Đầu Tiến Trình AI", type="primary", use_container_width=True, disabled=True)
        return

    matched_count = 0
    preview_rows = []
    for it in target_items:
        found_pdf_name = find_datasheet_name_for_tt(it.tt, DATASHEET_DIR)
        if found_pdf_name:
            matched_count += 1
        preview_rows.append({
            "TT": it.tt,
            "Nội dung": it.name,
            "Mã NSX": it.part_number,
            "Trạng thái Datasheet": found_pdf_name if found_pdf_name else "❌ Chưa có file"
        })

    st.divider()
    c1, c2, c3 = st.columns(3)
    c1.metric("Tổng hạng mục trong Excel", len(target_items))
    c2.metric("Số file PDF trên ổ cứng", total_pdfs)
    c3.metric("Số mục đã khớp Datasheet", f"{matched_count}/{len(target_items)}")

    st.markdown("##### Phạm vi thực hiện")
    scope_option = st.radio(
        "Lựa chọn danh sách cần xử lý:",
        [
            "Chỉ xử lý các hạng mục ĐÃ CÓ file Datasheet tải lên (Nhanh & Tối ưu)",
            "Xử lý TOÀN BỘ hạng mục",
            "Chỉ chạy thử 5 mục đầu tiên"
        ],
        index=0
    )

    items_to_process = []
    if "ĐÃ CÓ file Datasheet" in scope_option:
        items_to_process = [it for it in target_items if find_datasheet_name_for_tt(it.tt, DATASHEET_DIR)]
    elif "Chạy thử 5 mục" in scope_option:
        items_to_process = target_items[:5]
    else:
        items_to_process = target_items

    with st.expander(f"👁️ Xem trước danh sách ({len(items_to_process)} hạng mục)", expanded=False):
        st.dataframe(pd.DataFrame(preview_rows), use_container_width=True, hide_index=True)

    # NÚT BẤM ĐÃ ĐƯỢC MỞ KHÓA
    if st.button("🚀 Bắt Đầu Tiến Trình AI", type="primary", use_container_width=True):
        if not items_to_process:
            st.warning("Không có hạng mục nào thỏa mãn điều kiện.")
            return

        progress_bar = st.progress(0.0)
        status_box = st.empty()
        
        log_container = st.container(height=320, border=True)
        audit_results = []
        total_steps = len(items_to_process)

        def log_msg(msg: str):
            ts = datetime.now().strftime("%H:%M:%S")
            log_container.markdown(f"`[{ts}]` {msg}")

        mode_str = "ĐÁNH GIÁ CHỈ TIÊU KỸ THUẬT" if is_mode_audit else "XÂY DỰNG CHỈ TIÊU KỸ THUẬT"
        log_msg(f"**BẮT ĐẦU CHU TRÌNH {mode_str} CHO {total_steps} HẠNG MỤC...**")

        for idx, item in enumerate(items_to_process):
            step_num = idx + 1
            progress_bar.progress(step_num / total_steps)
            status_box.markdown(f"**Đang xử lý [{step_num}/{total_steps}]:** TT {item.tt} - {item.name}")

            pdf_name = find_datasheet_name_for_tt(item.tt, DATASHEET_DIR)

            if not pdf_name:
                log_msg(f"⚠️ **TT {item.tt}**: Ghi nhận thiếu tài liệu.")
                res = ItemAuditResult(
                    tt=item.tt, row_idx=item.row_idx, name=item.name, part_number=item.part_number,
                    datasheet_file="Không có", thong_so_ky_thuat="Không có datasheet",
                    nhan_xet="Chưa có tài liệu", tham_chieu="-", ghi_chu="Thiếu file",
                    de_xuat="Không có cơ sở đề xuất.", status="MISSING_DOC"
                )
                audit_results.append(res)
                continue

            log_msg(f"📄 Đang đọc file vật lý vào RAM: `{pdf_name}`...")
            
            pdf_path = os.path.join(DATASHEET_DIR, pdf_name)
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()

            try:
                pages = extract_pdf_pages(
                    file_bytes=pdf_bytes,
                    api_key=gemini_api_key.strip() if gemini_api_key else None,
                    log_callback=log_msg
                )
                pdf_full_text = "\n\n".join([f"--- TRANG {p['page_num']} ---\n{p['text']}" for p in pages])
            except Exception as e:
                log_msg(f"❌ Lỗi đọc file: {str(e)}")
                pdf_full_text = ""
                
            del pdf_bytes 

            # PHÂN NHÁNH LOGIC THEO CHẾ ĐỘ
            if is_mode_audit:
                res = audit_single_item_llm(
                    item=item, pdf_name=pdf_name, pdf_text=pdf_full_text,
                    api_key=gemini_api_key.strip() if gemini_api_key else None
                )
                log_msg(f"{'🟢 ĐẠT' if res.nhan_xet == 'Đạt' else '🔴 KHÔNG ĐẠT/LỖI'}")
            else:
                res = generate_specs_llm(
                    item=item, pdf_name=pdf_name, pdf_text=pdf_full_text,
                    api_key=gemini_api_key.strip() if gemini_api_key else None
                )
                log_msg(f"🪄 Đã xây dựng xong chỉ tiêu kỹ thuật đề xuất!")

            audit_results.append(res)
            time.sleep(1.5)

        status_box.success("🎉 Hoàn thành tiến trình! Hệ thống đã tự động dọn dẹp ổ đĩa.")
        updated_excel_bytes = save_audit_results_to_workbook(wb, audit_results, is_mode_audit)
        st.session_state["audited_excel_bytes"] = updated_excel_bytes
        st.session_state["audited_results_list"] = audit_results
        st.session_state["last_mode_was_audit"] = is_mode_audit
        
        for fname in os.listdir(DATASHEET_DIR):
            if fname.lower().endswith('.pdf'):
                try: os.remove(os.path.join(DATASHEET_DIR, fname))
                except: pass

    if "audited_results_list" in st.session_state:
        results = st.session_state["audited_results_list"]
        st.markdown("### 📊 Tổng Hợp Kết Quả")
        
        miss_c = sum(1 for r in results if r.status == "MISSING_DOC")

        if st.session_state.get("last_mode_was_audit", True):
            pass_c = sum(1 for r in results if r.nhan_xet == "Đạt")
            fail_c = sum(1 for r in results if r.nhan_xet != "Đạt" and r.status != "MISSING_DOC")
            
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Số mục đã đánh giá", len(results))
            k2.metric("Đạt yêu cầu", pass_c)
            k3.metric("Không đạt / Cần làm rõ", fail_c)
            k4.metric("Thiếu Datasheet", miss_c)

            rows_display = [{
                "TT": r.tt, "Hạng mục": r.name, "Mã NSX": r.part_number,
                "Nhận xét": "🟢 Đạt" if r.nhan_xet == "Đạt" else f"🔴 {r.nhan_xet}",
                "Đề xuất hiệu chỉnh": r.de_xuat, "Tham chiếu": r.tham_chieu
            } for r in results]
        else:
            success_c = sum(1 for r in results if r.status == "PASS")
            
            k1, k2, k3 = st.columns(3)
            k1.metric("Số mục yêu cầu xây dựng", len(results))
            k2.metric("Xây dựng thành công", success_c)
            k3.metric("Thiếu Datasheet", miss_c)

            rows_display = [{
                "TT": r.tt, "Hạng mục": r.name, "Mã NSX": r.part_number,
                "Bản nháp YCKT (AI viết)": r.de_xuat, "Ghi chú": r.ghi_chu
            } for r in results]

        st.dataframe(pd.DataFrame(rows_display), use_container_width=True, hide_index=True)

        st.download_button(
            label="📥 Tải File Excel Kết Quả",
            data=st.session_state["audited_excel_bytes"],
            file_name=f"KetQua_{excel_file.name}",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True
        )