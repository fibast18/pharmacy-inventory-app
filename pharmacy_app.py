import sqlite3
import pandas as pd
import streamlit as st
from datetime import date, datetime

# --- DATABASE SETUP ---
DB_FILE = "pharmacy_inventory.db"


def get_connection():
    conn = sqlite3.connect(DB_FILE)
    return conn


def init_db():
    conn = get_connection()
    c = conn.cursor()

    # Medicines Table
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS medicines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brand_name TEXT NOT NULL,
            generic_name TEXT NOT NULL,
            category TEXT,
            unit_price REAL NOT NULL,
            stock_qty INTEGER NOT NULL,
            min_threshold INTEGER DEFAULT 10,
            expiry_date DATE
        )
    """
    )

    # Sales Table
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            medicine_id INTEGER,
            medicine_name TEXT,
            qty_sold INTEGER,
            unit_price REAL,
            total_price REAL,
            FOREIGN KEY (medicine_id) REFERENCES medicines(id)
        )
    """
    )

    # Deliveries Table
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            delivery_date DATE,
            dr_number TEXT,
            supplier TEXT,
            medicine_id INTEGER,
            qty_received INTEGER,
            FOREIGN KEY (medicine_id) REFERENCES medicines(id)
        )
    """
    )

    conn.commit()
    conn.close()


# Initialize database schema on startup
init_db()

# --- APP LAYOUT ---
st.set_page_config(
    page_title="Pharmacy Inventory & Sales System", layout="wide"
)
st.title("💊 Pharmacy Inventory & Sales System")

menu = [
    "Dashboard",
    "Inventory Management",
    "POS / Record Sale",
    "Deliveries",
    "Sales History",
]
choice = st.sidebar.selectbox("Navigation Menu", menu)

# --- 1. DASHBOARD ---
if choice == "Dashboard":
    st.header("📊 Overview & Alerts")

    conn = get_connection()

    # Low Stock Items
    low_stock_df = pd.read_sql_query(
        "SELECT brand_name, generic_name, stock_qty, min_threshold FROM medicines WHERE stock_qty <= min_threshold",
        conn,
    )

    # Expiring Items (within 60 days)
    expiring_df = pd.read_sql_query(
        "SELECT brand_name, generic_name, stock_qty, expiry_date FROM medicines WHERE expiry_date <= date('now', '+60 days') AND expiry_date >= date('now')",
        conn,
    )

    # Metrics
    total_products = pd.read_sql_query(
        "SELECT COUNT(*) as count FROM medicines", conn
    ).iloc[0]["count"]
    today_sales = pd.read_sql_query(
        "SELECT SUM(total_price) as total FROM sales WHERE DATE(timestamp) = DATE('now')",
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
        inventory_df = pd.read_sql_query("SELECT * FROM medicines", conn)
        conn.close()

        search = st.text_input(
            "🔍 Search Medicine (Brand, Generic, or Category)"
        )
        if search:
            inventory_df = inventory_df[
                inventory_df["brand_name"].str.contains(search, case=False)
                | inventory_df["generic_name"].str.contains(search, case=False)
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
                        VALUES (?, ?, ?, ?, ?, ?, ?)
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
                    conn.close()
                    st.success(f"Added '{brand_name}' to inventory.")
                    st.rerun()
                else:
                    st.error("Please fill in both Brand Name and Generic Name.")

# --- 3. POINT OF SALE ---
elif choice == "POS / Record Sale":
    st.header("🛒 Point of Sale / Record Sale")

    conn = get_connection()
    medicines = pd.read_sql_query(
        "SELECT id, brand_name, generic_name, unit_price, stock_qty FROM medicines WHERE stock_qty > 0",
        conn,
    )
    conn.close()

    if medicines.empty:
        st.warning(
            "No available stock in inventory. Please add stock or record a delivery first."
        )
    else:
        # Create select options
        med_dict = {
            f"{row['brand_name']} ({row['generic_name']}) - Stock: {row['stock_qty']} | Price: ₱{row['unit_price']:.2f}": row
            for _, row in medicines.iterrows()
        }

        selected_item_label = st.selectbox("Select Medicine", list(med_dict.keys()))
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

            # Record Sale
            c.execute(
                """
                INSERT INTO sales (medicine_id, medicine_name, qty_sold, unit_price, total_price)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    selected_item["id"],
                    selected_item["brand_name"],
                    qty,
                    selected_item["unit_price"],
                    total,
                ),
            )

            # Deduct Inventory
            c.execute(
                """
                UPDATE medicines 
                SET stock_qty = stock_qty - ? 
                WHERE id = ?
            """,
                (qty, selected_item["id"]),
            )

            conn.commit()
            conn.close()

            st.success(
                f"Sold {qty} unit(s) of {selected_item['brand_name']} for ₱{total:,.2f}."
            )
            st.rerun()

# --- 4. DELIVERIES ---
elif choice == "Deliveries":
    st.header("🚚 Incoming Deliveries")

    conn = get_connection()
    medicines = pd.read_sql_query("SELECT id, brand_name, generic_name FROM medicines", conn)
    conn.close()

    st.subheader("Log Delivery Shipment")

    if medicines.empty:
        st.info("Please add medicines to your master list in 'Inventory Management' first.")
    else:
        med_dict = {
            f"{row['brand_name']} ({row['generic_name']})": row["id"]
            for _, row in medicines.iterrows()
        }

        with st.form("delivery_form"):
            dr_number = st.text_input("Delivery Receipt (DR) No.")
            supplier = st.text_input("Supplier Name")
            del_date = st.date_input("Delivery Date", value=date.today())

            selected_item_label = st.selectbox("Select Medicine Received", list(med_dict.keys()))
            qty_received = st.number_input("Quantity Received", min_value=1, step=1)

            submitted = st.form_submit_button("Record Delivery & Update Stock")

            if submitted:
                med_id = med_dict[selected_item_label]

                conn = get_connection()
                c = conn.cursor()

                # Insert into Deliveries log
                c.execute(
                    """
                    INSERT INTO deliveries (delivery_date, dr_number, supplier, medicine_id, qty_received)
                    VALUES (?, ?, ?, ?, ?)
                """,
                    (del_date, dr_number, supplier, med_id, qty_received),
                )

                # Add to current stock
                c.execute(
                    """
                    UPDATE medicines 
                    SET stock_qty = stock_qty + ? 
                    WHERE id = ?
                """,
                    (qty_received, med_id),
                )

                conn.commit()
                conn.close()

                st.success(f"Successfully added {qty_received} units to inventory!")
                st.rerun()

    st.divider()
    st.subheader("Delivery Log History")
    conn = get_connection()
    deliveries_df = pd.read_sql_query(
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
    sales_df = pd.read_sql_query(
        "SELECT * FROM sales ORDER BY timestamp DESC", conn
    )
    conn.close()

    if not sales_df.empty:
        total_rev = sales_df["total_price"].sum()
        st.metric("Total Recorded Revenue", f"₱{total_rev:,.2f}")
        st.dataframe(sales_df, use_container_width=True)
    else:
        st.info("No sales transactions recorded yet.")
