import streamlit as st
from db import run_select


st.set_page_config(
    page_title="Chemical Warehouse Management System",
    page_icon="🧪",
    layout="wide"
)


def get_single_value(query, params=None, default_value=0):
    """
    Run a query that returns one row and one value.
    Returns a default value if the query fails or returns no data.
    """
    success, result = run_select(query, params=params, fetchone=True)

    if not success:
        return None, result

    if result is None or result[0] is None:
        return default_value, None

    return result[0], None


def load_dashboard_metrics():
    """
    Load all dashboard metrics from the database.
    """
    metrics = {}

    total_chemicals_query = """
        SELECT COUNT(*)
        FROM chemicals
        WHERE is_active = TRUE;
    """
    total_warehouses_query = """
        SELECT COUNT(*)
        FROM warehouses
        WHERE is_active = TRUE;
    """
    total_inventory_query = """
        SELECT COALESCE(SUM(
            CASE
                WHEN sd.doc_type = 'INBOUND' THEN sdi.quantity
                WHEN sd.doc_type = 'OUTBOUND' THEN -sdi.quantity
                ELSE 0
            END
        ), 0) AS total_inventory
        FROM stock_document_items sdi
        JOIN stock_documents sd ON sdi.document_id = sd.id;
    """
    low_stock_count_query = """
        SELECT COUNT(*)
        FROM (
            SELECT
                c.id,
                c.sku,
                c.chemical_name,
                c.min_stock,
                COALESCE(SUM(
                    CASE
                        WHEN sd.doc_type = 'INBOUND' THEN sdi.quantity
                        WHEN sd.doc_type = 'OUTBOUND' THEN -sdi.quantity
                        ELSE 0
                    END
                ), 0) AS on_hand_quantity
            FROM chemicals c
            LEFT JOIN stock_document_items sdi
                ON c.id = sdi.chemical_id
            LEFT JOIN stock_documents sd
                ON sdi.document_id = sd.id
            WHERE c.is_active = TRUE
            GROUP BY c.id, c.sku, c.chemical_name, c.min_stock
        ) AS inventory_summary
        WHERE on_hand_quantity < min_stock;
    """

    value, error = get_single_value(total_chemicals_query, default_value=0)
    if error:
        return None, error
    metrics["total_chemicals"] = value

    value, error = get_single_value(total_warehouses_query, default_value=0)
    if error:
        return None, error
    metrics["total_warehouses"] = value

    value, error = get_single_value(total_inventory_query, default_value=0)
    if error:
        return None, error
    metrics["total_inventory"] = value

    value, error = get_single_value(low_stock_count_query, default_value=0)
    if error:
        return None, error
    metrics["low_stock_count"] = value

    return metrics, None


def load_recent_stock_documents(limit=10):
    """
    Load recent stock document records for the dashboard table.
    """
    query = """
        SELECT
            sd.doc_no,
            sd.doc_type,
            w.warehouse_name,
            sd.transaction_date,
            sd.operator_name,
            COALESCE(sd.counterparty_name, '') AS counterparty_name
        FROM stock_documents sd
        JOIN warehouses w ON sd.warehouse_id = w.id
        ORDER BY sd.transaction_date DESC, sd.id DESC
        LIMIT %s;
    """

    success, result = run_select(query, params=(limit,))
    if not success:
        return None, result

    records = []
    for row in result:
        records.append({
            "Document No": row[0],
            "Type": row[1],
            "Warehouse": row[2],
            "Transaction Date": row[3],
            "Operator": row[4],
            "Counterparty": row[5]
        })

    return records, None


st.title("Chemical Warehouse Management System")

st.write(
    """
    Welcome to the Chemical Warehouse Management System.

    This system helps warehouse administrators manage chemical master data,
    warehouses, storage locations, stock in/out transactions, inventory lookup,
    and stocktake records.
    """
)

st.info("Please use the sidebar to navigate to different functional pages.")

st.subheader("Dashboard Overview")

metrics, metrics_error = load_dashboard_metrics()

if metrics_error:
    st.error(f"Unable to load dashboard metrics. {metrics_error}")
else:
    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total Chemicals", metrics["total_chemicals"])
    col2.metric("Total Warehouses", metrics["total_warehouses"])
    col3.metric("Total Current Inventory Quantity", metrics["total_inventory"])
    col4.metric("Low-Stock Item Count", metrics["low_stock_count"])

st.subheader("Recent Stock Document Records")

recent_docs, recent_docs_error = load_recent_stock_documents(limit=10)

if recent_docs_error:
    st.error(f"Unable to load recent stock document records. {recent_docs_error}")
else:
    if recent_docs:
        st.dataframe(recent_docs, use_container_width=True)
    else:
        st.warning("No stock document records found yet.")

st.subheader("How to Use This System")
st.write(
    """
    - Use the sidebar to open each management page.
    - Add chemical, warehouse, and storage location master data first.
    - Then create inbound and outbound stock documents.
    - Use the inventory query page to check current stock.
    - Use the stocktake page to record counting and compare with system quantities.
    """
)