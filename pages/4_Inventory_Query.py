import streamlit as st
from db import run_select, get_lookup_options


def clean_text(value):
    """
    Convert None to empty string for safe string operations.
    """
    if value is None:
        return ""
    return str(value).strip()


def format_warehouse_label(row):
    """
    Build a friendly warehouse label.
    """
    return f"{row[1]} ({row[2]})"


def format_location_label(row):
    """
    Build a friendly storage location label.
    """
    warehouse_name = row[2]
    location_code = row[1]
    return f"{warehouse_name} - {location_code}"


def get_single_value(query, params=None, default_value=0):
    """
    Run a query that returns one row and one value.
    """
    success, result = run_select(query, params=params, fetchone=True)

    if not success:
        return None, result

    if result is None or result[0] is None:
        return default_value, None

    return result[0], None


def load_warehouses():
    """
    Load active warehouses for filter options.
    """
    query = """
        SELECT id, warehouse_name, warehouse_code
        FROM warehouses
        WHERE is_active = TRUE
        ORDER BY warehouse_name;
    """
    return get_lookup_options(query)


def load_locations(warehouse_id=None):
    """
    Load active storage locations.
    If warehouse_id is given, only load locations from that warehouse.
    """
    query = """
        SELECT
            sl.id,
            sl.location_code,
            w.warehouse_name
        FROM storage_locations sl
        JOIN warehouses w ON sl.warehouse_id = w.id
        WHERE sl.is_active = TRUE
          AND (%s IS NULL OR sl.warehouse_id = %s)
        ORDER BY w.warehouse_name, sl.location_code;
    """
    return get_lookup_options(query, params=(warehouse_id, warehouse_id))


def load_inventory_rows(
    sku_filter="",
    chemical_name_filter="",
    warehouse_id=None,
    location_id=None,
    low_stock_only=False
):
    """
    Load grouped current inventory rows.
    Inventory is calculated from stock document items:
    - INBOUND adds quantity
    - OUTBOUND subtracts quantity
    """
    query = """
        WITH inventory_base AS (
            SELECT
                c.id AS chemical_id,
                c.sku,
                c.chemical_name,
                c.unit,
                c.min_stock,
                w.id AS warehouse_id,
                w.warehouse_name,
                sl.id AS location_id,
                sl.location_code,
                COALESCE(sdi.batch_no, '') AS batch_no,
                sdi.manufacture_date,
                sdi.expiry_date,
                SUM(
                    CASE
                        WHEN sd.doc_type = 'INBOUND' THEN sdi.quantity
                        WHEN sd.doc_type = 'OUTBOUND' THEN -sdi.quantity
                        ELSE 0
                    END
                ) AS on_hand_quantity
            FROM stock_document_items sdi
            JOIN stock_documents sd
                ON sdi.document_id = sd.id
            JOIN chemicals c
                ON sdi.chemical_id = c.id
            JOIN storage_locations sl
                ON sdi.location_id = sl.id
            JOIN warehouses w
                ON sl.warehouse_id = w.id
            WHERE (%s = '' OR c.sku ILIKE %s)
              AND (%s = '' OR c.chemical_name ILIKE %s)
              AND (%s IS NULL OR w.id = %s)
              AND (%s IS NULL OR sl.id = %s)
            GROUP BY
                c.id,
                c.sku,
                c.chemical_name,
                c.unit,
                c.min_stock,
                w.id,
                w.warehouse_name,
                sl.id,
                sl.location_code,
                COALESCE(sdi.batch_no, ''),
                sdi.manufacture_date,
                sdi.expiry_date
        ),
        inventory_enriched AS (
            SELECT
                chemical_id,
                sku,
                chemical_name,
                unit,
                min_stock,
                warehouse_id,
                warehouse_name,
                location_id,
                location_code,
                batch_no,
                manufacture_date,
                expiry_date,
                on_hand_quantity,
                SUM(on_hand_quantity) OVER (PARTITION BY chemical_id) AS chemical_total_quantity
            FROM inventory_base
        )
        SELECT
            chemical_id,
            sku,
            chemical_name,
            unit,
            min_stock,
            warehouse_id,
            warehouse_name,
            location_id,
            location_code,
            batch_no,
            manufacture_date,
            expiry_date,
            on_hand_quantity,
            chemical_total_quantity,
            CASE
                WHEN chemical_total_quantity < min_stock THEN TRUE
                ELSE FALSE
            END AS is_low_stock
        FROM inventory_enriched
        WHERE on_hand_quantity <> 0
          AND (%s = FALSE OR chemical_total_quantity < min_stock)
        ORDER BY chemical_name, warehouse_name, location_code, batch_no;
    """

    sku_filter = clean_text(sku_filter)
    chemical_name_filter = clean_text(chemical_name_filter)

    params = (
        sku_filter,
        f"%{sku_filter}%",
        chemical_name_filter,
        f"%{chemical_name_filter}%",
        warehouse_id,
        warehouse_id,
        location_id,
        location_id,
        low_stock_only,
    )

    success, result = run_select(query, params=params)
    if not success:
        return None, result
    return result, None


