from datetime import date, datetime
import pandas as pd
import psycopg2
import streamlit as st

# --- USER ACCOUNTS & ROLES CONFIGURATION ---
USERS = {
    "admin": {
        "password": "adminpassword123",
        "role": "Administrator",
        "name": "Head Admin",
    },
    "manager": {
        "password": "managerpassword123",
        "role": "Management Viewer",
        "name": "Manager",
    },
    "cashier1": {
        "password": "cashierpassword123",
        "role": "Cashier / Sales",
        "name": "Store Cashier",
    },
    "inventory1": {
        "password": "invpassword123",
        "role": "Inventory Custodian",
        "name": "Stock Clerk",
    },
    "delivery1": {
        "password": "delpassword123",
        "role": "Delivery Custodian",
        "name": "Receiving Staff",
    },
}

# --- SUPABASE POSTGRES CONNECTION SETUP ---


def get_connection():
    db_url = st.secrets["postgres"]["url"]
    if "sslmode" not in db_url:
        separator = "&" if "?" in db_url else "?"
        db_url += f"{separator}sslmode=require"
    conn = psycopg2.connect(db_url)
    return conn


def init_db():
    conn = get_connection()
    c = conn.cursor()

    # Medicines Table
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS medicines (
            id SERIAL PRIMARY KEY,
            brand_name VARCHAR(255) NOT NULL,
            generic_name VARCHAR(255) NOT NULL,
            category VARCHAR(100),
            unit_price NUMERIC(10,2) NOT NULL,
            stock_qty INT NOT NULL,
            min_threshold INT DEFAULT 10,
            expiry_date DATE
        )
    """
    )

    # Sales Table
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS sales (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            medicine_id INT,
            medicine_name VARCHAR(255),
            qty_sold INT,
            unit_price NUMERIC(10,2),
            total_price NUMERIC(10,2),
            FOREIGN KEY (medicine_id) REFERENCES medicines(id)
        )
    """
    )

    # Deliveries Table
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS deliveries (
            id SERIAL PRIMARY KEY,
            delivery_date DATE,
            dr_number VARCHAR(100),
            supplier VARCHAR(255),
            medicine_id INT,
            qty_received INT,
            FOREIGN KEY (medicine_id) REFERENCES medicines(id)
        )
    """
    )

    conn.commit()
    c.close()
    conn.close()


init_db()

# --- APP LAYOUT & CONFIG ---
st.set_page_config(
    page_title="Pharmacy Inventory & Sales System", layout="wide"
)

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
    st.session_state["username"] = ""
    st.session_state["role"] = ""
    st.session_state["name"] = ""

# --- LOGIN SCREEN ---
if not st.session_state["logged_in"]:
    st.title("🔐 Pharmacy System Login")
    st.markdown("Please sign in with your assigned staff credentials.")

    with st.form("login_form"):
        username_input = st.text_input("Username")
        password_input = st.text_input("Password", type="password")
        submit_login = st.form_submit_button("Login")

        if submit_login:
            if (
                username_input in USERS
                and USERS[username_input]["password"] == password_input
            ):
                st.session_state["logged_in"] = True
                st.session_state["username"] = username_input
                st.session_state["role"] = USERS[username_input]["role"]
                st.session_state["name"] = USERS[username_input]["name"]
                st.success("Login successful! Loading dashboard...")
                st.rerun()
            else:
                st.error("Invalid username or password. Please try again.")

    with st.expander("ℹ️ Default Test Accounts"):
        st.markdown(
            """
        * **Administrator:** `admin` / `adminpassword123`
        * **Management Viewer:** `manager` / `managerpassword123`
        * **Cashier:** `cashier1` / `cashierpassword123`
        * **Inventory Custodian:** `inventory1` / `invpassword123`
        * **Delivery Custodian:** `delivery1` / `delpassword123`
        """
        )

else:
    st.title(
        "💊 Pharmacy Inventory & Sales System (Cloud-Backed via Supabase)"
    )

    st.sidebar.markdown(f"👤 **Logged in as:** {st.session_state['name']}")
    st.sidebar.markdown(f"🛡️ **Role:** `{st.session_state['role']}`")

    if st.sidebar.button("Logout"):
        st.session_state["logged_in"] = False
        st.session_state["username"] = ""
        st.session_state["role"] = ""
        st.session_state["name"] = ""
        st.rerun()

    st.sidebar.divider()

    role = st.session_state["role"]

    if role == "Administrator":
        menu = [
            "Dashboard",
            "Inventory Management",
            "POS / Record Sale",
            "Deliveries",
            "Sales History",
        ]
    elif role == "Management Viewer":
        menu = ["Dashboard", "Sales History"]
    elif role == "Cashier / Sales":
        menu = ["POS / Record Sale", "Sales History"]
    elif role == "Inventory Custodian":
        menu = ["Dashboard", "Inventory Management"]
    elif role == "Delivery Custodian":
        menu = ["Deliveries"]
    else:
        menu = []

    choice = st.sidebar.selectbox("Navigation Menu", menu)

    # --- 1. DASHBOARD ---
    if choice == "Dashboard":
        st.header("📊 Overview & Alerts")

        conn = get_connection()
        low_stock_df = pd.read_sql(
            "SELECT brand_name, generic_name, stock_qty, min_threshold FROM medicines WHERE stock_qty <= min_threshold",
            conn,
        )
        expiring_df = pd.read_sql(
            "SELECT brand_name, generic_name, stock_qty, expiry_date FROM medicines WHERE expiry_date <= CURRENT_DATE + INTERVAL '60 days' AND expiry_date >= CURRENT_DATE",
            conn,
        )
        total_products = pd.read_sql(
            "SELECT COUNT(*) as count FROM medicines", conn
        ).iloc[0]["count"]
        today_sales = pd.read_sql(
            "SELECT SUM(total_price) as total FROM sales WHERE DATE(timestamp) = CURRENT_DATE",
            conn,
        ).iloc[0]["total"]
        today_sales = today_sales if today_sales else 0.0
        conn.close()

        m1, m2, m3 = st.columns(3)
        m1.metric("Total Unique Items", total_products)
        m2.metric("Today's Sales", f"₱{today_sales:,.2f}")
        m3.metric("Low Stock Items", len(low_stock_df))

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("⚠️ Low Stock Warning")
            if not low_stock_df.empty:
                st.dataframe(low_stock_df, use_container_width=True)
            else:
                st.success("All items are above minimum stock levels.")

        with col2:
            st.subheader("⏳ Expiring Soon (Next 60 Days)")
            if not expiring_df.empty:
                st.dataframe(expiring_df, use_container_width=True)
            else:
                st.info("No items expiring within the next 60 days.")

    # --- 2. INVENTORY MANAGEMENT ---
    elif choice == "Inventory Management":
        st.header("📦 Inventory Stock")
        tab1, tab2 = st.tabs(["View / Search Inventory", "Add New Medicine"])

        with tab1:
            conn = get_connection()
            inventory_df = pd.read_sql("SELECT * FROM medicines", conn)
            conn.close()

            search = st.text_input(
                "🔍 Search Medicine (Brand, Generic, or Category)"
            )
            if search:
                inventory_df = inventory_df[
                    inventory_df["brand_name"].str.contains(search, case=False)
                    | inventory_df["generic_name"].str.contains(
                        search, case=False
                    )
                    | inventory_df["category"].str.contains(search, case=False)
                ]
            st.dataframe(inventory_df, use_container_width=True)

        with tab2:
            st.subheader("Add New Medicine Record")
            with st.form("add_medicine_form"):
                col1, col2 = st.columns(2)
                brand_name = col1.text_input("Brand Name")
                generic_name = col2.text_input("Generic Name")

                cat_col, price_col, qty_col = st.columns(3)
                category = cat_col.text_input(
                    "Category (e.g., Antibiotic, Analgesic)"
                )
                unit_price = price_col.number_input(
                    "Unit Price (₱)", min_value=0.0, step=0.5
                )
                initial_stock = qty_col.number_input(
                    "Initial Stock", min_value=0, step=1
                )

                thresh_col, exp_col = st.columns(2)
                min_thresh = thresh_col.number_input(
                    "Low Stock Alert Threshold", min_value=1, value=10
                )
                expiry = exp_col.date_input("Expiry Date", value=date.today())

                submitted = st.form_submit_button("Add Item")

                if submitted:
                    if brand_name and generic_name:
                        conn = get_connection()
                        c = conn.cursor()
                        c.execute(
                            """
                            INSERT INTO medicines (brand_name, generic_name, category, unit_price, stock_qty, min_threshold, expiry_date)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                            (
                                brand_name,
                                generic_name,
                                category,
                                unit_price,
                                initial_stock,
                                min_thresh,
                                expiry,
                            ),
                        )
                        conn.commit()
                        c.close()
                        conn.close()
                        st.success(f"Added '{brand_name}' to inventory.")
                        st.rerun()
                    else:
                        st.error(
                            "Please fill in both Brand Name and Generic Name."
                        )

    # --- 3. POINT OF SALE ---
    elif choice == "POS / Record Sale":
        st.header("🛒 Point of Sale / Record Sale")

        conn = get_connection()
        medicines = pd.read_sql(
            "SELECT id, brand_name, generic_name, unit_price, stock_qty FROM medicines WHERE stock_qty > 0",
            conn,
        )
        conn.close()

        if medicines.empty:
            st.warning(
                "No available stock in inventory. Please add stock or record a delivery first."
            )
        else:
            med_dict = {
                f"{row['brand_name']} ({row['generic_name']}) - Stock: {row['stock_qty']} | Price: ₱{row['unit_price']:.2f}": row
                for _, row in medicines.iterrows()
            }

            selected_item_label = st.selectbox(
                "Select Medicine", list(med_dict.keys())
            )
            selected_item = med_dict[selected_item_label]

            col1, col2 = st.columns(2)
            qty = col1.number_input(
                "Quantity to Sell",
                min_value=1,
                max_value=int(selected_item["stock_qty"]),
                value=1,
            )
            total = qty * selected_item["unit_price"]
            col2.metric("Total Amount Due", f"₱{total:,.2f}")

            if st.button("Complete Transaction"):
                conn = get_connection()
                c = conn.cursor()

                c.execute(
                    """
                    INSERT INTO sales (medicine_id, medicine_name, qty_sold, unit_price, total_price)
                    VALUES (%s, %s, %s, %s, %s)
                """,
                    (
                        int(selected_item["id"]),
                        selected_item["brand_name"],
                        int(qty),
                        float(selected_item["unit_price"]),
                        float(total),
                    ),
                )

                c.execute(
                    """
                    UPDATE medicines 
                    SET stock_qty = stock_qty - %s 
                    WHERE id = %s
                """,
                    (int(qty), int(selected_item["id"])),
                )

                conn.commit()
                c.close()
                conn.close()

                st.success(
                    f"Sold {qty} unit(s) of {selected_item['brand_name']} for ₱{total:,.2f}."
                )
                st.rerun()

    # --- 4. DELIVERIES ---
    elif choice == "Deliveries":
        st.header("🚚 Incoming Deliveries")

        conn = get_connection()
        medicines = pd.read_sql(
            "SELECT id, brand_name, generic_name FROM medicines", conn
        )
        conn.close()

        st.subheader("Log Delivery Shipment")

        if medicines.empty:
            st.info(
                "Please add medicines to your master list in 'Inventory Management' first."
            )
        else:
            med_dict = {
                f"{row['brand_name']} ({row['generic_name']})": row["id"]
                for _, row in medicines.iterrows()
            }

            with st.form("delivery_form"):
                dr_number = st.text_input("Delivery Receipt (DR) No.")
                supplier = st.text_input("Supplier Name")
                del_date = st.date_input("Delivery Date", value=date.today())

                selected_item_label = st.selectbox(
                    "Select Medicine Received", list(med_dict.keys())
                )
                qty_received = st.number_input(
                    "Quantity Received", min_value=1, step=1
                )

                submitted = st.form_submit_button(
                    "Record Delivery & Update Stock"
                )

                if submitted:
                    med_id = med_dict[selected_item_label]
                    conn = get_connection()
                    c = conn.cursor()

                    c.execute(
                        """
                        INSERT INTO deliveries (delivery_date, dr_number, supplier, medicine_id, qty_received)
                        VALUES (%s, %s, %s, %s, %s)
                    """,
                        (
                            del_date,
                            dr_number,
                            supplier,
                            int(med_id),
                            int(qty_received),
                        ),
                    )

                    c.execute(
                        """
                        UPDATE medicines 
                        SET stock_qty = stock_qty + %s 
                        WHERE id = %s
                    """,
                        (int(qty_received), int(med_id)),
                    )

                    conn.commit()
                    c.close()
                    conn.close()

                    st.success(
                        f"Successfully added {qty_received} units to inventory!"
                    )
                    st.rerun()

        st.divider()
        st.subheader("Delivery Log History")
        conn = get_connection()
        deliveries_df = pd.read_sql(
            """
            SELECT d.id, d.delivery_date, d.dr_number, d.supplier, m.brand_name, d.qty_received 
            FROM deliveries d 
            JOIN medicines m ON d.medicine_id = m.id 
            ORDER BY d.delivery_date DESC
        """,
            conn,
        )
        conn.close()
        st.dataframe(deliveries_df, use_container_width=True)

    # --- 5. SALES HISTORY ---
    elif choice == "Sales History":
        st.header("📈 Sales Records & Reports")

        conn = get_connection()
        sales_df = pd.read_sql(
            "SELECT * FROM sales ORDER BY timestamp DESC", conn
        )
        conn.close()

        if not sales_df.empty:
            total_rev = sales_df["total_price"].sum()
            st.metric("Total Recorded Revenue", f"₱{total_rev:,.2f}")
            st.dataframe(sales_df, use_container_width=True)
        else:
            st.info("No sales transactions recorded yet.")
