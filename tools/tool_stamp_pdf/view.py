import streamlit as st
from tools.tool_stamp_pdf.engine import apply_stamp_to_pdf


def render():
    st.subheader("Trình đóng dấu giáp lai PDF tự động")
    st.caption("Cắt dấu tròn/vuông thành từng phần và đóng đều dọc theo mép các trang PDF.")

    col1, col2 = st.columns(2)
    with col1:
        uploaded_pdf = st.file_uploader("1. Chọn file PDF cần đóng dấu", type=["pdf"])
    with col2:
        uploaded_stamp = st.file_uploader(
            "2. Chọn file ảnh con dấu (Khuyên dùng PNG trong suốt)",
            type=["png", "jpg", "jpeg"],
        )

    if uploaded_stamp:
        with st.expander("Xem trước ảnh con dấu"):
            st.image(uploaded_stamp, width=150)

    st.markdown("---")
    st.markdown("**Cấu hình thông số con dấu**")

    c1, c2, c3 = st.columns(3)
    with c1:
        scale_factor = st.slider("Tỷ lệ kích thước (Scale)", 0.5, 2.5, 1.0, 0.1)
    with c2:
        base_mm = st.number_input("Chiều cao chuẩn của dấu (mm)", value=14.0, step=1.0)
    with c3:
        side = st.selectbox("Mép đóng dấu", ["Phải", "Trái"])

    if uploaded_pdf and uploaded_stamp:
        if st.button("Tiến hành đóng dấu giáp lai", type="primary", use_container_width=True):
            with st.spinner("Đang tính toán toạ độ và đóng dấu lên từng trang..."):
                try:
                    pdf_bytes = uploaded_pdf.read()
                    stamp_bytes = uploaded_stamp.read()

                    stamped_pdf_bytes = apply_stamp_to_pdf(
                        pdf_bytes=pdf_bytes,
                        stamp_bytes=stamp_bytes,
                        scale_factor=scale_factor,
                        base_mm=base_mm,
                        side=side,
                    )

                    st.success("Đóng dấu giáp lai hoàn tất!")

                    output_filename = f"{uploaded_pdf.name.rsplit('.', 1)[0]}_giaplaitool.pdf"
                    st.download_button(
                        label="Tải file PDF đã đóng dấu",
                        data=stamped_pdf_bytes,
                        file_name=output_filename,
                        mime="application/pdf",
                        type="secondary",
                        use_container_width=True,
                    )
                except Exception as e:
                    st.error(f"Lỗi trong quá trình xử lý: {str(e)}")
    else:
        st.info("Vui lòng tải lên đầy đủ file PDF và ảnh con dấu để bắt đầu.")