def load_inventory_summary(
    sku_filter="",
    chemical_name_filter="",
    warehouse_id=None,
    location_id=None,
    low_stock_only=False
):
    """
    Load summary metrics for the current inventory filter.
    """
    query = """
        WITH inventory_base AS (
            SELECT
                c.id AS chemical_id,
                c.min_stock,
                COALESCE(sdi.batch_no, '') AS batch_no,
                sdi.expiry_date,
                sl.id AS location_id,
                w.id AS warehouse_id,
                SUM(
                    CASE
                        WHEN sd.doc_type = 'INBOUND' THEN sdi.quantity
                        WHEN sd.doc_type = 'OUTBOUND' THEN -sdi.quantity
                        ELSE 0
                    END
                ) AS on_hand_quantity
            FROM stock_document_items sdi
            JOIN stock_documents sd
                ON sdi.document_id = sd.id
            JOIN chemicals c
                ON sdi.chemical_id = c.id
            JOIN storage_locations sl
                ON sdi.location_id = sl.id
            JOIN warehouses w
                ON sl.warehouse_id = w.id
            WHERE (%s = '' OR c.sku ILIKE %s)
              AND (%s = '' OR c.chemical_name ILIKE %s)
              AND (%s IS NULL OR w.id = %s)
              AND (%s IS NULL OR sl.id = %s)
            GROUP BY
                c.id,
                c.min_stock,
                COALESCE(sdi.batch_no, ''),
                sdi.expiry_date,
                sl.id,
                w.id
        ),
        enriched AS (
            SELECT
                chemical_id,
                min_stock,
                batch_no,
                expiry_date,
                location_id,
                warehouse_id,
                on_hand_quantity,
                SUM(on_hand_quantity) OVER (PARTITION BY chemical_id) AS chemical_total_quantity
            FROM inventory_base
        ),
        filtered AS (
            SELECT *
            FROM enriched
            WHERE on_hand_quantity <> 0
              AND (%s = FALSE OR chemical_total_quantity < min_stock)
        )
        SELECT
            COUNT(*) AS inventory_row_count,
            COALESCE(SUM(on_hand_quantity), 0) AS total_on_hand_quantity,
            COUNT(DISTINCT chemical_id) FILTER (
                WHERE chemical_total_quantity < min_stock
            ) AS low_stock_chemical_count,
            COUNT(*) FILTER (
                WHERE expiry_date IS NOT NULL AND expiry_date < CURRENT_DATE
            ) AS expired_batch_count
        FROM filtered;
    """

    sku_filter = clean_text(sku_filter)
    chemical_name_filter = clean_text(chemical_name_filter)

    params = (
        sku_filter,
        f"%{sku_filter}%",
        chemical_name_filter,
        f"%{chemical_name_filter}%",
        warehouse_id,
        warehouse_id,
        location_id,
        location_id,
        low_stock_only,
    )

    success, result = run_select(query, params=params, fetchone=True)
    if not success:
        return None, result
    return result, None


