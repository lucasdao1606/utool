import streamlit as st
import pandas as pd
import re
import os
import time
from datetime import datetime

from .parser_excel import parse_template_excel, save_audit_results_to_workbook
from .parser_pdf import extract_pdf_pages
from .engine_llm import audit_single_item_llm
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
    st.subheader("🔬 Đối soát Bảng Chỉ tiêu Kỹ thuật & Datasheet PDF")
    st.caption("Tối ưu hóa VPS 1GB RAM: Trực tiếp ghi ổ đĩa phân mảnh (Chunking) & Giảm tải CPU.")

    with st.expander("⚙️ Cấu hình API & Tùy chọn", expanded=False):
        gemini_api_key = st.text_input(
            "Gemini API Key (Tự động đọc từ secret nếu để trống)",
            type="password"
        )

    # Khởi tạo khóa động (Dynamic Key) để reset hộp tải file liên tục
    if "uploader_key" not in st.session_state:
        st.session_state.uploader_key = 0

    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown("#### 1. File Bảng Chỉ tiêu (Excel)")
        template_path = os.path.join(os.path.dirname(__file__), "CTKT_Temp_2.xlsx")
        if os.path.exists(template_path):
            with open(template_path, "rb") as f:
                template_bytes = f.read()
            st.download_button(
                label="📥 Tải File Template Mẫu",
                data=template_bytes,
                file_name="CTKT_Temp_2.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

        excel_file = st.file_uploader("Chọn file template cần kiểm tra (.xlsx)", type=["xlsx"], key="audit_template")
        if excel_file:
            st.success(f"Đã nạp file: **{excel_file.name}**")

    with col2:
        st.markdown("#### 2. Nạp Datasheet (PDF)")
        
        tab1, tab2 = st.tabs(["📤 Tải mẻ liên tục (An toàn RAM)", "📂 Quét thư mục VPS"])
        
        with tab1:
            st.info("💡 **Mẹo an toàn cho VPS:** Kéo thả từng mẻ 10-30 file (Tối đa 200MB/mẻ). Hệ thống ghi theo phân mảnh (Chunking) 64KB để không làm đầy RAM.")
            
            # Sử dụng Dynamic Key để uploader luôn được làm mới sau khi nạp xong
            pdf_files = st.file_uploader(
                "Kéo thả Datasheet vào đây (Có thể dừng bất cứ lúc nào)",
                type=["pdf"],
                accept_multiple_files=True,
                key=f"audit_datasheet_uploader_{st.session_state.uploader_key}"
            )
            
            # Xử lý lưu phân mảnh (Chunking) và reset UI
            if pdf_files:
                new_count = 0
                for f in pdf_files:
                    file_path = os.path.join(DATASHEET_DIR, f.name)
                    if not os.path.exists(file_path):
                        # Ghi file theo từng khối nhỏ 64KB thay vì đọc cả cục bằng getvalue()
                        with open(file_path, "wb") as out_file:
                            while True:
                                chunk = f.read(65536)
                                if not chunk:
                                    break
                                out_file.write(chunk)
                        new_count += 1
                
                if new_count > 0:
                    # Tăng key để hộp upload tự xóa rỗng, nhảy số Live Counter
                    st.session_state.uploader_key += 1
                    st.rerun()

        with tab2:
            st.caption("Dùng phần mềm như WinSCP/FileZilla copy hàng loạt file vào thư mục sau để nhanh nhất (Không tốn RAM):")
            st.code(DATASHEET_DIR, language="bash")

        # Đếm file thực tế đang tồn tại trên ổ cứng (LIVE COUNTER)
        current_files = [f for f in os.listdir(DATASHEET_DIR) if f.lower().endswith('.pdf')]
        total_pdfs = len(current_files)
        
        # Hiển thị số lượng ngay lập tức
        if total_pdfs > 0:
            st.success(f"📦 **Kho dữ liệu (Ổ đĩa):** Đang có sẵn **{total_pdfs}** file Datasheet an toàn.")
            if st.button("🗑️ Xóa toàn bộ file trong ổ đĩa", use_container_width=True):
                for fname in current_files:
                    try:
                        os.remove(os.path.join(DATASHEET_DIR, fname))
                    except:
                        pass
                st.rerun()
        else:
            st.warning("📦 **Kho dữ liệu (Ổ đĩa):** Đang trống (0 file).")

    if not excel_file:
        st.info("Vui lòng tải lên file Excel bảng chỉ tiêu kỹ thuật để bắt đầu.")
        return

    try:
        excel_bytes = excel_file.getvalue()
        wb, target_items = parse_template_excel(excel_bytes)
    except Exception as e:
        st.error(f"Lỗi khi đọc file Excel: {e}")
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
            "Số chỉ tiêu": len(it.sub_specs),
            "File Datasheet": found_pdf_name if found_pdf_name else "❌ Chưa có file"
        })

    st.divider()
    c1, c2, c3 = st.columns(3)
    c1.metric("Tổng hạng mục trong Excel", len(target_items))
    c2.metric("Số file PDF trên ổ cứng", total_pdfs)
    c3.metric("Số mục đã khớp Datasheet", f"{matched_count}/{len(target_items)}")

    st.markdown("##### Phạm vi thực hiện đối soát")
    scope_option = st.radio(
        "Lựa chọn danh sách cần rà soát:",
        [
            "Chỉ đối soát các hạng mục ĐÃ CÓ file Datasheet tải lên (Nhanh & Tối ưu)",
            "Đối soát TOÀN BỘ hạng mục",
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

    with st.expander(f"👁️ Xem trước danh sách kiểm tra ({len(items_to_process)} hạng mục)", expanded=False):
        st.dataframe(pd.DataFrame(preview_rows), use_container_width=True, hide_index=True)

    if st.button("🚀 Bắt Đầu Quy Trình Rà Soát Kỹ Thuật", type="primary", use_container_width=True):
        if not items_to_process:
            st.warning("Không có hạng mục nào thỏa mãn điều kiện để đối soát.")
            return

        progress_bar = st.progress(0.0)
        status_box = st.empty()
        
        log_container = st.container(height=320, border=True)
        audit_results = []
        total_steps = len(items_to_process)

        def log_msg(msg: str):
            ts = datetime.now().strftime("%H:%M:%S")
            log_container.markdown(f"`[{ts}]` {msg}")

        log_msg(f"**BẮT ĐẦU ĐỐI SOÁT {total_steps} HẠNG MỤC...**")

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
                    nhan_xet="Chưa có tài liệu đối soát", tham_chieu="-", ghi_chu="Thiếu file",
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
                
            # Xóa biến bytes để giải phóng RAM lập tức
            del pdf_bytes 

            res = audit_single_item_llm(
                item=item, pdf_name=pdf_name, pdf_text=pdf_full_text,
                api_key=gemini_api_key.strip() if gemini_api_key else None
            )

            if res.nhan_xet == "Đạt":
                log_msg(f"🟢 KẾT QUẢ: **ĐẠT**")
            else:
                log_msg(f"🔴 KẾT QUẢ: **{res.nhan_xet.upper()}**")

            audit_results.append(res)
            
            # Thêm nhịp nghỉ 1.5 giây để hạ nhiệt CPU (Tránh treo VPS 1GB RAM)
            time.sleep(1.5)

        status_box.success("🎉 Hoàn thành chu trình rà soát! Hệ thống đã tự động dọn dẹp ổ đĩa.")
        updated_excel_bytes = save_audit_results_to_workbook(wb, audit_results)
        st.session_state["audited_excel_bytes"] = updated_excel_bytes
        st.session_state["audited_results_list"] = audit_results
        
        # Tự động dọn ổ đĩa sau khi chạy xong
        for fname in os.listdir(DATASHEET_DIR):
            if fname.lower().endswith('.pdf'):
                try:
                    os.remove(os.path.join(DATASHEET_DIR, fname))
                except:
                    pass

    if "audited_results_list" in st.session_state:
        results = st.session_state["audited_results_list"]
        st.markdown("### 📊 Tổng Hợp Kết Quả Rà Soát")
        
        pass_c = sum(1 for r in results if r.nhan_xet == "Đạt")
        fail_c = sum(1 for r in results if r.nhan_xet == "Không đạt")
        miss_c = sum(1 for r in results if r.status == "MISSING_DOC")

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Số mục đã rà soát", len(results))
        k2.metric("Đạt yêu cầu", pass_c)
        k3.metric("Không đạt / Cần làm rõ", fail_c)
        k4.metric("Thiếu Datasheet", miss_c)

        rows_display = [{
            "TT": r.tt, "Hạng mục": r.name, "Mã NSX": r.part_number,
            "Nhận xét": "🟢 Đạt" if r.nhan_xet == "Đạt" else f"🔴 {r.nhan_xet}",
            "Đề xuất hiệu chỉnh": r.de_xuat, "Ghi chú": r.ghi_chu, "Tham chiếu": r.tham_chieu
        } for r in results]

        st.dataframe(pd.DataFrame(rows_display), use_container_width=True, hide_index=True)

        st.download_button(
            label="📥 Tải File Excel Đã Đối Soát",
            data=st.session_state["audited_excel_bytes"],
            file_name=f"KetQua_DoiSoat_{excel_file.name}",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True
        )