import streamlit as st
import gspread
import pandas as pd
import plotly.express as px
from oauth2client.service_account import ServiceAccountCredentials
import datetime
import os

# --- KẾT NỐI ---
def connect_to_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # 1. Ưu tiên kiểm tra file key.json trước (Dùng cho máy Local)
    if os.path.exists("key.json"):
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
        except Exception as e:
            st.error(f"Lỗi khi đọc file key.json: {e}")
            raise e
    
    # 2. Nếu không có file key.json, mới kiểm tra Streamlit Secrets (Dùng cho Cloud)
    elif "gcp_service_account" in st.secrets:
        try:
            creds_info = dict(st.secrets["gcp_service_account"])
            if "private_key" in creds_info:
                creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
        except Exception as e:
            st.error(f"Lỗi khi đọc Streamlit Secrets: {e}")
            raise e
    
    else:
        st.error("Không tìm thấy cấu hình kết nối! (Thiếu key.json hoặc Streamlit Secrets)")
        st.stop()
        
    client = gspread.authorize(creds)
    return client.open("Quan_Ly_Chi_Tieu_Gia_Dinh").sheet1

# --- POPUP CHO BILL MƯỢN ---
@st.dialog("Nguồn tiền cho mượn")
def lend_dialog(date, amount, note):
    st.write(f"Sếp đang cho mượn **{amount:,.2f} AUD**. Mượn từ đâu vậy sếp?")
    source = st.selectbox("Chọn tài khoản nguồn", ["Tiền mặt", "Ngân hàng"])
    if st.button("Xác nhận cho mượn"):
        try:
            # Kết nối lại để thao tác
            s = connect_to_sheet()
            transfer_note = f"[Bill mượn] {note}" if note else "[Bill mượn]"
            # Tạo 2 dòng transfer giống logic chuyển tiền
            row_out = [str(date), "Chuyển tiền (Ra)", f"{transfer_note} sang Tiền nợ", amount, "Bill", source]
            row_in = [str(date), "Chuyển tiền (Vào)", f"{transfer_note} từ {source}", amount, "Bill", "Tiền nợ"]
            s.append_rows([row_out, row_in])
            st.success("✅ Đã ghi nhận Bill mượn tiền!")
            st.rerun()
        except Exception as e:
            st.error(f"Lỗi: {e}")

st.set_page_config(page_title="Tài chính nhà Bill", layout="centered", page_icon="💰")