def get_expiry_status(expiry_date):
    """
    Build a simple expiry status label.
    """
    if expiry_date is None:
        return "No Expiry Date"

    days_left = (expiry_date - st.session_state["inventory_today"]).days

    if days_left < 0:
        return "Expired"
    if days_left <= 30:
        return "Expiring Within 30 Days"
    return "Valid"


st.title("Inventory Query")
st.write(
    "View current inventory grouped by chemical, warehouse, storage location, and batch."
)

if "inventory_today" not in st.session_state:
    today_value, today_error = get_single_value("SELECT CURRENT_DATE;", default_value=None)
    if today_error:
        st.error(f"Unable to load current date from database. {today_error}")
        st.stop()
    st.session_state["inventory_today"] = today_value

warehouse_rows = load_warehouses()
warehouse_map = {None: "-- All Warehouses --"}
warehouse_options = [None]

for row in warehouse_rows:
    warehouse_options.append(row[0])
    warehouse_map[row[0]] = format_warehouse_label(row)

filter_col1, filter_col2, filter_col3, filter_col4, filter_col5 = st.columns(5)

with filter_col1:
    filter_sku = st.text_input("Search SKU")

with filter_col2:
    filter_chemical_name = st.text_input("Search Chemical Name")

with filter_col3:
    selected_warehouse_id = st.selectbox(
        "Warehouse",
        options=warehouse_options,
        format_func=lambda x: warehouse_map[x]
    )

location_rows = load_locations(selected_warehouse_id)
location_map = {None: "-- All Locations --"}
location_options = [None]

for row in location_rows:
    location_options.append(row[0])
    location_map[row[0]] = format_location_label(row)

with filter_col4:
    selected_location_id = st.selectbox(
        "Storage Location",
        options=location_options,
        format_func=lambda x: location_map[x]
    )

with filter_col5:
    low_stock_only = st.checkbox("Low-Stock Only")

summary_row, summary_error = load_inventory_summary(
    sku_filter=filter_sku,
    chemical_name_filter=filter_chemical_name,
    warehouse_id=selected_warehouse_id,
    location_id=selected_location_id,
    low_stock_only=low_stock_only
)

if summary_error:
    st.error(f"Unable to load inventory summary. {summary_error}")
else:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Inventory Rows", summary_row[0])
    col2.metric("Total On-Hand Quantity", summary_row[1])
    col3.metric("Low-Stock Chemicals", summary_row[2])
    col4.metric("Expired Batches", summary_row[3])

inventory_rows, inventory_error = load_inventory_rows(
    sku_filter=filter_sku,
    chemical_name_filter=filter_chemical_name,
    warehouse_id=selected_warehouse_id,
    location_id=selected_location_id,
    low_stock_only=low_stock_only
)

st.subheader("Current Inventory")

if inventory_error:
    st.error(f"Unable to load inventory data. {inventory_error}")
else:
    if inventory_rows:
        display_rows = []

        for row in inventory_rows:
            expiry_status = get_expiry_status(row[11])

            display_rows.append(
                {
                    "Chemical ID": row[0],
                    "SKU": row[1],
                    "Chemical Name": row[2],
                    "Unit": row[3],
                    "Minimum Stock": row[4],
                    "Warehouse": row[6],
                    "Location": row[8],
                    "Batch No": row[9],
                    "Manufacture Date": row[10],
                    "Expiry Date": row[11],
                    "Expiry Status": expiry_status,
                    "On-Hand Quantity": row[12],
                    "Chemical Total Quantity": row[13],
                    "Low Stock": row[14],
                }
            )

        st.dataframe(display_rows, use_container_width=True)
        st.caption(f"Total inventory records found: {len(display_rows)}")
    else:
        st.warning("No inventory records matched the current filters.")

st.subheader("How Inventory Is Calculated")
st.write(
    """
    Current inventory is calculated from stock transactions:
    - INBOUND item quantities are added
    - OUTBOUND item quantities are subtracted

    The result is grouped by chemical, warehouse, storage location, and batch.
    """
)