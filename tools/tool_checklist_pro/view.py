import os
import streamlit as st
from tools.tool_checklist_pro.engine import process_checklist

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "template_checklist.xlsx")

def render_checklist_pro_tool():
    st.subheader("📋 Checklist Pro - Đối soát & Đánh giá Tiêu chí Kỹ thuật")
    st.caption("Tự động đọc thông số, quy đổi đơn vị (khối lượng, độ dài, tần số, điện áp) và chấm điểm PASS/FAIL.")

    # Khu vực tải file mẫu tham khảo
    col_temp1, col_temp2 = st.columns([3, 1])
    with col_temp1:
        st.info("💡 Bạn có thể tải file template chuẩn về để điền thông số hoặc bấm chạy thử trực tiếp.")
    with col_temp2:
        if os.path.exists(TEMPLATE_PATH):
            with open(TEMPLATE_PATH, "rb") as f:
                st.download_button(
                    label="📥 Tải file mẫu (.xlsx)",
                    data=f.read(),
                    file_name="Template_Checklist_KyThuat.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )

    use_sample = st.checkbox("Sử dụng luôn file mẫu có sẵn để chạy thử nghiệm")

    uploaded_file = None
    if not use_sample:
        uploaded_file = st.file_uploader("Chọn file Excel cần đối soát (*.xlsx)", type=["xlsx"])

    with st.expander("⚙️ Cấu hình vị trí cột (Mặc định chuẩn theo file mẫu)"):
        c1, c2 = st.columns(2)
        with c1:
            col_name = st.number_input("Cột Tên chỉ tiêu (Tên yêu cầu)", value=1, min_value=0, step=1)
            col_req = st.number_input("Cột Chỉ tiêu yêu cầu kỹ thuật", value=2, min_value=0, step=1)
        with c2:
            sp1_col = st.number_input("Cột Tham khảo 1 (SP1)", value=4, min_value=0, step=1)
            sp2_col = st.number_input("Cột Tham khảo 2 (SP2)", value=6, min_value=0, step=1)
            sp3_col = st.number_input("Cột Tham khảo 3 (SP3)", value=8, min_value=0, step=1)

    sp_config = {"Tham khảo 1": sp1_col, "Tham khảo 2": sp2_col, "Tham khảo 3": sp3_col}

    file_bytes = None
    target_name = "Template_Checklist"

    if use_sample and os.path.exists(TEMPLATE_PATH):
        with open(TEMPLATE_PATH, "rb") as f:
            file_bytes = f.read()
    elif uploaded_file is not None:
        file_bytes = uploaded_file.read()
        target_name = uploaded_file.name.rsplit('.', 1)[0]

    if file_bytes is not None:
        if st.button("🚀 Bắt đầu đối soát", type="primary", use_container_width=True):
            with st.spinner("Đang trích xuất chỉ tiêu, quy đổi đơn vị và đối soát..."):
                try:
                    df_res, score_percent, excel_bytes = process_checklist(
                        file_bytes=file_bytes,
                        col_name=col_name,
                        col_req=col_req,
                        sp_cols=sp_config
                    )

                    st.success("✅ Đối soát hoàn tất!")

                    # Hiển thị tỷ lệ đáp ứng
                    st.markdown("### 📊 Tỷ lệ đáp ứng tiêu chuẩn")
                    cols = st.columns(len(score_percent))
                    for idx, (sp, percent) in enumerate(score_percent.items()):
                        with cols[idx]:
                            st.metric(label=f"Độ phù hợp {sp}", value=f"{percent}%")

                    # Bảng dữ liệu chi tiết
                    st.markdown("### 📝 Chi tiết đánh giá từng hạng mục")
                    st.dataframe(df_res, use_container_width=True)

                    # Nút tải file kết quả đã highlight
                    st.download_button(
                        label="📥 Tải file Excel kết quả (đã highlight xanh/đỏ)",
                        data=excel_bytes,
                        file_name=f"{target_name}_checked.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="secondary",
                        use_container_width=True
                    )

                except Exception as e:
                    st.error(f"Lỗi khi xử lý file: {str(e)}")
    else:
        if not use_sample:
            st.info("Vui lòng tải lên file Excel hoặc tích chọn 'Sử dụng luôn file mẫu có sẵn' để bắt đầu.")