import streamlit as st
from datetime import datetime
from db import run_select, run_action, value_exists, get_lookup_options, get_connection
from validation import (
    validate_stock_document_header,
    validate_stock_document_item,
    add_unique_error,
    add_outbound_stock_error,
)


DOC_TYPES = ["INBOUND", "OUTBOUND"]


def clean_text(value):
    """
    Convert blank text to None after stripping whitespace.
    """
    if value is None:
        return None
    text = str(value).strip()
    return text if text != "" else None


def show_validation_errors(errors):
    """
    Show all validation errors together.
    """
    for error in errors:
        st.error(error)


def format_decimal(value):
    """
    Format numeric values for display.
    """
    if value is None:
        return 0
    return float(value)


def build_timestamp(date_value, time_value):
    """
    Combine date and time values into a Python datetime.
    """
    return datetime.combine(date_value, time_value)


def load_warehouses():
    """
    Load active warehouses for dropdown lists.
    """
    query = """
        SELECT id, warehouse_name, warehouse_code
        FROM warehouses
        WHERE is_active = TRUE
        ORDER BY warehouse_name;
    """
    return get_lookup_options(query)


def load_chemicals():
    """
    Load active chemicals for dropdown lists.
    """
    query = """
        SELECT id, sku, chemical_name, unit
        FROM chemicals
        WHERE is_active = TRUE
        ORDER BY chemical_name;
    """
    return get_lookup_options(query)


def load_locations_by_warehouse(warehouse_id):
    """
    Load active storage locations for a selected warehouse.
    """
    query = """
        SELECT id, location_code, location_type
        FROM storage_locations
        WHERE warehouse_id = %s
          AND is_active = TRUE
        ORDER BY location_code;
    """
    return get_lookup_options(query, params=(warehouse_id,))


def load_all_documents():
    """
    Load all stock documents for dropdowns.
    """
    query = """
        SELECT
            sd.id,
            sd.doc_no,
            sd.doc_type,
            w.warehouse_name,
            sd.transaction_date
        FROM stock_documents sd
        JOIN warehouses w ON sd.warehouse_id = w.id
        ORDER BY sd.transaction_date DESC, sd.id DESC;
    """
    success, result = run_select(query)
    if not success:
        return None, result
    return result, None


def load_stock_documents(doc_no_filter="", doc_type_filter="", warehouse_filter=None,
                         start_date=None, end_date=None):
    """
    Load stock documents with search filters.
    """
    query = """
        SELECT
            sd.id,
            sd.doc_no,
            sd.doc_type,
            w.warehouse_name,
            sd.transaction_date,
            sd.operator_name,
            COALESCE(sd.counterparty_name, '') AS counterparty_name,
            COALESCE(sd.notes, '') AS notes,
            COUNT(sdi.id) AS item_count,
            COALESCE(SUM(sdi.quantity), 0) AS total_quantity
        FROM stock_documents sd
        JOIN warehouses w ON sd.warehouse_id = w.id
        LEFT JOIN stock_document_items sdi ON sd.id = sdi.document_id
        WHERE (%s = '' OR sd.doc_no ILIKE %s)
          AND (%s = '' OR sd.doc_type = %s)
          AND (%s IS NULL OR sd.warehouse_id = %s)
          AND (%s IS NULL OR DATE(sd.transaction_date) >= %s)
          AND (%s IS NULL OR DATE(sd.transaction_date) <= %s)
        GROUP BY
            sd.id,
            sd.doc_no,
            sd.doc_type,
            w.warehouse_name,
            sd.transaction_date,
            sd.operator_name,
            sd.counterparty_name,
            sd.notes
        ORDER BY sd.transaction_date DESC, sd.id DESC;
    """

    doc_no_filter = doc_no_filter.strip()

    params = (
        doc_no_filter,
        f"%{doc_no_filter}%",
        doc_type_filter,
        doc_type_filter,
        warehouse_filter,
        warehouse_filter,
        start_date,
        start_date,
        end_date,
        end_date,
    )

    success, result = run_select(query, params=params)
    if not success:
        return None, result
    return result, None


def load_document_items(document_id):
    """
    Load item lines for one stock document.
    """
    query = """
        SELECT
            sdi.id,
            c.sku,
            c.chemical_name,
            sl.location_code,
            COALESCE(sdi.batch_no, '') AS batch_no,
            sdi.manufacture_date,
            sdi.expiry_date,
            sdi.quantity,
            sdi.unit_price,
            c.id AS chemical_id,
            sl.id AS location_id
        FROM stock_document_items sdi
        JOIN chemicals c ON sdi.chemical_id = c.id
        JOIN storage_locations sl ON sdi.location_id = sl.id
        WHERE sdi.document_id = %s
        ORDER BY sdi.id;
    """
    success, result = run_select(query, params=(document_id,))
    if not success:
        return None, result
    return result, None


