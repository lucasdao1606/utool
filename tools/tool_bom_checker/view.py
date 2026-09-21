import streamlit as st
import pandas as pd
import os
from tools.tool_bom_checker.engine import (
    process_bom_data, 
    generate_styled_excel, 
    generate_sample_bom_template
)

def get_secret_safely(section: str, key: str, fallback_flat_key: str = "") -> str:
    """Hàm trích xuất API key an toàn tuyệt đối từ Streamlit secrets hoặc biến môi trường"""
    try:
        # Cách 1: Theo nhóm [section] -> key
        if section in st.secrets and key in st.secrets[section]:
            val = str(st.secrets[section][key]).strip()
            if val:
                return val
    except Exception:
        pass

    try:
        # Cách 2: Theo key dạng phẳng ví dụ: mouser_api_key
        if fallback_flat_key and fallback_flat_key in st.secrets:
            val = str(st.secrets[fallback_flat_key]).strip()
            if val:
                return val
    except Exception:
        pass

    # Cách 3: Lấy từ Environment Variable
    env_val = os.environ.get(f"{section.upper()}_{key.upper()}", "") or os.environ.get(fallback_flat_key.upper(), "")
    return env_val.strip()

def render_bom_checker_tool():
    st.subheader("⚡ Thẩm Định & Quét Nguồn Hàng BOM Linh Kiện (R&D & Mua Hàng)")
    st.caption("Tự động tra cứu tồn kho, đơn giá tối ưu, đề xuất mã thay thế R&D và xuất báo cáo chuẩn hóa.")

    # 1. TỰ ĐỘNG NẠP API KEYS NGẦM AN TOÀN
    mouser_k = get_secret_safely("mouser", "api_key", "mouser_api_key")
    digikey_id = get_secret_safely("digikey", "client_id", "digikey_client_id")
    digikey_sec = get_secret_safely("digikey", "client_secret", "digikey_client_secret")
    oem_k = get_secret_safely("oemsecrets", "api_key", "oemsecrets_api_key")
    nexar_id = get_secret_safely("nexar", "client_id", "nexar_client_id")
    nexar_sec = get_secret_safely("nexar", "client_secret", "nexar_client_secret")

    config = {
        "mouser_key": mouser_k,
        "digikey_id": digikey_id,
        "digikey_secret": digikey_sec,
        "oemsecrets_key": oem_k,
        "nexar_id": nexar_id,
        "nexar_secret": nexar_sec
    }

    # 2. KHU VỰC TẢI FILE & TEMPLATE
    c_left, c_right = st.columns([3, 1.2])
    with c_left:
        st.markdown("**1. Tải lên file BOM cần kiểm tra:**")
    with c_right:
        template_bytes = generate_sample_bom_template()
        st.download_button(
            label="📥 Tải BOM Template mẫu",
            data=template_bytes,
            file_name="BOM_Template_Chuan_San_Xuat.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    uploaded_file = st.file_uploader("Chọn file BOM (.xlsx, .xls, .csv)", type=["xlsx", "xls", "csv"], label_visibility="collapsed")

    if uploaded_file:
        try:
            if uploaded_file.name.endswith(".csv"):
                df_input = pd.read_csv(uploaded_file)
            else:
                df_input = pd.read_excel(uploaded_file)
        except Exception as e:
            st.error(f"Không thể đọc file: {e}")
            return

        with st.expander("📋 Xem trước 5 dòng đầu của file tải lên", expanded=False):
            st.dataframe(df_input.head(5), use_container_width=True)

        columns = list(df_input.columns)
        default_mpn = next((i for i, c in enumerate(columns) if any(k in c.lower() for k in ["mpn", "mã", "part"])), 0)
        default_qty = next((i for i, c in enumerate(columns) if any(k in c.lower() for k in ["qty", "sl", "lượng", "quantity"])), min(1, len(columns)-1))
        default_des = next((i for i, c in enumerate(columns) if any(k in c.lower() for k in ["designator", "vị trí", "ref"])), None)

        col_mpn, col_qty, col_des, col_btn = st.columns([2, 1.5, 1.5, 2])
        mpn_col = col_mpn.selectbox("Cột Mã MPN:", options=columns, index=default_mpn)
        qty_col = col_qty.selectbox("Cột Số Lượng:", options=columns, index=default_qty)
        des_col = col_des.selectbox("Cột Vị trí (Designator):", options=["Không có"] + columns, index=(default_des + 1) if default_des is not None else 0)

        des_key = None if des_col == "Không có" else des_col

        if col_btn.button("🚀 Bắt đầu thẩm định BOM", type="primary", use_container_width=True):
            if not config.get("mouser_key") and not config.get("digikey_id"):
                st.error("❌ Không tìm thấy API Key nào trong file `.streamlit/secrets.toml`. Vui lòng kiểm tra lại file cấu hình.")
                return

            prog_bar = st.progress(0.0)
            status_txt = st.empty()
            debug_logs = []

            # In xác nhận dạng che dấu để kiểm tra nạp key thành công
            m_key = config.get("mouser_key", "")
            if m_key:
                debug_logs.append(f"🔐 Đã nạp Mouser API Key ngầm: {m_key[:4]}...{m_key[-4:]} (độ dài: {len(m_key)} ký tự)")
            else:
                debug_logs.append("⚠️ Không đọc được Mouser API Key từ secrets.")

            try:
                with st.spinner("Đang kết nối kho dữ liệu toàn cầu & phân tích linh kiện tương đương..."):
                    results = process_bom_data(
                        df=df_input,
                        mpn_col=mpn_col,
                        qty_col=qty_col,
                        des_col=des_key,
                        config=config,
                        progress_bar=prog_bar,
                        status_text=status_txt,
                        debug_logs=debug_logs
                    )
                prog_bar.empty()
                status_txt.success(f"✅ Đã thẩm định xong {len(results)} linh kiện!")
                st.session_state["bom_check_results"] = results
            except Exception as ex:
                prog_bar.empty()
                status_txt.error(f"❌ Xảy ra lỗi trong quá trình thực thi: {ex}")
            finally:
                st.session_state["bom_debug_logs"] = debug_logs

    # 3. HIỂN THỊ BÁO CÁO & EXPORT
    if "bom_check_results" in st.session_state and st.session_state["bom_check_results"]:
        results = st.session_state["bom_check_results"]
        df_result = pd.DataFrame(results)

        st.divider()
        st.markdown("### 📊 Kết Quả Thẩm Định BOM Linh Kiện")

        kpi_total = len(df_result)
        kpi_ready = len(df_result[df_result["Trạng Thái Cung Ứng"].str.contains("Sẵn hàng")])
        kpi_partial = len(df_result[df_result["Trạng Thái Cung Ứng"].str.contains("Thiếu hàng")])
        kpi_out = len(df_result[df_result["Trạng Thái Cung Ứng"].str.contains("Hết hàng")])

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Tổng số linh kiện", kpi_total)
        c2.metric("🟢 Đủ hàng sẵn kho", kpi_ready)
        c3.metric("🟡 Thiếu hàng một phần", kpi_partial)
        c4.metric("🔴 Hết hàng", kpi_out)

        st.dataframe(df_result, use_container_width=True, height=480)

        excel_bytes = generate_styled_excel(results)
        st.download_button(
            label="📥 Tải Xuống Báo Cáo BOM Master Hoàn Chỉnh (Excel)",
            data=excel_bytes,
            file_name=f"BOM_Master_Report_{uploaded_file.name if uploaded_file else 'data'}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True
        )

    # Hiển thị Debug Logs nếu cần kiểm tra
    if "bom_debug_logs" in st.session_state and st.session_state["bom_debug_logs"]:
        has_issue = ("bom_check_results" in st.session_state and kpi_ready == 0 and kpi_partial == 0)
        with st.expander("🛠️ Xem nhật ký phản hồi API (Debug Logs)", expanded=has_issue):
            st.code("\n".join(st.session_state["bom_debug_logs"]), language="text")