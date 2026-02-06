import streamlit as st
import gspread
import pandas as pd
import plotly.express as px
from oauth2client.service_account import ServiceAccountCredentials
import datetime

# --- KẾT NỐI ---
def connect_to_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # Kiểm tra xem đang chạy trên Cloud hay Local
    if "gcp_service_account" in st.secrets:
        # Chạy trên Cloud: Lấy chìa khóa từ Secrets
        creds_info = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(creds_info), scope)
    else:
        # Chạy ở máy sếp: Lấy từ file key.json
        creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
        
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

st.set_page_config(page_title="Tài chính nhà Bill", layout="wide")
st.title("💰 Quản Lý Tài Chính & Số Dư")

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
        # Danh sách các loại cộng vào số dư
        income_types = ["Thu nhập (DoorDash)", "Chuyển tiền (Vào)"]
        inc = df[(df['Tài khoản'] == acc_name) & (df['Loại'].isin(income_types))]['Số tiền'].sum()
        # Các loại còn lại là trừ ra
        exp = df[(df['Tài khoản'] == acc_name) & (~df['Loại'].isin(income_types))]['Số tiền'].sum()
        return inc - exp

    bal_cash = get_balance("Tiền mặt")
    bal_bank = get_balance("Ngân hàng")
    bal_debt = get_balance("Tiền nợ")

    # --- GIAO DIỆN TABS ---
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Tổng kết tài chính", "🍰 Tỉ lệ chi tiêu", "📝 Thêm giao dịch mới", "💸 Chuyển tiền nội bộ"])

    with tab1:
        st.subheader("📊 Tổng kết tài chính")
        m1, m2, m3 = st.columns(3)
        m1.metric("💵 Tiền mặt", f"${bal_cash:,.2f} AUD")
        m2.metric("🏦 Ngân hàng", f"${bal_bank:,.2f} AUD")
        m3.metric("📉 Tiền nợ", f"${bal_debt:,.2f} AUD", delta_color="inverse")

    with tab2:
        if not df.empty:
            # Lọc chi tiêu (không lấy thu nhập và không lấy chuyển tiền nội bộ để báo cáo chuẩn)
            exclude_cats = ["Thu nhập (DoorDash)", "Chuyển tiền (Vào)", "Chuyển tiền (Ra)"]
            df_expense = df[~df["Loại"].isin(exclude_cats)]
            if not df_expense.empty:
                st.subheader("🍰 Tỷ lệ chi tiêu")
                # Group by category
                expense_by_cat = df_expense.groupby("Loại")["Số tiền"].sum().reset_index()
                fig = px.pie(expense_by_cat, values="Số tiền", names="Loại", hole=0.4, 
                             color_discrete_sequence=px.colors.qualitative.Set3)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Chưa có dữ liệu chi tiêu để hiển thị biểu đồ.")
        else:
            st.info("Chưa có dữ liệu.")

    with tab3:
        with st.form("input_form", clear_on_submit=True):
            st.subheader("📝 Thêm giao dịch mới")
            c1, c2, c3 = st.columns(3)
            with c1:
                date = st.date_input("Ngày", datetime.date.today())
                acc = st.selectbox("📥 Tài khoản sử dụng", ["Tiền mặt", "Ngân hàng", "Tiền nợ"])
            with c2:
                category = st.selectbox("📂 Phân loại", ["Thu nhập (DoorDash)", "Ăn uống", "Xăng xe", "Chợ búa", "Vợ tiêu", "Cho Bill mượn", "Khác"])
                amount = st.number_input("Số tiền ($ AUD)", min_value=0.0)
            with c3:
                note = st.text_input("Ghi chú")
            
            submitted = st.form_submit_button("Cập nhật số dư Cloud")

        if submitted and amount > 0:
            if category == "Cho Bill mượn":
                lend_dialog(date, amount, note)
            else:
                # Ghi thêm cột Tài khoản vào Google Sheets
                sheet.append_row([str(date), category, note, amount, "Bill", acc])
                st.success("✅ Đã cập nhật số dư thành công!")
                st.rerun() # Tải lại trang để cập nhật con số ở trên

    with tab4:
        st.subheader("💸 Chuyển tiền giữa các tài khoản")
        with st.form("transfer_form", clear_on_submit=True):
            col_t1, col_t2, col_t3 = st.columns(3)
            with col_t1:
                t_date = st.date_input("Ngày chuyển", datetime.date.today())
                from_acc = st.selectbox("Từ tài khoản", ["Tiền mặt", "Ngân hàng", "Tiền nợ"])
            with col_t2:
                to_acc = st.selectbox("Đến tài khoản", ["Tiền mặt", "Ngân hàng", "Tiền nợ"])
                t_amount = st.number_input("Số tiền chuyển ($ AUD)", min_value=0.0)
            with col_t3:
                t_note = st.text_input("Ghi chú chuyển tiền", placeholder="Ví dụ: Rút tiền ATM...")
                
            t_submitted = st.form_submit_button("Xác nhận chuyển tiền")
            
        if t_submitted and t_amount > 0:
            if from_acc == to_acc:
                st.warning("Tài khoản nguồn và đích phải khác nhau chứ sếp!")
            else:
                try:
                    # Tạo 2 dòng dữ liệu: Một dòng trừ tiền (Ra), một dòng cộng tiền (Vào)
                    transfer_note = f"[Chuyển tiền] {t_note}" if t_note else "[Chuyển tiền]"
                    
                    # Dòng 1: Tài khoản nguồn (Ra)
                    row_out = [str(t_date), "Chuyển tiền (Ra)", f"{transfer_note} sang {to_acc}", t_amount, "Bill", from_acc]
                    # Dòng 2: Tài khoản đích (Vào)
                    row_in = [str(t_date), "Chuyển tiền (Vào)", f"{transfer_note} từ {from_acc}", t_amount, "Bill", to_acc]
                    
                    sheet.append_rows([row_out, row_in])
                    st.success(f"✅ Đã chuyển {t_amount} AUD từ {from_acc} sang {to_acc}!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Lỗi khi chuyển tiền: {e}")

except Exception as e:
    st.error(f"⚠️ Có lỗi xảy ra: {e}")