def get_document_by_id(document_id):
    """
    Load one stock document header by ID.
    """
    query = """
        SELECT
            id,
            doc_no,
            doc_type,
            warehouse_id,
            transaction_date,
            operator_name,
            counterparty_name,
            notes
        FROM stock_documents
        WHERE id = %s;
    """
    success, result = run_select(query, params=(document_id,), fetchone=True)
    if not success:
        return None, result
    return result, None


def get_document_item_by_id(item_id):
    """
    Load one stock document item by ID.
    """
    query = """
        SELECT
            id,
            document_id,
            chemical_id,
            location_id,
            batch_no,
            manufacture_date,
            expiry_date,
            quantity,
            unit_price
        FROM stock_document_items
        WHERE id = %s;
    """
    success, result = run_select(query, params=(item_id,), fetchone=True)
    if not success:
        return None, result
    return result, None


def document_no_exists(doc_no, exclude_id=None):
    """
    Check whether a document number already exists.
    """
    if exclude_id is None:
        query = """
            SELECT 1
            FROM stock_documents
            WHERE LOWER(doc_no) = LOWER(%s);
        """
        return value_exists(query, params=(doc_no,))

    query = """
        SELECT 1
        FROM stock_documents
        WHERE LOWER(doc_no) = LOWER(%s)
          AND id <> %s;
    """
    return value_exists(query, params=(doc_no, exclude_id))


def location_belongs_to_warehouse(location_id, warehouse_id):
    """
    Check whether the selected location belongs to the selected warehouse.
    """
    query = """
        SELECT 1
        FROM storage_locations
        WHERE id = %s
          AND warehouse_id = %s;
    """
    return value_exists(query, params=(location_id, warehouse_id))


def get_available_stock(chemical_id, location_id, batch_no=None):
    """
    Calculate current available stock by chemical, location, and batch.
    INBOUND adds quantity and OUTBOUND subtracts quantity.
    """
    query = """
        SELECT COALESCE(SUM(
            CASE
                WHEN sd.doc_type = 'INBOUND' THEN sdi.quantity
                WHEN sd.doc_type = 'OUTBOUND' THEN -sdi.quantity
                ELSE 0
            END
        ), 0) AS available_stock
        FROM stock_document_items sdi
        JOIN stock_documents sd ON sdi.document_id = sd.id
        WHERE sdi.chemical_id = %s
          AND sdi.location_id = %s
          AND COALESCE(sdi.batch_no, '') = COALESCE(%s, '');
    """
    success, result = run_select(
        query,
        params=(chemical_id, location_id, clean_text(batch_no)),
        fetchone=True
    )

    if not success or result is None or result[0] is None:
        return 0
    return float(result[0])


def get_reserved_outbound_quantity_from_draft(draft_items, chemical_id, location_id, batch_no):
    """
    Sum the quantity of matching outbound lines already added to the current draft.
    """
    total = 0.0
    normalized_batch = clean_text(batch_no) or ""

    for item in draft_items:
        item_batch = clean_text(item["batch_no"]) or ""
        if (
            item["chemical_id"] == chemical_id
            and item["location_id"] == location_id
            and item_batch == normalized_batch
        ):
            total += float(item["quantity"])

    return total


def create_document_with_items(header_data, item_lines):
    """
    Create one stock document header and all item lines in a single transaction.
    """
    conn = None
    cur = None

    try:
        conn = get_connection()
        cur = conn.cursor()

        header_query = """
            INSERT INTO stock_documents
            (
                doc_no,
                doc_type,
                warehouse_id,
                transaction_date,
                operator_name,
                counterparty_name,
                notes
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """

        cur.execute(
            header_query,
            (
                header_data["doc_no"],
                header_data["doc_type"],
                header_data["warehouse_id"],
                header_data["transaction_date"],
                header_data["operator_name"],
                header_data["counterparty_name"],
                header_data["notes"],
            ),
        )

        document_id = cur.fetchone()[0]

        item_query = """
            INSERT INTO stock_document_items
            (
                document_id,
                chemical_id,
                location_id,
                batch_no,
                manufacture_date,
                expiry_date,
                quantity,
                unit_price
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        """

        for item in item_lines:
            cur.execute(
                item_query,
                (
                    document_id,
                    item["chemical_id"],
                    item["location_id"],
                    clean_text(item["batch_no"]),
                    item["manufacture_date"],
                    item["expiry_date"],
                    item["quantity"],
                    item["unit_price"],
                ),
            )

        conn.commit()
        return True, document_id

    except Exception:
        if conn is not None:
            conn.rollback()
        return False, "Database error while creating the stock document."

    finally:
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()


