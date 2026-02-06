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

# --- POPUP SỬA GIAO DỊCH ---
@st.dialog("Sửa giao dịch")
def edit_dialog(row_data, sheet_row_idx, is_transfer=False, sibling_row_idx=None, sibling_data=None):
    st.write(f"Sếp đang sửa giao dịch tại dòng **{sheet_row_idx}**" + (f" & **{sibling_row_idx}**" if is_transfer else ""))
    
    try:
        current_date = datetime.datetime.strptime(row_data["Ngày"], "%Y-%m-%d").date()
    except:
        current_date = datetime.date.today()
        
    with st.form("edit_form"):
        new_date = st.date_input("Ngày", current_date)
        
        if not is_transfer:
            new_acc = st.selectbox("Tài khoản", ["Tiền mặt", "Ngân hàng"], index=["Tiền mặt", "Ngân hàng"].index(row_data["Tài khoản"]) if row_data["Tài khoản"] in ["Tiền mặt", "Ngân hàng"] else 0)
            cats = ["Thu nhập", "Ăn uống", "Xăng xe", "Chợ búa", "Vợ tiêu", "Cho Bill mượn", "Khác"]
            new_cat = st.selectbox("Phân loại", cats, index=cats.index(row_data["Loại"]) if row_data["Loại"] in cats else 6)
        else:
            st.info(f"Đang sửa cặp chuyển khoản: **{sibling_data['Tài khoản']} → {row_data['Tài khoản']}**")
            new_acc = row_data["Tài khoản"]
            new_cat = row_data["Loại"]
            
        new_amount = st.number_input("Số tiền ($ AUD)", min_value=0.0, value=float(row_data["Số tiền"]), step=1.0)
        # Nếu là chuyển khoản, cho phép sửa ghi chú gốc (bỏ phần đuôi tự động)
        clean_note = row_data["Ghi chú"].split(" từ ")[0] if is_transfer and " từ " in row_data["Ghi chú"] else row_data["Ghi chú"]
        new_note = st.text_input("Ghi chú", value=clean_note)
        
        if st.form_submit_button("Lưu thay đổi", use_container_width=True):
            try:
                s = connect_to_sheet()
                updates = []
                
                if not is_transfer:
                    # Giao dịch đơn
                    new_row = [str(new_date), new_cat, new_note, new_amount, "Bill", new_acc]
                    s.update(f"A{sheet_row_idx}:F{sheet_row_idx}", [new_row])
                else:
                    # Giao dịch đôi (Chuyển khoản)
                    # Giữ nguyên logic ghi chú tự động cho chuyển khoản
                    note_out = f"{new_note} sang {row_data['Tài khoản']}" if new_note else f"Chuyển sang {row_data['Tài khoản']}"
                    note_in = f"{new_note} từ {sibling_data['Tài khoản']}" if new_note else f"Nhận từ {sibling_data['Tài khoản']}"
                    
                    row_out = [str(new_date), sibling_data["Loại"], note_out, new_amount, "Bill", sibling_data["Tài khoản"]]
                    row_in = [str(new_date), row_data["Loại"], note_in, new_amount, "Bill", row_data["Tài khoản"]]
                    
                    # Update cả 2 dòng
                    s.update(f"A{sibling_row_idx}:F{sibling_row_idx}", [row_out])
                    s.update(f"A{sheet_row_idx}:F{sheet_row_idx}", [row_in])
                    
                st.success("✅ Đã cập nhật thành công!")
                st.rerun()
            except Exception as e:
                st.error(f"Lỗi khi cập nhật: {e}")

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
        st.write(f"🏁 **Tiết kiệm: {progress_per*100:.1f}%** (\${current_savings:,.2f} / \${saving_goal:,.2f})")
        st.progress(progress_per)
    
    st.divider()

    # --- GIAO DIỆN TABS ---
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Tổng", "🍰 Biểu đồ", "📝 Nhập", "💸 Chuyển", "📜 Lịch sử"])

    with tab1:
        st.subheader(f"📊 Số dư hiện có: \${current_savings:,.2f}")
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
            # Chỉ hiện 30 giao dịch gần nhất
            recent_df = df_with_balance.iloc[::-1].head(35) # Tăng lên chút vì sẽ gộp dòng
            
            # Header giả cho bảng
            h1, h2, h3, h4, h5 = st.columns([2, 2, 2, 0.6, 0.6])
            h1.caption("**Ngày/TK**")
            h2.caption("**Loại/$**")
            h3.caption("**Số dư**")
            h4.caption("**Sửa**")
            h5.caption("**Xóa**")
            
            st.divider()

            skip_next = False
            for i in range(len(recent_df)):
                if skip_next:
                    skip_next = False
                    continue
                
                row = recent_df.iloc[i]
                idx = recent_df.index[i]
                sheet_row_idx = int(idx) + 2
                
                # Logic Gộp: Nếu dòng hiện tại là "Chuyển tiền (Vào)" và dòng tiếp theo là "Chuyển tiền (Ra)" (vì đã đảo ngược iloc[::-1])
                # Thực tế: Trong Sheet, Ra (index n) thường ở trước Vào (index n+1). 
                # Khi đảo ngược: n+1 (Vào) sẽ ở trên n (Ra).
                is_merged = False
                display_cat = row['Loại']
                display_acc = row['Tài khoản']
                display_note = row['Ghi chú']
                delete_indices = [sheet_row_idx]
                
                if i + 1 < len(recent_df):
                    next_row = recent_df.iloc[i+1]
                    # Nếu dòng hiện tại là Vào và dòng sau là Ra, và cùng số tiền, cùng ghi chú cơ bản
                    if row['Loại'] == "Chuyển tiền (Vào)" and next_row['Loại'] == "Chuyển tiền (Ra)" and abs(row['Số tiền'] - next_row['Số tiền']) < 0.01:
                        is_merged = True
                        skip_next = True
                        display_cat = "Chuyển tiền"
                        display_acc = f"{next_row['Tài khoản']} ➔ {row['Tài khoản']}"
                        # Làm sạch ghi chú: bỏ phần "từ..." hoặc "sang..." tự động
                        display_note = row['Ghi chú'].split(" từ ")[0] if " từ " in row['Ghi chú'] else row['Ghi chú']
                        delete_indices = [sheet_row_idx, int(recent_df.index[i+1]) + 2]

                c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 0.6, 0.6])
                
                # Cột 1: Ngày & Tài khoản
                c1.write(f"{row['Ngày']}")
                c1.caption(f"{display_acc}")
                
                # Cột 2: Loại & Số tiền
                color = "green" if row['Loại'] in ["Thu nhập", "Thu nhập (DoorDash)", "Chuyển tiền (Vào)"] else "red"
                if is_merged: color = "#3182ce" # Màu xanh dương cho chuyển khoản
                
                c2.write(f"{display_cat}")
                if display_note:
                    c2.caption(f"{display_note}")
                c2.markdown(f"<span style='color:{color}; font-weight:bold;'>${row['Số tiền']:,.2f}</span>", unsafe_allow_html=True)
                
                # Cột 3: Số dư (Lấy từ dòng "Vào" - dòng mới nhất trong cặp)
                c3.caption(f"TM: {row['Dư TM']:,.2f}")
                c3.caption(f"NH: {row['Dư NH']:,.2f}")
                c3.caption(f"Nợ: {row['Dư Nợ']:,.2f}")
                
                # Cột 4: Nút Sửa
                if c4.button("✏️", key=f"edit_{sheet_row_idx}"):
                    if not is_merged:
                        edit_dialog(row, sheet_row_idx)
                    else:
                        sibling_idx = int(recent_df.index[i+1]) + 2
                        edit_dialog(row, sheet_row_idx, is_transfer=True, sibling_row_idx=sibling_idx, sibling_data=recent_df.iloc[i+1])

                # Cột 5: Nút xóa
                if c5.button("❌", key=f"del_{sheet_row_idx}"):
                    try:
                        # Xóa từ dòng lớn đến dòng nhỏ để không bị lệch index
                        for d_idx in sorted(delete_indices, reverse=True):
                            sheet.delete_rows(d_idx)
                        st.success(f"Đã xóa thành công!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Lỗi khi xóa: {e}")
                
                st.write("---")
        else:
            st.info("Chưa có lịch sử giao dịch.")

except Exception as e:
    st.error(f"⚠️ Có lỗi xảy ra: {e}")
