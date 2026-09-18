import io
import os
import streamlit as st
from tools.tool_docx_converter.engine import (
    inspect_docx_tables,
    convert_docx_table_to_excel_buffer,
    save_excel_to_local_path
)

def render_docx_converter_tool():
    st.header("📄 Chuyển đổi Bảng DOCX sang Excel")
    st.caption("Trích xuất bảng biểu kỹ thuật từ Word sang Excel chuẩn định dạng, giữ nguyên xuống dòng và viền khung.")

    tab1, tab2 = st.tabs(["🚀 Xử lý & Xuất file", "📖 Hướng dẫn & Lưu ý"])

    with tab1:
        uploaded_file = st.file_uploader(
            "Chọn file tài liệu Word (.docx):",
            type=["docx"],
            help="Hỗ trợ file .docx chứa bảng tiêu chuẩn hoặc bảng kỹ thuật."
        )

        if uploaded_file is not None:
            file_bytes = uploaded_file.read()
            try:
                tables_info = inspect_docx_tables(io.BytesIO(file_bytes))
            except Exception as e:
                st.error(f"❌ Không thể đọc file DOCX: {str(e)}")
                return

            if not tables_info:
                st.warning("⚠️ File Word này không chứa bất kỳ bảng (table) nào!")
                return

            st.success(f"🔍 Phát hiện **{len(tables_info)}** bảng trong tài liệu.")

            col_sel, col_name = st.columns([1, 1])
            with col_sel:
                table_options = [
                    f"Bảng {t['index'] + 1} ({t['rows']} dòng x {t['cols']} cột) - {t['preview']}"
                    for t in tables_info
                ]
                selected_opt = st.selectbox("Chọn bảng cần xuất:", table_options, index=0)
                chosen_index = int(selected_opt.split()[1]) - 1

            with col_name:
                default_name = os.path.splitext(uploaded_file.name)[0] + ".xlsx"
                custom_excel_name = st.text_input("Tên file Excel xuất ra:", value=default_name)

            st.divider()

            # Nút thực thi
            if st.button("⚙️ Bắt đầu xử lý & Trích xuất", type="primary"):
                with st.spinner("Đang trích xuất dữ liệu và định dạng ô..."):
                    try:
                        excel_buffer = convert_docx_table_to_excel_buffer(
                            io.BytesIO(file_bytes),
                            table_index=chosen_index
                        )
                        st.session_state["docx_excel_data"] = excel_buffer.getvalue()
                        st.session_state["docx_excel_filename"] = custom_excel_name
                        st.success("✅ Đã xử lý thành công bảng dữ liệu sang định dạng Excel!")
                    except Exception as e:
                        st.error(f"❌ Xử lý thất bại: {str(e)}")

            # Khu vực xuất file
            if "docx_excel_data" in st.session_state and st.session_state["docx_excel_data"]:
                st.markdown("### 📥 Tùy chọn xuất file")
                
                # Tùy chọn 1: Tải về trình duyệt
                st.download_button(
                    label="💾 Tải trực tiếp về máy tính (Thư mục Downloads trình duyệt)",
                    data=st.session_state["docx_excel_data"],
                    file_name=st.session_state.get("docx_excel_filename", "output.xlsx"),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

                st.markdown("---")
                
                # Tùy chọn 2: Lưu trực tiếp vào thư mục chỉ định trên ổ đĩa
                st.markdown("##### 📁 Hoặc lưu trực tiếp vào thư mục chỉ định:")
                st.caption("Nhập đường dẫn thư mục mong muốn trên máy tính cá nhân.")
                
                col_path, col_save = st.columns([3, 1])
                with col_path:
                    target_dir = st.text_input(
                        "Đường dẫn thư mục lưu trữ:",
                        value=os.path.expanduser("~/Downloads"),
                        placeholder="Ví dụ: D:/BaoCao/Excel hoặc /home/user/output"
                    )
                with col_save:
                    st.write("")
                    st.write("")
                    save_btn = st.button("Lưu vào thư mục")

                if save_btn:
                    if not target_dir.strip():
                        st.warning("⚠️ Vui lòng nhập đường dẫn thư mục!")
                    else:
                        try:
                            saved_path = save_excel_to_local_path(
                                excel_bytes=st.session_state["docx_excel_data"],
                                target_directory=target_dir,
                                filename=st.session_state.get("docx_excel_filename", "output.xlsx")
                            )
                            st.success(f"🎉 Đã lưu file thành công tại: `{saved_path}`")
                        except Exception as e:
                            st.error(f"❌ Không thể lưu vào thư mục đã chọn: {str(e)}")

    with tab2:
        st.markdown("""
        ### Đặc điểm kỹ thuật:
        - **Bảo toàn xuống dòng:** Nội dung văn bản nhiều dòng trong 1 ô được giữ nguyên và tự động bật chế độ `wrap_text`.
        - **Khung viền bảng:** Kẻ viền đen mỏng xung quanh tất cả các ô dữ liệu.
        - **Header:** Tô màu nền tiêu chuẩn `#D9E1F2`, font chữ Arial in đậm, căn giữa.
        - **Độ rộng cột:** Tự động co giãn phù hợp với dòng dài nhất trong cột.
        """)