def format_warehouse_label(row):
    return f"{row[1]} ({row[2]})"


def format_chemical_label(row):
    return f"{row[1]} - {row[2]} ({row[3]})"


def format_location_label(row):
    location_type = row[2] if row[2] else "No Type"
    return f"{row[1]} ({location_type})"


if "draft_stock_items" not in st.session_state:
    st.session_state["draft_stock_items"] = []


st.title("Stock In/Out Management")
st.write("Create, view, edit, and delete inbound and outbound stock documents.")

warehouse_rows = load_warehouses()
chemical_rows = load_chemicals()

warehouse_map = {row[0]: format_warehouse_label(row) for row in warehouse_rows}
chemical_map = {row[0]: format_chemical_label(row) for row in chemical_rows}

tab1, tab2, tab3, tab4 = st.tabs(
    ["Create Stock Document", "View / Search Documents", "Edit Documents and Items", "Delete Document"]
)

# ---------------------------------------------------------
# Tab 1: Create Stock Document
# ---------------------------------------------------------
with tab1:
    st.subheader("Create Stock Document")

    if not warehouse_rows:
        st.warning("Please add warehouse records first.")
    elif not chemical_rows:
        st.warning("Please add chemical records first.")
    else:
        col1, col2 = st.columns(2)

        with col1:
            create_doc_no = st.text_input("Document Number *", key="create_doc_no")
            create_doc_type = st.selectbox("Document Type *", DOC_TYPES, key="create_doc_type")
            create_warehouse_id = st.selectbox(
                "Warehouse *",
                options=list(warehouse_map.keys()),
                format_func=lambda x: warehouse_map[x],
                key="create_warehouse_id"
            )
            create_operator_name = st.text_input("Operator Name *", key="create_operator_name")

        with col2:
            create_doc_date = st.date_input("Transaction Date *", key="create_doc_date")
            create_doc_time = st.time_input("Transaction Time *", key="create_doc_time")
            create_counterparty_name = st.text_input("Counterparty Name", key="create_counterparty_name")
            create_notes = st.text_area("Notes", key="create_notes")

        transaction_timestamp = build_timestamp(create_doc_date, create_doc_time)

        st.divider()
        st.subheader("Add Item Lines")

        current_location_rows = load_locations_by_warehouse(create_warehouse_id)
        current_location_map = {row[0]: format_location_label(row) for row in current_location_rows}

        if not current_location_rows:
            st.warning("The selected warehouse has no active storage locations.")
        else:
            item_col1, item_col2 = st.columns(2)

            with item_col1:
                create_item_chemical_id = st.selectbox(
                    "Chemical *",
                    options=list(chemical_map.keys()),
                    format_func=lambda x: chemical_map[x],
                    key="create_item_chemical_id"
                )
                create_item_location_id = st.selectbox(
                    "Storage Location *",
                    options=list(current_location_map.keys()),
                    format_func=lambda x: current_location_map[x],
                    key="create_item_location_id"
                )
                create_item_batch_no = st.text_input("Batch No", key="create_item_batch_no")
                use_manufacture_date = st.checkbox("Provide Manufacture Date", key="use_manufacture_date")

            with item_col2:
                if use_manufacture_date:
                    create_item_manufacture_date = st.date_input(
                        "Manufacture Date",
                        key="create_item_manufacture_date"
                    )
                else:
                    create_item_manufacture_date = None

                use_expiry_date = st.checkbox("Provide Expiry Date", key="use_expiry_date")
                if use_expiry_date:
                    create_item_expiry_date = st.date_input(
                        "Expiry Date",
                        key="create_item_expiry_date"
                    )
                else:
                    create_item_expiry_date = None

                create_item_quantity = st.number_input(
                    "Quantity *",
                    min_value=0.01,
                    value=1.00,
                    step=0.01,
                    key="create_item_quantity"
                )
                create_item_unit_price = st.number_input(
                    "Unit Price",
                    min_value=0.0,
                    value=0.0,
                    step=0.01,
                    key="create_item_unit_price"
                )

            if st.button("Add Item Line", key="add_item_line_button"):
                item_errors = validate_stock_document_item(
                    create_item_chemical_id,
                    create_item_location_id,
                    create_item_quantity,
                    create_item_unit_price,
                    create_item_manufacture_date,
                    create_item_expiry_date,
                )

                if not location_belongs_to_warehouse(create_item_location_id, create_warehouse_id):
                    item_errors.append("Selected location does not belong to the selected warehouse.")

                if create_doc_type == "OUTBOUND":
                    available_stock = get_available_stock(
                        create_item_chemical_id,
                        create_item_location_id,
                        create_item_batch_no,
                    )
                    reserved_in_draft = get_reserved_outbound_quantity_from_draft(
                        st.session_state["draft_stock_items"],
                        create_item_chemical_id,
                        create_item_location_id,
                        create_item_batch_no,
                    )
                    remaining_available = available_stock - reserved_in_draft
                    add_outbound_stock_error(item_errors, create_item_quantity, remaining_available)

                if item_errors:
                    show_validation_errors(item_errors)
                else:
                    new_item = {
                        "chemical_id": create_item_chemical_id,
                        "chemical_label": chemical_map[create_item_chemical_id],
                        "location_id": create_item_location_id,
                        "location_label": current_location_map[create_item_location_id],
                        "batch_no": clean_text(create_item_batch_no),
                        "manufacture_date": create_item_manufacture_date,
                        "expiry_date": create_item_expiry_date,
                        "quantity": float(create_item_quantity),
                        "unit_price": float(create_item_unit_price),
                    }
                    st.session_state["draft_stock_items"].append(new_item)
                    st.success("Item line added to the draft document.")

        st.subheader("Draft Item Lines")

        if st.session_state["draft_stock_items"]:
            draft_display = []
            for index, item in enumerate(st.session_state["draft_stock_items"], start=1):
                draft_display.append({
                    "Line No": index,
                    "Chemical": item["chemical_label"],
                    "Location": item["location_label"],
                    "Batch No": item["batch_no"] or "",
                    "Manufacture Date": item["manufacture_date"],
                    "Expiry Date": item["expiry_date"],
                    "Quantity": item["quantity"],
                    "Unit Price": item["unit_price"],
                })
            st.dataframe(draft_display, use_container_width=True)

            remove_options = list(range(len(st.session_state["draft_stock_items"])))
            selected_remove_index = st.selectbox(
                "Select draft line to remove",
                options=remove_options,
                format_func=lambda x: f"Line {x + 1}",
                key="selected_remove_index"
            )

            if st.button("Remove Selected Draft Line", key="remove_draft_line_button"):
                st.session_state["draft_stock_items"].pop(selected_remove_index)
                st.success("Draft line removed.")
                st.rerun()
        else:
            st.info("No draft item lines added yet.")

        st.divider()

        create_document_errors = []

        if st.button("Save Stock Document", key="save_stock_document_button"):
            create_document_errors = validate_stock_document_header(
                create_doc_no,
                create_doc_type,
                create_warehouse_id,
                create_operator_name,
            )

            cleaned_doc_no = clean_text(create_doc_no)

            if cleaned_doc_no and document_no_exists(cleaned_doc_no):
                add_unique_error(create_document_errors, True, "Document number")

            if len(st.session_state["draft_stock_items"]) == 0:
                create_document_errors.append("At least one item line is required before saving the document.")

            if create_doc_type == "OUTBOUND":
                draft_consumed = {}
                for item in st.session_state["draft_stock_items"]:
                    batch_value = clean_text(item["batch_no"]) or ""
                    stock_key = (item["chemical_id"], item["location_id"], batch_value)

                    db_available = get_available_stock(
                        item["chemical_id"],
                        item["location_id"],
                        item["batch_no"]
                    )
                    already_reserved = draft_consumed.get(stock_key, 0.0)
                    remaining = db_available - already_reserved

                    if item["quantity"] > remaining:
                        create_document_errors.append(
                            f"Outbound stock is not enough for {item['chemical_label']} at "
                            f"{item['location_label']} (batch: {batch_value or 'N/A'}). "
                            f"Available stock: {remaining}."
                        )

                    draft_consumed[stock_key] = already_reserved + item["quantity"]

            if create_document_errors:
                show_validation_errors(create_document_errors)
            else:
                header_data = {
                    "doc_no": cleaned_doc_no,
                    "doc_type": create_doc_type,
                    "warehouse_id": create_warehouse_id,
                    "transaction_date": transaction_timestamp,
                    "operator_name": clean_text(create_operator_name),
                    "counterparty_name": clean_text(create_counterparty_name),
                    "notes": clean_text(create_notes),
                }

                success, result = create_document_with_items(
                    header_data,
                    st.session_state["draft_stock_items"]
                )

                if success:
                    st.session_state["draft_stock_items"] = []
                    st.success("Stock document created successfully.")
                    st.rerun()
                else:
                    st.error(result)