# --- CUSTOM CSS CHO MOBILE ---
st.markdown("""
    <style>
    /* Giảm khoảng cách thừa trên mobile */
    .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
        padding-left: 1rem;
        padding-right: 1rem;
    }
    /* Làm đẹp các thẻ Metric */
    [data-testid="stMetricValue"] {
        font-size: 1.8rem !important;
    }
    /* Tối ưu Tab trên màn hình nhỏ */
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
    }
    .stTabs [data-baseweb="tab"] {
        padding-left: 10px;
        padding-right: 10px;
        white-space: nowrap;
    }
    /* Thanh tiến trình bo tròn và đẹp hơn */
    .stProgress > div > div > div > div {
        background-color: #00cc66;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("💰 Tài Chính Nhà Bill")

try:
    sheet = connect_to_sheet()
    
    # Lấy toàn bộ dữ liệu dạng list of lists (an toàn hơn get_all_records khi thiếu header)
    data = sheet.get_all_values()
    
    Expected_Headers = ["Ngày", "Loại", "Ghi chú", "Số tiền", "Người chi", "Tài khoản"]
    
    if not data:
        # Nếu sheet trắng trơn, thêm header luôn
        sheet.append_row(Expected_Headers)
        df = pd.DataFrame(columns=Expected_Headers)
    else:
        headers = data[0]
        # Kiểm tra xem dòng đầu tiên có phải là header chuẩn không
        if headers != Expected_Headers:
            # Nếu dòng đầu ko khớp (ví dụ sheet cũ), coi chừng là data cũ ko có header
            # Tốt nhất là check xem nó có giống tên cột ko. Nếu ko giống thì khả năng là data.
            # Ở đây ta xử lý đơn giản: Nếu data[0] ko phải header chuẩn => Insert header
            # (Logic này có thể cần tinh chỉnh tùy thực tế, nhưng an toàn cho case "mất header")
             if "Ngày" not in headers: # Dấu hiệu nhận biết header
                sheet.insert_row(Expected_Headers, 1)
                data = sheet.get_all_values() # Lấy lại data sau khi sửa
        
        # Tạo DataFrame từ dòng thứ 2 trở đi
        # Xử lý trường hợp các dòng có độ dài không đều (do data cũ thiếu cột Tài khoản)
        # Bằng cách ép chuẩn số lượng cột
        df_data = data[1:] if len(data) > 1 else []
        
        if df_data:
            # Pad các dòng ngắn hơn bằng None
            max_len = len(Expected_Headers)
            normalized_data = []
            for row in df_data:
                # Ép kiểu thành list để tránh lỗi linter và đảm bảo an toàn
                current_row = list(row)
                
                # Nếu dòng thiếu cột (ví dụ thiếu cột Tài khoản), thêm default "Tiền mặt"
                if len(current_row) < max_len:
                    current_row += [""] * (max_len - len(current_row)) # Fill empty string
                    # Nếu cột Tài khoản (index 5) sau khi fill vẫn rỗng (do data cũ), set mặc định
                    if current_row[5] == "": current_row[5] = "Tiền mặt" 
                
                # Cắt bớt nếu thừa
                normalized_data.append(current_row[:max_len])
                
            df = pd.DataFrame(normalized_data, columns=Expected_Headers)
            
            # Convert cột Số tiền sang số (xử lý remove dấu $ hoặc , nếu có)
            # Vì gspread trả về string toàn bộ
            # Hàm clean tiền:
            def clean_money(val):
                if isinstance(val, (int, float)): return float(val)
                if not val: return 0.0
                return float(str(val).replace(",", "").replace("$", ""))
                
            df["Số tiền"] = df["Số tiền"].apply(clean_money)
            
        else:
            df = pd.DataFrame(columns=Expected_Headers)

    # Logic tính toán số dư cho từng tài khoản
    def get_balance(acc_name):
        if df.empty: return 0.0
        # Hỗ trợ cả tên cũ (DoorDash) và tên mới (Thu nhập)
        income_types = ["Thu nhập (DoorDash)", "Thu nhập", "Chuyển tiền (Vào)"]
        inc = df[(df['Tài khoản'] == acc_name) & (df['Loại'].isin(income_types))]['Số tiền'].sum()
        # Các loại còn lại là trừ ra
        exp = df[(df['Tài khoản'] == acc_name) & (~df['Loại'].isin(income_types))]['Số tiền'].sum()
        return inc - exp

    bal_cash = get_balance("Tiền mặt")
    bal_bank = get_balance("Ngân hàng")
    bal_debt = get_balance("Tiền nợ")

    # --- TÍNH TOÁN LỊCH SỬ SỐ DƯ (RUNNING BALANCE) ---
    def calculate_running_balances(input_df):
        if input_df.empty:
            return input_df
            
        # Copy df để tránh side effect
        df_hist = input_df.copy()
        
        # Khởi tạo các cột số dư
        df_hist["Dư TM"] = 0.0
        df_hist["Dư NH"] = 0.0
        df_hist["Dư Nợ"] = 0.0
        
        running_tm = 0.0
        running_nh = 0.0
        running_no = 0.0
        
        # Duyệt theo thứ tự thời gian (từ cũ đến mới) để tính lũy kế
        # Giả định dữ liệu trong Sheet được append theo thứ tự thời gian
        for i, row in df_hist.iterrows():
            amt = row["Số tiền"]
            acc = row["Tài khoản"]
            cat = row["Loại"]
            
            # Logic: Nếu là thu nhập hoặc chuyển vào thì cộng, còn lại trừ
            is_plus = cat in ["Thu nhập", "Thu nhập (DoorDash)", "Chuyển tiền (Vào)"]
            change = amt if is_plus else -amt
            
            if acc == "Tiền mặt": running_tm += change
            elif acc == "Ngân hàng": running_nh += change
            elif acc == "Tiền nợ": running_no += change
            
            # Lưu lại trạng thái ngay sau giao dịch này
            df_hist.at[i, "Dư TM"] = running_tm
            df_hist.at[i, "Dư NH"] = running_nh
            df_hist.at[i, "Dư Nợ"] = running_no
            
        return df_hist

    df_with_balance = calculate_running_balances(df)

    # --- THANH TIẾN TRÌNH TIẾT KIỆM ---
    st.sidebar.header("🎯 Mục tiêu tài chính")
    saving_goal = st.sidebar.number_input("Mục tiêu tiết kiệm ($ AUD)", min_value=1.0, value=10000.0, step=500.0)
    
    # Cập nhật theo ý sếp: Tổng = Tiền mặt + Ngân hàng + Tiền nợ
    current_savings = bal_cash + bal_bank + bal_debt
    
    if saving_goal > 0:
        progress_per = min(max(current_savings / saving_goal, 0.0), 1.0)
    else:
        progress_per = 0.0
        
    # Giao diện Progress Bar gọn gàng cho Mobile
    with st.container():
        st.write(f"🏁 **Tiết kiệm: {progress_per*100:.1f}%** (${current_savings:,.0f}/${saving_goal:,.0f})")
        st.progress(progress_per)
    
    st.divider()

    # --- GIAO DIỆN TABS ---
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Tổng", "🍰 Biểu đồ", "📝 Nhập", "💸 Chuyển", "📜 Lịch sử"])

    with tab1:
        st.subheader("📊 Số dư hiện có")
        # Metric sẽ tự stack dọc trên Mobile
        m1, m2, m3 = st.columns(3)
        m1.metric("💵 Tiền mặt", f"${bal_cash:,.2f}")
        m2.metric("🏦 Ngân hàng", f"${bal_bank:,.2f}")
        m3.metric("📉 Tiền nợ", f"${bal_debt:,.2f}", delta_color="inverse")

    with tab2:
        if not df.empty:
            # Lọc chi tiêu (không lấy thu nhập và không lấy chuyển tiền nội bộ)
            exclude_cats = ["Thu nhập (DoorDash)", "Thu nhập", "Chuyển tiền (Vào)", "Chuyển tiền (Ra)"]
            df_expense = df[~df["Loại"].isin(exclude_cats)]
            if not df_expense.empty:
                st.subheader("🍰 Cơ cấu chi tiêu")
                expense_by_cat = df_expense.groupby("Loại")["Số tiền"].sum().reset_index()
                fig = px.pie(expense_by_cat, values="Số tiền", names="Loại", hole=0.4, 
                             color_discrete_sequence=px.colors.qualitative.Set3)
                # Tối ưu chú thích biểu đồ cho mobile
                fig.update_layout(showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=-0.5))
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Chưa có dữ liệu chi tiêu.")
        else:
            st.info("Chưa có dữ liệu.")

    with tab3:
        with st.form("input_form", clear_on_submit=True):
            st.subheader("📝 Nhập giao dịch")
            # Stack các trường nhập liệu cho mobile
            date = st.date_input("Ngày", datetime.date.today())
            acc = st.selectbox("Tài khoản", ["Tiền mặt", "Ngân hàng"])
            category = st.selectbox("Phân loại", ["Thu nhập", "Ăn uống", "Xăng xe", "Chợ búa", "Vợ tiêu", "Cho Bill mượn", "Khác"])
            amount = st.number_input("Số tiền ($ AUD)", min_value=0.0, step=1.0)
            note = st.text_input("Ghi chú")
            
            submitted = st.form_submit_button("Lưu dữ liệu", use_container_width=True)

        if submitted and amount > 0:
            if category == "Cho Bill mượn":
                lend_dialog(date, amount, note)
            else:
                # Ghi thêm cột Tài khoản vào Google Sheets
                sheet.append_row([str(date), category, note, amount, "Bill", acc])
                st.success("✅ Đã lưu thành công!")
                st.rerun()

    with tab4:
        st.subheader("💸 Chuyển khoản nội bộ")
        with st.form("transfer_form", clear_on_submit=True):
            t_date = st.date_input("Ngày chuyển", datetime.date.today())
            from_acc = st.selectbox("Từ tài khoản", ["Tiền mặt", "Ngân hàng"])
            to_acc = st.selectbox("Đến tài khoản", ["Tiền mặt", "Ngân hàng"])
            t_amount = st.number_input("Số tiền chuyển ($ AUD)", min_value=0.0, step=1.0)
            t_note = st.text_input("Ghi chú chuyển tiền")
                
            t_submitted = st.form_submit_button("Xác nhận chuyển", use_container_width=True)
            
        if t_submitted and t_amount > 0:
            if from_acc == to_acc:
                st.warning("Tài khoản nguồn và đích phải khác nhau!")
            else:
                try:
                    transfer_note = f"[Chuyển tiền] {t_note}" if t_note else "[Chuyển tiền]"
                    row_out = [str(t_date), "Chuyển tiền (Ra)", f"{transfer_note} sang {to_acc}", t_amount, "Bill", from_acc]
                    row_in = [str(t_date), "Chuyển tiền (Vào)", f"{transfer_note} từ {from_acc}", t_amount, "Bill", to_acc]
                    sheet.append_rows([row_out, row_in])
                    st.success("✅ Đã chuyển thành công!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Lỗi: {e}")

    with tab5:
        st.subheader("📜 Lịch sử giao dịch")
        if not df_with_balance.empty:
            # Chỉ hiện 30 giao dịch gần nhất để đảm bảo hiệu năng
            recent_df = df_with_balance.iloc[::-1].head(30)
            
            # Header giả cho bảng
            h1, h2, h3, h4 = st.columns([2, 2, 2, 1])
            h1.caption("**Ngày/Tài khoản**")
            h2.caption("**Loại/Số tiền**")
            h3.caption("**Số dư sau đó**")
            h4.caption("**Xóa**")
            
            st.divider()

            for idx, row in recent_df.iterrows():
                # Tính row index chuẩn trong Google Sheet (1-indexed, +1 cho header)
                sheet_row_idx = int(idx) + 2
                
                c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
                
                # Cột 1: Ngày & Tài khoản
                c1.write(f"{row['Ngày']}")
                c1.caption(f"{row['Tài khoản']}")
                
                # Cột 2: Loại & Số tiền
                color = "green" if row['Loại'] in ["Thu nhập", "Chuyển tiền (Vào)"] else "red"
                c2.write(f"{row['Loại']}")
                c2.markdown(f"<span style='color:{color}; font-weight:bold;'>${row['Số tiền']:,.0f}</span>", unsafe_allow_html=True)
                
                # Cột 3: Số dư (hiện TM và NH cho gọn)
                c3.caption(f"TM: {row['Dư TM']:,.0f}")
                c3.caption(f"NH: {row['Dư NH']:,.0f}")
                c3.caption(f"Nợ: {row['Dư Nợ']:,.0f}")
                
                # Cột 4: Nút xóa
                if c4.button("❌", key=f"del_{sheet_row_idx}"):
                    try:
                        sheet.delete_rows(sheet_row_idx)
                        st.success(f"Đã xóa dòng {sheet_row_idx}!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Lỗi khi xóa: {e}")
                
                st.write("---")
        else:
            st.info("Chưa có lịch sử giao dịch.")

except Exception as e:
    st.error(f"⚠️ Có lỗi xảy ra: {e}")
