from datetime import date, datetime
import pandas as pd
import psycopg2
import streamlit as st

# --- SUPABASE POSTGRES CONNECTION WITH CONNECTION CACHING ---


@st.cache_resource
def get_db_connection():
    """Cache the database connection pool so it stays warm across re-runs."""
    db_url = st.secrets["postgres"]["url"]
    conn = psycopg2.connect(db_url, sslmode="require")
    return conn


def get_connection():
    """Retrieves the cached connection or re-establishes if dropped."""
    try:
        conn = get_db_connection()
        with conn.cursor() as c:
            c.execute("SELECT 1;")
        return conn
    except Exception:
        st.cache_resource.clear()
        return get_db_connection()


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

    # Users Table for Dynamic RBAC
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS app_users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            role VARCHAR(100) NOT NULL,
            name VARCHAR(255) NOT NULL
        )
    """
    )

    # Seed default admin if no users exist
    c.execute("SELECT COUNT(*) FROM app_users")
    count = c.fetchone()[0]
    if count == 0:
        c.execute(
            """
            INSERT INTO app_users (username, password, role, name)
            VALUES (%s, %s, %s, %s)
        """,
            ("admin", "adminpassword123", "Administrator", "Head Admin"),
        )

    conn.commit()
    c.close()


init_db()

# --- APP LAYOUT & CONFIG ---
st.set_page_config(
    page_title="Pharmacy Inventory & Sales System", layout="wide"
)

# --- HIDE STREAMLIT HEADER, TOOLBAR, & FOOTER UI ---
hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            header {visibility: hidden;}
            footer {visibility: hidden;}
            [data-testid="stHeader"] {display: none;}
            [data-testid="stToolbar"] {display: none;}
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

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
            conn = get_connection()
            c = conn.cursor()
            c.execute(
                "SELECT password, role, name FROM app_users WHERE username = %s",
                (username_input,),
            )
            user_record = c.fetchone()
            c.close()

            if user_record and user_record[0] == password_input:
                st.session_state["logged_in"] = True
                st.session_state["username"] = username_input
                st.session_state["role"] = user_record[1]
                st.session_state["name"] = user_record[2]
                st.success("Login successful! Loading dashboard...")
                st.rerun()
            else:
                st.error("Invalid username or password. Please try again.")

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
            "User Management",
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
        tab1, tab2, tab3 = st.tabs(
            [
                "View / Search Inventory",
                "Add New Medicine",
                "Edit / Delete Medicine",
            ]
        )

        with tab1:
            conn = get_connection()
            inventory_df = pd.read_sql("SELECT * FROM medicines", conn)

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
                        st.success(f"Added '{brand_name}' to inventory.")
                        st.rerun()
                    else:
                        st.error(
                            "Please fill in both Brand Name and Generic Name."
                        )

        with tab3:
            st.subheader("Edit or Delete Sample Medicine")
            conn = get_connection()
            meds_df = pd.read_sql("SELECT * FROM medicines", conn)

            if meds_df.empty:
                st.info("No medicines currently in inventory.")
            else:
                med_dict = {
                    f"{row['brand_name']} ({row['generic_name']}) - ID: {row['id']}": row
                    for _, row in meds_df.iterrows()
                }
                selected_med_label = st.selectbox(
                    "Select Medicine to Modify/Delete", list(med_dict.keys())
                )
                selected_med = med_dict[selected_med_label]

                with st.form("edit_medicine_form"):
                    col1, col2 = st.columns(2)
                    e_brand = col1.text_input(
                        "Brand Name", value=selected_med["brand_name"]
                    )
                    e_generic = col2.text_input(
                        "Generic Name", value=selected_med["generic_name"]
                    )

                    cat_col, price_col, qty_col = st.columns(3)
                    e_category = cat_col.text_input(
                        "Category", value=selected_med["category"]
                    )
                    e_price = price_col.number_input(
                        "Unit Price (₱)",
                        min_value=0.0,
                        value=float(selected_med["unit_price"]),
                        step=0.5,
                    )
                    e_qty = qty_col.number_input(
                        "Stock Quantity",
                        min_value=0,
                        value=int(selected_med["stock_qty"]),
                        step=1,
                    )

                    update_med_btn = st.form_submit_button(
                        "Save Changes to Medicine"
                    )

                if update_med_btn:
                    conn = get_connection()
                    c = conn.cursor()
                    c.execute(
                        """
                        UPDATE medicines 
                        SET brand_name=%s, generic_name=%s, category=%s, unit_price=%s, stock_qty=%s 
                        WHERE id=%s
                    """,
                        (
                            e_brand,
                            e_generic,
                            e_category,
                            e_price,
                            e_qty,
                            int(selected_med["id"]),
                        ),
                    )
                    conn.commit()
                    c.close()
                    st.success(f"Updated record for '{e_brand}'!")
                    st.rerun()

                st.divider()
                st.subheader("🗑️ Delete Record")
                confirm_del_med = st.checkbox(
                    "I want to permanently delete this medicine from inventory",
                    key="del_med_check",
                )
                if st.button("Delete Selected Medicine", type="primary"):
                    if not confirm_del_med:
                        st.warning(
                            "Please check the confirmation box above to proceed with deletion."
                        )
                    else:
                        conn = get_connection()
                        c = conn.cursor()
                        # Optional: delete dependent sales/deliveries first or clear reference if needed
                        c.execute(
                            "DELETE FROM medicines WHERE id = %s",
                            (int(selected_med["id"]),),
                        )
                        conn.commit()
                        c.close()
                        st.success(
                            f"Deleted '{selected_med['brand_name']}' from inventory!"
                        )
                        st.rerun()

    # --- 3. POINT OF SALE ---
    elif choice == "POS / Record Sale":
        st.header("🛒 Point of Sale / Record Sale")

        conn = get_connection()
        medicines = pd.read_sql(
            "SELECT id, brand_name, generic_name, unit_price, stock_qty FROM medicines WHERE stock_qty > 0",
            conn,
        )

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
        st.dataframe(deliveries_df, use_container_width=True)

    # --- 5. SALES HISTORY ---
    elif choice == "Sales History":
        st.header("📈 Sales Records & Reports")

        conn = get_connection()
        sales_df = pd.read_sql(
            "SELECT * FROM sales ORDER BY timestamp DESC", conn
        )

        if not sales_df.empty:
            total_rev = sales_df["total_price"].sum()
            st.metric("Total Recorded Revenue", f"₱{total_rev:,.2f}")
            st.dataframe(sales_df, use_container_width=True)
        else:
            st.info("No sales transactions recorded yet.")

    # --- 6. USER MANAGEMENT (Admin Only) ---
    elif choice == "User Management":
        st.header("🛡️ Staff User & Role Management")
        tab1, tab2, tab3 = st.tabs(
            [
                "View Existing Staff",
                "Create New Staff Account",
                "Edit / Delete User",
            ]
        )

        with tab1:
            conn = get_connection()
            users_df = pd.read_sql(
                "SELECT id, username, role, name FROM app_users", conn
            )
            st.dataframe(users_df, use_container_width=True)

        with tab2:
            st.subheader("Add New Staff Login")
            with st.form("new_user_form"):
                new_username = st.text_input("Username")
                new_password = st.text_input("Password", type="password")
                new_name = st.text_input("Staff Full Name / Label")
                new_role = st.selectbox(
                    "Assigned Role",
                    [
                        "Administrator",
                        "Management Viewer",
                        "Cashier / Sales",
                        "Inventory Custodian",
                        "Delivery Custodian",
                    ],
                )

                create_user_btn = st.form_submit_button("Create Account")

                if create_user_btn:
                    if new_username and new_password and new_name:
                        try:
                            conn = get_connection()
                            c = conn.cursor()
                            c.execute(
                                """
                                INSERT INTO app_users (username, password, role, name)
                                VALUES (%s, %s, %s, %s)
                            """,
                                (
                                    new_username,
                                    new_password,
                                    new_role,
                                    new_name,
                                ),
                            )
                            conn.commit()
                            c.close()
                            st.success(
                                f"Successfully created account for '{new_name}' with role '{new_role}'!"
                            )
                            st.rerun()
                        except Exception as e:
                            st.error(
                                f"Error creating user (Username might already exist): {e}"
                            )
                    else:
                        st.error("Please fill in all fields.")

        with tab3:
            st.subheader("Edit or Delete Staff Account")
            conn = get_connection()
            users_df = pd.read_sql(
                "SELECT id, username, role, name FROM app_users", conn
            )

            if users_df.empty:
                st.info("No users found.")
            else:
                user_dict = {
                    f"{row['name']} ({row['username']} - {row['role']})": row
                    for _, row in users_df.iterrows()
                }
                selected_user_label = st.selectbox(
                    "Select User to Manage",
                    list(user_dict.keys()),
                    key="edit_user_selectbox",
                )
                selected_user = user_dict[selected_user_label]

                with st.form("edit_user_form"):
                    e_name = st.text_input(
                        "Staff Full Name / Label", value=selected_user["name"]
                    )
                    role_options = [
                        "Administrator",
                        "Management Viewer",
                        "Cashier / Sales",
                        "Inventory Custodian",
                        "Delivery Custodian",
                    ]
                    current_role_idx = (
                        role_options.index(selected_user["role"])
                        if selected_user["role"] in role_options
                        else 0
                    )
                    e_role = st.selectbox(
                        "Assigned Role",
                        role_options,
                        index=current_role_idx,
                    )
                    e_password = st.text_input(
                        "New Password (leave blank to keep current)",
                        type="password",
                    )

                    update_btn = st.form_submit_button("Update User Details")

                if update_btn:
                    conn = get_connection()
                    c = conn.cursor()
                    if e_password:
                        c.execute(
                            "UPDATE app_users SET name = %s, role = %s, password = %s WHERE id = %s",
                            (
                                e_name,
                                e_role,
                                e_password,
                                int(selected_user["id"]),
                            ),
                        )
                    else:
                        c.execute(
                            "UPDATE app_users SET name = %s, role = %s WHERE id = %s",
                            (e_name, e_role, int(selected_user["id"])),
                        )
                    conn.commit()
                    c.close()
                    st.success(
                        f"Successfully updated user '{selected_user['username']}'!"
                    )
                    st.rerun()

                st.divider()
                st.subheader("⚠️ Danger Zone")
                confirm_delete = st.checkbox(
                    "I want to delete this user account", key="confirm_del_user"
                )
                if st.button("Delete Selected User", type="primary"):
                    if selected_user["username"] == "admin":
                        st.error(
                            "You cannot delete the primary admin account!"
                        )
                    elif not confirm_delete:
                        st.warning(
                            "Please check the confirmation box above to delete."
                        )
                    else:
                        conn = get_connection()
                        c = conn.cursor()
                        c.execute(
                            "DELETE FROM app_users WHERE id = %s",
                            (int(selected_user["id"]),),
                        )
                        conn.commit()
                        c.close()
                        st.success(
                            f"User '{selected_user['username']}' has been deleted."
                        )
                        st.rerun()