# ---------------------------------------------------------
# Tab 2: View / Search Documents
# ---------------------------------------------------------
with tab2:
    st.subheader("Search and View Stock Documents")

    filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)

    with filter_col1:
        search_doc_no = st.text_input("Document Number", key="search_doc_no")

    with filter_col2:
        search_doc_type = st.selectbox(
            "Document Type",
            options=[""] + DOC_TYPES,
            format_func=lambda x: "-- All Types --" if x == "" else x,
            key="search_doc_type"
        )

    with filter_col3:
        warehouse_filter_options = [None] + list(warehouse_map.keys())
        search_warehouse_id = st.selectbox(
            "Warehouse",
            options=warehouse_filter_options,
            format_func=lambda x: "-- All Warehouses --" if x is None else warehouse_map[x],
            key="search_warehouse_id"
        )

    with filter_col4:
        search_start_date = st.date_input("Start Date", value=None, key="search_start_date")

    search_end_date = st.date_input("End Date", value=None, key="search_end_date")

    document_rows, document_error = load_stock_documents(
        doc_no_filter=search_doc_no,
        doc_type_filter=search_doc_type,
        warehouse_filter=search_warehouse_id,
        start_date=search_start_date,
        end_date=search_end_date,
    )

    if document_error:
        st.error(f"Unable to load stock documents. {document_error}")
    else:
        if document_rows:
            display_docs = []
            document_option_map = {}

            for row in document_rows:
                document_option_map[row[0]] = f"{row[1]} - {row[2]} - {row[3]}"
                display_docs.append({
                    "ID": row[0],
                    "Document No": row[1],
                    "Type": row[2],
                    "Warehouse": row[3],
                    "Transaction Date": row[4],
                    "Operator": row[5],
                    "Counterparty": row[6],
                    "Notes": row[7],
                    "Item Count": row[8],
                    "Total Quantity": format_decimal(row[9]),
                })

            st.dataframe(display_docs, use_container_width=True)

            selected_view_document_id = st.selectbox(
                "Select a document to view item lines",
                options=list(document_option_map.keys()),
                format_func=lambda x: document_option_map[x],
                key="selected_view_document_id"
            )

            item_rows, item_error = load_document_items(selected_view_document_id)

            if item_error:
                st.error(f"Unable to load item lines. {item_error}")
            else:
                st.subheader("Document Item Lines")
                if item_rows:
                    display_items = []
                    for row in item_rows:
                        display_items.append({
                            "Item ID": row[0],
                            "SKU": row[1],
                            "Chemical Name": row[2],
                            "Location": row[3],
                            "Batch No": row[4],
                            "Manufacture Date": row[5],
                            "Expiry Date": row[6],
                            "Quantity": format_decimal(row[7]),
                            "Unit Price": format_decimal(row[8]),
                        })
                    st.dataframe(display_items, use_container_width=True)
                else:
                    st.info("This document has no item lines.")
        else:
            st.warning("No stock documents matched the current filters.")

