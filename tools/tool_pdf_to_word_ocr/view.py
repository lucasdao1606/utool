import streamlit as st
import os
from .engine import process_pdf_to_docx

def render_pdf_to_word_tool():
    st.header("📑 Chuyển đổi PDF/Scan sang Word (PP-StructureV2)")
    st.caption("Trích xuất văn bản tiếng Việt và tái tạo cấu trúc bảng biểu sang file .docx")

    col1, col2 = st.columns([3, 1])
    with col1:
        uploaded_file = st.file_uploader("Tải lên tệp PDF:", type=["pdf"])
    with col2:
        use_gpu = st.checkbox("Sử dụng GPU (nếu có)", value=False)

    if uploaded_file is not None:
        st.info(f"Đã chọn: **{uploaded_file.name}** ({round(uploaded_file.size / 1024, 2)} KB)")

        if st.button("🚀 Bắt đầu chuyển đổi", type="primary"):
            progress_bar = st.progress(0)
            status_text = st.empty()

            def update_progress(current, total):
                progress_bar.progress(current / total)
                status_text.text(f"Đang phân tích và OCR trang {current}/{total}...")

            try:
                pdf_bytes = uploaded_file.read()
                docx_path = process_pdf_to_docx(
                    pdf_bytes=pdf_bytes, 
                    use_gpu=use_gpu, 
                    progress_callback=update_progress
                )
                
                status_text.success("✅ Hoàn tất chuyển đổi!")

                with open(docx_path, "rb") as f:
                    docx_data = f.read()

                output_filename = os.path.splitext(uploaded_file.name)[0] + "_converted.docx"
                st.download_button(
                    label="📥 Tải xuống tệp Word (.docx)",
                    data=docx_data,
                    file_name=output_filename,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )
                
                # Xóa tệp tạm sau khi đọc xong
                os.remove(docx_path)

            except Exception as e:
                st.error(f"Đã xảy ra lỗi trong quá trình xử lý: {str(e)}")