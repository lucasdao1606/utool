import streamlit as st
import pandas as pd
import re
import os
from datetime import datetime

from .parser_excel import parse_template_excel, save_audit_results_to_workbook
from .parser_pdf import extract_pdf_pages
from .engine_llm import audit_single_item_llm
from .models import ItemAuditResult

def find_datasheet_for_tt(tt: int, uploaded_pdfs_dict: dict):
    """
    Tìm file PDF bắt đầu bằng số TT tương ứng (ví dụ: 1.LNB.pdf, 1_Digi.pdf, 1-Module.pdf).
    """
    pattern = rf"^{tt}(?![0-9])"
    for filename, pdf_bytes in uploaded_pdfs_dict.items():
        if re.match(pattern, filename):
            return filename, pdf_bytes
    return None, None

def render_spec_auditor_tool():
    st.subheader("🔬 Đối soát Bảng Chỉ tiêu Kỹ thuật & Datasheet PDF")
    st.caption("Tự động đọc danh sách chỉ tiêu theo số TT, ghép nối Datasheet tương ứng và điền trực tiếp kết quả vào file Excel.")

    with st.expander("⚙️ Cấu hình API & Tùy chọn", expanded=False):
        gemini_api_key = st.text_input(
            "Gemini API Key (Khuyên dùng để kích hoạt Vision OCR và phân tích logic)",
            type="password",
            help="Nếu để trống, hệ thống sẽ sử dụng bộ phân tích Heuristic Offline."
        )

    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown("#### 1. File Bảng Chỉ tiêu Kỹ thuật (Excel)")
        
        # Nút tải file Template
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
        else:
            st.caption("*(💡 Đặt file `CTKT_Temp_2.xlsx` vào cùng thư mục chứa code để hiển thị nút tải template)*")

        excel_file = st.file_uploader(
            "Chọn file template cần kiểm tra (.xlsx)",
            type=["xlsx"],
            key="audit_template_uploader"
        )
        if excel_file:
            st.success(f"Đã nạp file: **{excel_file.name}**")

    with col2:
        st.markdown("#### 2. Thư mục / Danh sách Datasheet (PDF)")
        pdf_files = st.file_uploader(
            "Chọn một hoặc nhiều file PDF datasheet (Ví dụ: 1.LNB.pdf, 2.BUC.pdf)",
            type=["pdf"],
            accept_multiple_files=True,
            key="audit_datasheet_uploader"
        )
        if pdf_files:
            st.info(f"Đã nạp **{len(pdf_files)}** file Datasheet PDF.")

    if not excel_file:
        st.info("Vui lòng tải lên file Excel bảng chỉ tiêu kỹ thuật để bắt đầu.")
        return

    # Đọc và kiểm tra file Excel
    try:
        excel_bytes = excel_file.getvalue()
        wb, target_items = parse_template_excel(excel_bytes)
    except Exception as e:
        st.error(f"Lỗi khi đọc file Excel: {e}")
        return

    # Tạo dictionary lưu trữ PDF
    pdf_dict = {f.name: f.getvalue() for f in pdf_files} if pdf_files else {}

    # Thống kê số lượng ghép nối được
    matched_count = 0
    preview_rows = []
    for it in target_items:
        found_pdf, _ = find_datasheet_for_tt(it.tt, pdf_dict)
        if found_pdf:
            matched_count += 1
        preview_rows.append({
            "TT": it.tt,
            "Nội dung": it.name,
            "Mã NSX": it.part_number,
            "Số chỉ tiêu": len(it.sub_specs),
            "File Datasheet ghép nối": found_pdf if found_pdf else "❌ Chưa có file"
        })

    st.divider()
    c1, c2, c3 = st.columns(3)
    c1.metric("Tổng hạng mục trong Excel", len(target_items))
    c2.metric("Số file PDF đã tải lên", len(pdf_dict))
    c3.metric("Số mục đã khớp Datasheet", f"{matched_count}/{len(target_items)}")

    # Lựa chọn phạm vi kiểm tra
    st.markdown("##### Phạm vi thực hiện đối soát")
    scope_option = st.radio(
        "Lựa chọn danh sách cần rà soát:",
        [
            "Chỉ đối soát các hạng mục ĐÃ CÓ file Datasheet tải lên (Nhanh & Tối ưu)",
            "Đối soát TOÀN BỘ hạng mục (Các mục thiếu file sẽ ghi nhận chưa có tài liệu)",
            "Chỉ chạy thử 5 mục đầu tiên"
        ],
        index=0
    )

    items_to_process = []
    if "ĐÃ CÓ file Datasheet" in scope_option:
        items_to_process = [it for it in target_items if find_datasheet_for_tt(it.tt, pdf_dict)[0]]
    elif "Chạy thử 5 mục" in scope_option:
        items_to_process = target_items[:5]
    else:
        items_to_process = target_items

    with st.expander(f"👁️ Xem trước danh sách kiểm tra ({len(items_to_process)} hạng mục)", expanded=False):
        st.dataframe(pd.DataFrame(preview_rows), use_container_width=True, hide_index=True)

    # Nút bắt đầu chạy
    if st.button("🚀 Bắt Đầu Quy Trình Rà Soát Kỹ Thuật", type="primary", use_container_width=True):
        if not items_to_process:
            st.warning("Không có hạng mục nào thỏa mãn điều kiện để đối soát.")
            return

        progress_bar = st.progress(0.0)
        status_box = st.empty()
        
        st.markdown("##### 🖥️ Cửa Sổ Giám Sát Chu Trình (Live Debug & Logs):")
        log_container = st.container(height=320, border=True)

        audit_results = []
        total_steps = len(items_to_process)

        def log_msg(msg: str):
            ts = datetime.now().strftime("%H:%M:%S")
            log_container.markdown(f"`[{ts}]` {msg}")

        log_msg(f"**BẮT ĐẦU CHU TRÌNH ĐỐI SOÁT CHO {total_steps} HẠNG MỤC...**")

        for idx, item in enumerate(items_to_process):
            step_num = idx + 1
            progress_bar.progress(step_num / total_steps)
            status_box.markdown(f"**Đang xử lý [{step_num}/{total_steps}]:** TT {item.tt} - {item.name}")

            log_msg(f"**[Bước {step_num}/{total_steps}]** Đang xử lý **TT {item.tt}: {item.name}** (Mã: `{item.part_number}`) | Số chỉ tiêu: {len(item.sub_specs)}")

            # 1. Tìm file datasheet
            pdf_name, pdf_bytes = find_datasheet_for_tt(item.tt, pdf_dict)

            if not pdf_name:
                log_msg(f"⚠️ **TT {item.tt}**: Không tìm thấy file PDF bắt đầu bằng số `{item.tt}.`")
                res = ItemAuditResult(
                    tt=item.tt, row_idx=item.row_idx, name=item.name, part_number=item.part_number,
                    datasheet_file="Không có", thong_so_ky_thuat="Không có datasheet để kiểm tra",
                    nhan_xet="Chưa có tài liệu đối soát", tham_chieu="-", ghi_chu="Thiếu file PDF datasheet",
                    de_xuat="Không có cơ sở để đề xuất do thiếu tài liệu.", status="MISSING_DOC"
                )
                audit_results.append(res)
                continue

            log_msg(f"📄 **TT {item.tt}**: Đã ghép nối Datasheet: `{pdf_name}`")

            # 2. Trích xuất nội dung PDF (Tích hợp Vision OCR)
            log_msg(f"⏳ **TT {item.tt}**: Đang trích xuất nội dung từ `{pdf_name}`...")
            try:
                pages = extract_pdf_pages(
                    file_bytes=pdf_bytes,
                    api_key=gemini_api_key.strip() if gemini_api_key else None,
                    log_callback=log_msg
                )
                pdf_full_text = "\n\n".join([f"--- TRANG {p['page_num']} ---\n{p['text']}" for p in pages])
                log_msg(f"✅ **TT {item.tt}**: Đã trích xuất {len(pages)} trang ({len(pdf_full_text)} ký tự).")
            except Exception as e:
                log_msg(f"❌ **TT {item.tt}**: Lỗi khi đọc file PDF `{pdf_name}`: {str(e)}")
                pdf_full_text = ""

            # 3. Gọi Engine đối soát
            log_msg(f"🧠 **TT {item.tt}**: Bắt đầu đối soát từng chỉ tiêu với nội dung datasheet...")
            res = audit_single_item_llm(
                item=item,
                pdf_name=pdf_name,
                pdf_text=pdf_full_text,
                api_key=gemini_api_key.strip() if gemini_api_key else None
            )

            # Log kết quả chi tiết
            if res.nhan_xet == "Đạt":
                log_msg(f"🟢 **TT {item.tt}**: KẾT QUẢ: **ĐẠT** (Toàn bộ {len(item.sub_specs)} chỉ tiêu đều đáp ứng)")
            else:
                log_msg(f"🔴 **TT {item.tt}**: KẾT QUẢ: **{res.nhan_xet.upper()}** | Lưu ý: {res.ghi_chu}")

            audit_results.append(res)

        status_box.success("🎉 Hoàn thành chu trình rà soát cho toàn bộ các hạng mục đã chọn!")
        log_msg("🏁 **HOÀN THÀNH TOÀN BỘ CHU TRÌNH RÀ SOÁT.**")

        # Ghi kết quả vào Workbook gốc
        updated_excel_bytes = save_audit_results_to_workbook(wb, audit_results)
        st.session_state["audited_excel_bytes"] = updated_excel_bytes
        st.session_state["audited_results_list"] = audit_results

    # Hiển thị kết quả tổng hợp và nút tải xuống
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

        # Bảng kết quả
        rows_display = []
        for r in results:
            rows_display.append({
                "TT": r.tt,
                "Hạng mục": r.name,
                "Mã NSX": r.part_number,
                "Nhận xét": "🟢 Đạt" if r.nhan_xet == "Đạt" else f"🔴 {r.nhan_xet}",
                "Đề xuất hiệu chỉnh (Cột 11)": r.de_xuat,
                "Ghi chú (Cột 10)": r.ghi_chu,
                "Tham chiếu (Cột 9)": r.tham_chieu,
                "Thông số thực tế": r.thong_so_ky_thuat[:100] + "..." if len(r.thong_so_ky_thuat) > 100 else r.thong_so_ky_thuat
            })

        st.dataframe(pd.DataFrame(rows_display), use_container_width=True, hide_index=True)

        st.download_button(
            label="📥 Tải File Excel Đã Đối Soát (Giữ nguyên định dạng gốc)",
            data=st.session_state["audited_excel_bytes"],
            file_name=f"KetQua_DoiSoat_{excel_file.name}",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True
        )