# ---------------------------------------------------------
# Tab 3: Edit Documents and Items
# ---------------------------------------------------------
with tab3:
    st.subheader("Edit Document Header and Item Lines")

    all_documents, all_documents_error = load_all_documents()

    if all_documents_error:
        st.error(f"Unable to load documents. {all_documents_error}")
    elif not all_documents:
        st.info("No stock documents are available to edit.")
    else:
        edit_document_options = {
            row[0]: f"{row[1]} - {row[2]} - {row[3]} - {row[4]}"
            for row in all_documents
        }

        selected_edit_document_id = st.selectbox(
            "Select Document",
            options=list(edit_document_options.keys()),
            format_func=lambda x: edit_document_options[x],
            key="selected_edit_document_id"
        )

        edit_document_row, edit_document_error = get_document_by_id(selected_edit_document_id)

        if edit_document_error:
            st.error(f"Unable to load the selected document. {edit_document_error}")
        elif edit_document_row:
            st.subheader("Edit Document Header")

            with st.form("edit_document_header_form"):
                edit_col1, edit_col2 = st.columns(2)

                with edit_col1:
                    edit_doc_no = st.text_input("Document Number *", value=edit_document_row[1])
                    edit_doc_type = st.selectbox(
                        "Document Type *",
                        DOC_TYPES,
                        index=DOC_TYPES.index(edit_document_row[2])
                    )
                    edit_warehouse_id = st.selectbox(
                        "Warehouse *",
                        options=list(warehouse_map.keys()),
                        index=list(warehouse_map.keys()).index(edit_document_row[3]),
                        format_func=lambda x: warehouse_map[x]
                    )

                with edit_col2:
                    current_dt = edit_document_row[4]
                    edit_doc_date = st.date_input("Transaction Date *", value=current_dt.date())
                    edit_doc_time = st.time_input("Transaction Time *", value=current_dt.time())
                    edit_operator_name = st.text_input("Operator Name *", value=edit_document_row[5])

                edit_counterparty_name = st.text_input(
                    "Counterparty Name",
                    value=edit_document_row[6] or ""
                )
                edit_notes = st.text_area("Notes", value=edit_document_row[7] or "")

                update_header_submitted = st.form_submit_button("Update Document Header")

                if update_header_submitted:
                    header_errors = validate_stock_document_header(
                        edit_doc_no,
                        edit_doc_type,
                        edit_warehouse_id,
                        edit_operator_name
                    )

                    cleaned_edit_doc_no = clean_text(edit_doc_no)
                    if cleaned_edit_doc_no and document_no_exists(
                        cleaned_edit_doc_no,
                        exclude_id=selected_edit_document_id
                    ):
                        add_unique_error(header_errors, True, "Document number")

                    item_rows_for_header_check, _ = load_document_items(selected_edit_document_id)
                    if item_rows_for_header_check:
                        for item_row in item_rows_for_header_check:
                            item_location_id = item_row[10]
                            if not location_belongs_to_warehouse(item_location_id, edit_warehouse_id):
                                header_errors.append(
                                    "The selected warehouse does not match one or more existing item locations. "
                                    "Please edit or remove those item lines first."
                                )
                                break

                    if header_errors:
                        show_validation_errors(header_errors)
                    else:
                        update_query = """
                            UPDATE stock_documents
                            SET
                                doc_no = %s,
                                doc_type = %s,
                                warehouse_id = %s,
                                transaction_date = %s,
                                operator_name = %s,
                                counterparty_name = %s,
                                notes = %s
                            WHERE id = %s;
                        """

                        params = (
                            cleaned_edit_doc_no,
                            edit_doc_type,
                            edit_warehouse_id,
                            build_timestamp(edit_doc_date, edit_doc_time),
                            clean_text(edit_operator_name),
                            clean_text(edit_counterparty_name),
                            clean_text(edit_notes),
                            selected_edit_document_id
                        )

                        success, result = run_action(update_query, params=params)

                        if success:
                            st.success("Document header updated successfully.")
                            st.rerun()
                        else:
                            st.error(result)

            st.divider()
            st.subheader("Current Item Lines")

            current_item_rows, current_item_error = load_document_items(selected_edit_document_id)

            if current_item_error:
                st.error(f"Unable to load document item lines. {current_item_error}")
            else:
                if current_item_rows:
                    current_item_display = []
                    for row in current_item_rows:
                        current_item_display.append({
                            "Item ID": row[0],
                            "SKU": row[1],
                            "Chemical Name": row[2],
                            "Location": row[3],
                            "Batch No": row[4],
                            "Manufacture Date": row[5],
                            "Expiry Date": row[6],
                            "Quantity": format_decimal(row[7]),
                            "Unit Price": format_decimal(row[8]),
                        })
                    st.dataframe(current_item_display, use_container_width=True)
                else:
                    st.info("No item lines found for this document.")

            edit_doc_type_value = edit_document_row[2]
            edit_warehouse_id_value = edit_document_row[3]
            edit_location_rows = load_locations_by_warehouse(edit_warehouse_id_value)
            edit_location_map = {row[0]: format_location_label(row) for row in edit_location_rows}

            st.divider()
            st.subheader("Add New Item to This Document")

            if not edit_location_rows:
                st.warning("This document's warehouse has no active storage locations.")
            else:
                add_item_col1, add_item_col2 = st.columns(2)

                with add_item_col1:
                    add_item_chemical_id = st.selectbox(
                        "Chemical *",
                        options=list(chemical_map.keys()),
                        format_func=lambda x: chemical_map[x],
                        key="add_item_chemical_id_existing_doc"
                    )
                    add_item_location_id = st.selectbox(
                        "Location *",
                        options=list(edit_location_map.keys()),
                        format_func=lambda x: edit_location_map[x],
                        key="add_item_location_id_existing_doc"
                    )
                    add_item_batch_no = st.text_input("Batch No", key="add_item_batch_no_existing_doc")

                with add_item_col2:
                    add_use_manufacture_date = st.checkbox(
                        "Provide Manufacture Date",
                        key="add_use_manufacture_date_existing_doc"
                    )
                    if add_use_manufacture_date:
                        add_item_manufacture_date = st.date_input(
                            "Manufacture Date",
                            key="add_item_manufacture_date_existing_doc"
                        )
                    else:
                        add_item_manufacture_date = None

                    add_use_expiry_date = st.checkbox(
                        "Provide Expiry Date",
                        key="add_use_expiry_date_existing_doc"
                    )
                    if add_use_expiry_date:
                        add_item_expiry_date = st.date_input(
                            "Expiry Date",
                            key="add_item_expiry_date_existing_doc"
                        )
                    else:
                        add_item_expiry_date = None

                    add_item_quantity = st.number_input(
                        "Quantity *",
                        min_value=0.01,
                        value=1.00,
                        step=0.01,
                        key="add_item_quantity_existing_doc"
                    )
                    add_item_unit_price = st.number_input(
                        "Unit Price",
                        min_value=0.0,
                        value=0.0,
                        step=0.01,
                        key="add_item_unit_price_existing_doc"
                    )

                if st.button("Add Item to Document", key="add_item_to_existing_document_button"):
                    add_item_errors = validate_stock_document_item(
                        add_item_chemical_id,
                        add_item_location_id,
                        add_item_quantity,
                        add_item_unit_price,
                        add_item_manufacture_date,
                        add_item_expiry_date,
                    )

                    if not location_belongs_to_warehouse(add_item_location_id, edit_warehouse_id_value):
                        add_item_errors.append("Selected location does not belong to the document warehouse.")

                    if edit_doc_type_value == "OUTBOUND":
                        available_stock = get_available_stock(
                            add_item_chemical_id,
                            add_item_location_id,
                            add_item_batch_no,
                        )
                        add_outbound_stock_error(add_item_errors, add_item_quantity, available_stock)

                    if add_item_errors:
                        show_validation_errors(add_item_errors)
                    else:
                        insert_query = """
                            INSERT INTO stock_document_items
                            (
                                document_id,
                                chemical_id,
                                location_id,
                                batch_no,
                                manufacture_date,
                                expiry_date,
                                quantity,
                                unit_price
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                        """

                        params = (
                            selected_edit_document_id,
                            add_item_chemical_id,
                            add_item_location_id,
                            clean_text(add_item_batch_no),
                            add_item_manufacture_date,
                            add_item_expiry_date,
                            add_item_quantity,
                            add_item_unit_price
                        )

                        success, result = run_action(insert_query, params=params)

                        if success:
                            st.success("Item line added successfully.")
                            st.rerun()
                        else:
                            st.error(result)

            if current_item_rows:
                st.divider()
                st.subheader("Edit Existing Item Line")

                edit_item_options = {
                    row[0]: f"Item {row[0]} - {row[1]} - {row[2]} - {row[3]}"
                    for row in current_item_rows
                }

                selected_edit_item_id = st.selectbox(
                    "Select Item Line",
                    options=list(edit_item_options.keys()),
                    format_func=lambda x: edit_item_options[x],
                    key="selected_edit_item_id"
                )

                edit_item_row, edit_item_error = get_document_item_by_id(selected_edit_item_id)

                if edit_item_error:
                    st.error(f"Unable to load the selected item line. {edit_item_error}")
                elif edit_item_row:
                    with st.form("edit_existing_item_form"):
                        item_edit_col1, item_edit_col2 = st.columns(2)

                        with item_edit_col1:
                            edit_item_chemical_id = st.selectbox(
                                "Chemical *",
                                options=list(chemical_map.keys()),
                                index=list(chemical_map.keys()).index(edit_item_row[2]),
                                format_func=lambda x: chemical_map[x]
                            )
                            edit_item_location_id = st.selectbox(
                                "Location *",
                                options=list(edit_location_map.keys()),
                                index=list(edit_location_map.keys()).index(edit_item_row[3]),
                                format_func=lambda x: edit_location_map[x]
                            )
                            edit_item_batch_no = st.text_input("Batch No", value=edit_item_row[4] or "")

                        with item_edit_col2:
                            edit_item_use_mfg = st.checkbox(
                                "Provide Manufacture Date",
                                value=edit_item_row[5] is not None
                            )
                            if edit_item_use_mfg:
                                edit_item_manufacture_date = st.date_input(
                                    "Manufacture Date",
                                    value=edit_item_row[5] if edit_item_row[5] else datetime.today()
                                )
                            else:
                                edit_item_manufacture_date = None

                            edit_item_use_expiry = st.checkbox(
                                "Provide Expiry Date",
                                value=edit_item_row[6] is not None
                            )
                            if edit_item_use_expiry:
                                edit_item_expiry_date = st.date_input(
                                    "Expiry Date",
                                    value=edit_item_row[6] if edit_item_row[6] else datetime.today()
                                )
                            else:
                                edit_item_expiry_date = None

                            edit_item_quantity = st.number_input(
                                "Quantity *",
                                min_value=0.01,
                                value=float(edit_item_row[7]),
                                step=0.01
                            )
                            edit_item_unit_price = st.number_input(
                                "Unit Price",
                                min_value=0.0,
                                value=float(edit_item_row[8]),
                                step=0.01
                            )

                        update_item_submitted = st.form_submit_button("Update Item Line")

                        if update_item_submitted:
                            item_errors = validate_stock_document_item(
                                edit_item_chemical_id,
                                edit_item_location_id,
                                edit_item_quantity,
                                edit_item_unit_price,
                                edit_item_manufacture_date,
                                edit_item_expiry_date,
                            )

                            if not location_belongs_to_warehouse(edit_item_location_id, edit_warehouse_id_value):
                                item_errors.append("Selected location does not belong to the document warehouse.")

                            if edit_doc_type_value == "OUTBOUND":
                                available_stock = get_available_stock(
                                    edit_item_chemical_id,
                                    edit_item_location_id,
                                    edit_item_batch_no,
                                )

                                same_combination = (
                                    edit_item_row[2] == edit_item_chemical_id
                                    and edit_item_row[3] == edit_item_location_id
                                    and (clean_text(edit_item_row[4]) or "") == (clean_text(edit_item_batch_no) or "")
                                )

                                allowed_available = available_stock
                                if same_combination:
                                    allowed_available += float(edit_item_row[7])

                                add_outbound_stock_error(item_errors, edit_item_quantity, allowed_available)

                            if item_errors:
                                show_validation_errors(item_errors)
                            else:
                                update_item_query = """
                                    UPDATE stock_document_items
                                    SET
                                        chemical_id = %s,
                                        location_id = %s,
                                        batch_no = %s,
                                        manufacture_date = %s,
                                        expiry_date = %s,
                                        quantity = %s,
                                        unit_price = %s
                                    WHERE id = %s;
                                """

                                params = (
                                    edit_item_chemical_id,
                                    edit_item_location_id,
                                    clean_text(edit_item_batch_no),
                                    edit_item_manufacture_date,
                                    edit_item_expiry_date,
                                    edit_item_quantity,
                                    edit_item_unit_price,
                                    selected_edit_item_id
                                )

                                success, result = run_action(update_item_query, params=params)

                                if success:
                                    st.success("Item line updated successfully.")
                                    st.rerun()
                                else:
                                    st.error(result)

                st.divider()
                st.subheader("Delete Item Line")

                confirm_delete_item = st.checkbox(
                    "I confirm that I want to delete the selected item line.",
                    key="confirm_delete_item_line"
                )

                if st.button("Delete Selected Item Line", key="delete_selected_item_line_button"):
                    if not confirm_delete_item:
                        st.error("Please confirm deletion before deleting the item line.")
                    else:
                        delete_item_query = """
                            DELETE FROM stock_document_items
                            WHERE id = %s;
                        """
                        success, result = run_action(delete_item_query, params=(selected_edit_item_id,))

                        if success:
                            if result > 0:
                                st.success("Item line deleted successfully.")
                                st.rerun()
                            else:
                                st.warning("No item line was deleted.")
                        else:
                            st.error(result)

# ---------------------------------------------------------
# Tab 4: Delete Document
# ---------------------------------------------------------
with tab4:
    st.subheader("Delete Stock Document")
    st.warning("Deleting a stock document will also delete all of its item lines.")

    delete_documents, delete_documents_error = load_all_documents()

    if delete_documents_error:
        st.error(f"Unable to load documents. {delete_documents_error}")
    elif not delete_documents:
        st.info("No stock documents are available to delete.")
    else:
        delete_document_options = {
            row[0]: f"{row[1]} - {row[2]} - {row[3]} - {row[4]}"
            for row in delete_documents
        }

        selected_delete_document_id = st.selectbox(
            "Select Document to Delete",
            options=list(delete_document_options.keys()),
            format_func=lambda x: delete_document_options[x],
            key="selected_delete_document_id"
        )

        delete_document_row, delete_document_error = get_document_by_id(selected_delete_document_id)

        if delete_document_error:
            st.error(f"Unable to load document details. {delete_document_error}")
        elif delete_document_row:
            st.write(f"**Document Number:** {delete_document_row[1]}")
            st.write(f"**Document Type:** {delete_document_row[2]}")
            st.write(f"**Warehouse ID:** {delete_document_row[3]}")
            st.write(f"**Transaction Date:** {delete_document_row[4]}")
            st.write(f"**Operator Name:** {delete_document_row[5]}")
            st.write(f"**Counterparty Name:** {delete_document_row[6] or ''}")

            confirm_delete_document = st.checkbox(
                "I confirm that I want to delete this stock document.",
                key="confirm_delete_document"
            )

            if st.button("Delete Stock Document", key="delete_stock_document_button"):
                if not confirm_delete_document:
                    st.error("Please confirm deletion before deleting the stock document.")
                else:
                    delete_query = """
                        DELETE FROM stock_documents
                        WHERE id = %s;
                    """
                    success, result = run_action(delete_query, params=(selected_delete_document_id,))

                    if success:
                        if result > 0:
                            st.success("Stock document deleted successfully.")
                            st.rerun()
                        else:
                            st.warning("No stock document was deleted.")
                    else:
                        st.error(result)