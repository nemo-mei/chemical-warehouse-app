import streamlit as st
from datetime import date
from db import run_select, run_action, get_lookup_options, get_connection
from validation import validate_stocktake_session, validate_stocktake_item


STATUSES = ["OPEN", "COMPLETED"]


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
    Display all validation errors together.
    """
    for error in errors:
        st.error(error)


def format_decimal(value):
    """
    Format numeric value for display.
    """
    if value is None:
        return 0.0
    return float(value)


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
    Load active locations for the selected warehouse.
    """
    query = """
        SELECT id, location_code, location_type
        FROM storage_locations
        WHERE warehouse_id = %s
          AND is_active = TRUE
        ORDER BY location_code;
    """
    return get_lookup_options(query, params=(warehouse_id,))


def load_sessions():
    """
    Load all stocktake sessions for dropdowns.
    """
    query = """
        SELECT
            ss.id,
            ss.session_name,
            w.warehouse_name,
            ss.planned_date,
            ss.status
        FROM stocktake_sessions ss
        JOIN warehouses w ON ss.warehouse_id = w.id
        ORDER BY ss.planned_date DESC, ss.id DESC;
    """
    success, result = run_select(query)
    if not success:
        return None, result
    return result, None


def load_stocktake_sessions(
    warehouse_id=None,
    status_filter="",
    planned_date_from=None,
    planned_date_to=None
):
    """
    Load stocktake session history with optional filters.
    """
    query = """
        SELECT
            ss.id,
            ss.session_name,
            w.warehouse_name,
            ss.planned_date,
            ss.completed_date,
            ss.status,
            ss.operator_name,
            COALESCE(ss.notes, '') AS notes,
            COUNT(si.id) AS item_count
        FROM stocktake_sessions ss
        JOIN warehouses w ON ss.warehouse_id = w.id
        LEFT JOIN stocktake_items si ON ss.id = si.session_id
        WHERE (%s IS NULL OR ss.warehouse_id = %s)
          AND (%s = '' OR ss.status = %s)
          AND (%s IS NULL OR ss.planned_date >= %s)
          AND (%s IS NULL OR ss.planned_date <= %s)
        GROUP BY
            ss.id,
            ss.session_name,
            w.warehouse_name,
            ss.planned_date,
            ss.completed_date,
            ss.status,
            ss.operator_name,
            ss.notes
        ORDER BY ss.planned_date DESC, ss.id DESC;
    """

    params = (
        warehouse_id,
        warehouse_id,
        status_filter,
        status_filter,
        planned_date_from,
        planned_date_from,
        planned_date_to,
        planned_date_to
    )

    success, result = run_select(query, params=params)
    if not success:
        return None, result
    return result, None


def load_stocktake_items(session_id):
    """
    Load item lines for one stocktake session.
    """
    query = """
        SELECT
            si.id,
            c.sku,
            c.chemical_name,
            sl.location_code,
            COALESCE(si.batch_no, '') AS batch_no,
            si.system_quantity,
            si.counted_quantity,
            (si.counted_quantity - si.system_quantity) AS variance,
            c.id AS chemical_id,
            sl.id AS location_id
        FROM stocktake_items si
        JOIN chemicals c ON si.chemical_id = c.id
        JOIN storage_locations sl ON si.location_id = sl.id
        WHERE si.session_id = %s
        ORDER BY si.id;
    """
    success, result = run_select(query, params=(session_id,))
    if not success:
        return None, result
    return result, None


def get_session_by_id(session_id):
    """
    Load one stocktake session by ID.
    """
    query = """
        SELECT
            id,
            session_name,
            warehouse_id,
            planned_date,
            completed_date,
            status,
            operator_name,
            notes
        FROM stocktake_sessions
        WHERE id = %s;
    """
    success, result = run_select(query, params=(session_id,), fetchone=True)
    if not success:
        return None, result
    return result, None


def get_stocktake_item_by_id(item_id):
    """
    Load one stocktake item by ID.
    """
    query = """
        SELECT
            id,
            session_id,
            chemical_id,
            location_id,
            batch_no,
            system_quantity,
            counted_quantity
        FROM stocktake_items
        WHERE id = %s;
    """
    success, result = run_select(query, params=(item_id,), fetchone=True)
    if not success:
        return None, result
    return result, None


def location_belongs_to_warehouse(location_id, warehouse_id):
    """
    Check whether a location belongs to the selected warehouse.
    """
    query = """
        SELECT 1
        FROM storage_locations
        WHERE id = %s
          AND warehouse_id = %s;
    """
    success, result = run_select(query, params=(location_id, warehouse_id), fetchone=True)
    if not success:
        return False
    return result is not None


def get_system_quantity(chemical_id, location_id, batch_no=None):
    """
    Calculate current system quantity from stock transactions.
    INBOUND adds quantity and OUTBOUND subtracts quantity.
    """
    query = """
        SELECT COALESCE(SUM(
            CASE
                WHEN sd.doc_type = 'INBOUND' THEN sdi.quantity
                WHEN sd.doc_type = 'OUTBOUND' THEN -sdi.quantity
                ELSE 0
            END
        ), 0) AS system_quantity
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
        return 0.0
    return float(result[0])


def create_session_with_items(session_data, item_lines):
    """
    Create one stocktake session and its item lines in a single transaction.
    """
    conn = None
    cur = None

    try:
        conn = get_connection()
        cur = conn.cursor()

        session_query = """
            INSERT INTO stocktake_sessions
            (
                session_name,
                warehouse_id,
                planned_date,
                completed_date,
                status,
                operator_name,
                notes
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """

        cur.execute(
            session_query,
            (
                session_data["session_name"],
                session_data["warehouse_id"],
                session_data["planned_date"],
                session_data["completed_date"],
                session_data["status"],
                session_data["operator_name"],
                session_data["notes"],
            )
        )

        session_id = cur.fetchone()[0]

        item_query = """
            INSERT INTO stocktake_items
            (
                session_id,
                chemical_id,
                location_id,
                batch_no,
                system_quantity,
                counted_quantity
            )
            VALUES (%s, %s, %s, %s, %s, %s);
        """

        for item in item_lines:
            cur.execute(
                item_query,
                (
                    session_id,
                    item["chemical_id"],
                    item["location_id"],
                    clean_text(item["batch_no"]),
                    item["system_quantity"],
                    item["counted_quantity"],
                )
            )

        conn.commit()
        return True, session_id

    except Exception:
        if conn is not None:
            conn.rollback()
        return False, "Database error while creating the stocktake session."

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


def variance_label(variance):
    """
    Build a readable variance label.
    """
    if variance > 0:
        return "Surplus"
    if variance < 0:
        return "Shortage"
    return "Match"


if "draft_stocktake_items" not in st.session_state:
    st.session_state["draft_stocktake_items"] = []


st.title("Stocktake Management")
st.write("Create stocktake sessions, record counted quantities, and compare them with system quantities.")

warehouse_rows = load_warehouses()
chemical_rows = load_chemicals()

warehouse_map = {row[0]: format_warehouse_label(row) for row in warehouse_rows}
chemical_map = {row[0]: format_chemical_label(row) for row in chemical_rows}

tab1, tab2, tab3, tab4 = st.tabs(
    ["Create Stocktake Session", "View Stocktake History", "Edit Session and Items", "Delete Session"]
)

# ---------------------------------------------------------
# Tab 1: Create Stocktake Session
# ---------------------------------------------------------
with tab1:
    st.subheader("Create Stocktake Session")

    if not warehouse_rows:
        st.warning("Please add warehouse records first.")
    elif not chemical_rows:
        st.warning("Please add chemical records first.")
    else:
        col1, col2 = st.columns(2)

        with col1:
            create_session_name = st.text_input("Session Name *", key="create_session_name")
            create_warehouse_id = st.selectbox(
                "Warehouse *",
                options=list(warehouse_map.keys()),
                format_func=lambda x: warehouse_map[x],
                key="create_stocktake_warehouse_id"
            )
            create_planned_date = st.date_input(
                "Planned Date *",
                value=date.today(),
                key="create_planned_date"
            )

        with col2:
            create_status = st.selectbox("Status *", STATUSES, key="create_stocktake_status")
            create_operator_name = st.text_input("Operator Name *", key="create_stocktake_operator_name")
            create_notes = st.text_area("Notes", key="create_stocktake_notes")

        create_completed_date = None
        if create_status == "COMPLETED":
            create_completed_date = st.date_input(
                "Completed Date",
                value=date.today(),
                key="create_completed_date"
            )

        st.divider()
        st.subheader("Add Stocktake Item Lines")

        location_rows = load_locations_by_warehouse(create_warehouse_id)
        location_map = {row[0]: format_location_label(row) for row in location_rows}

        if not location_rows:
            st.warning("The selected warehouse has no active storage locations.")
        else:
            item_col1, item_col2 = st.columns(2)

            with item_col1:
                create_item_chemical_id = st.selectbox(
                    "Chemical *",
                    options=list(chemical_map.keys()),
                    format_func=lambda x: chemical_map[x],
                    key="create_stocktake_item_chemical_id"
                )
                create_item_location_id = st.selectbox(
                    "Storage Location *",
                    options=list(location_map.keys()),
                    format_func=lambda x: location_map[x],
                    key="create_stocktake_item_location_id"
                )
                create_item_batch_no = st.text_input("Batch No", key="create_stocktake_item_batch_no")

            with item_col2:
                current_system_quantity = get_system_quantity(
                    create_item_chemical_id,
                    create_item_location_id,
                    create_item_batch_no
                )
                st.number_input(
                    "System Quantity",
                    value=float(current_system_quantity),
                    step=0.01,
                    disabled=True,
                    key="display_create_system_quantity"
                )
                create_item_counted_quantity = st.number_input(
                    "Counted Quantity *",
                    min_value=0.0,
                    value=0.0,
                    step=0.01,
                    key="create_stocktake_item_counted_quantity"
                )
                variance_preview = float(create_item_counted_quantity) - float(current_system_quantity)
                st.number_input(
                    "Variance Preview",
                    value=float(variance_preview),
                    step=0.01,
                    disabled=True,
                    key="display_create_variance_preview"
                )

            if st.button("Add Stocktake Item Line", key="add_stocktake_item_button"):
                item_errors = validate_stocktake_item(
                    create_item_chemical_id,
                    create_item_location_id,
                    current_system_quantity,
                    create_item_counted_quantity
                )

                if not location_belongs_to_warehouse(create_item_location_id, create_warehouse_id):
                    item_errors.append("Selected location does not belong to the selected warehouse.")

                if item_errors:
                    show_validation_errors(item_errors)
                else:
                    st.session_state["draft_stocktake_items"].append(
                        {
                            "chemical_id": create_item_chemical_id,
                            "chemical_label": chemical_map[create_item_chemical_id],
                            "location_id": create_item_location_id,
                            "location_label": location_map[create_item_location_id],
                            "batch_no": clean_text(create_item_batch_no),
                            "system_quantity": float(current_system_quantity),
                            "counted_quantity": float(create_item_counted_quantity),
                        }
                    )
                    st.success("Stocktake item line added to the draft session.")

        st.subheader("Draft Stocktake Item Lines")

        if st.session_state["draft_stocktake_items"]:
            draft_display = []
            for index, item in enumerate(st.session_state["draft_stocktake_items"], start=1):
                variance = float(item["counted_quantity"]) - float(item["system_quantity"])
                draft_display.append(
                    {
                        "Line No": index,
                        "Chemical": item["chemical_label"],
                        "Location": item["location_label"],
                        "Batch No": item["batch_no"] or "",
                        "System Quantity": item["system_quantity"],
                        "Counted Quantity": item["counted_quantity"],
                        "Variance": variance,
                        "Variance Type": variance_label(variance),
                    }
                )

            st.dataframe(draft_display, use_container_width=True)

            remove_options = list(range(len(st.session_state["draft_stocktake_items"])))
            selected_remove_index = st.selectbox(
                "Select draft line to remove",
                options=remove_options,
                format_func=lambda x: f"Line {x + 1}",
                key="selected_remove_stocktake_line_index"
            )

            if st.button("Remove Selected Draft Line", key="remove_stocktake_draft_line_button"):
                st.session_state["draft_stocktake_items"].pop(selected_remove_index)
                st.success("Draft stocktake line removed.")
                st.rerun()
        else:
            st.info("No draft stocktake item lines added yet.")

        st.divider()

        if st.button("Save Stocktake Session", key="save_stocktake_session_button"):
            session_errors = validate_stocktake_session(
                create_session_name,
                create_warehouse_id,
                create_planned_date,
                create_status,
                create_operator_name
            )

            if create_status == "COMPLETED" and create_completed_date is None:
                session_errors.append("Completed date is required when status is COMPLETED.")

            if create_status == "COMPLETED" and create_completed_date and create_completed_date < create_planned_date:
                session_errors.append("Completed date cannot be earlier than planned date.")

            if len(st.session_state["draft_stocktake_items"]) == 0:
                session_errors.append("At least one stocktake item line is required before saving.")

            if session_errors:
                show_validation_errors(session_errors)
            else:
                session_data = {
                    "session_name": clean_text(create_session_name),
                    "warehouse_id": create_warehouse_id,
                    "planned_date": create_planned_date,
                    "completed_date": create_completed_date,
                    "status": create_status,
                    "operator_name": clean_text(create_operator_name),
                    "notes": clean_text(create_notes),
                }

                success, result = create_session_with_items(
                    session_data,
                    st.session_state["draft_stocktake_items"]
                )

                if success:
                    st.session_state["draft_stocktake_items"] = []
                    st.success("Stocktake session created successfully.")
                    st.rerun()
                else:
                    st.error(result)

# ---------------------------------------------------------
# Tab 2: View Stocktake History
# ---------------------------------------------------------
with tab2:
    st.subheader("View Stocktake History")

    filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)

    warehouse_filter_options = [None] + list(warehouse_map.keys())

    with filter_col1:
        history_warehouse_id = st.selectbox(
            "Warehouse",
            options=warehouse_filter_options,
            format_func=lambda x: "-- All Warehouses --" if x is None else warehouse_map[x],
            key="history_warehouse_id"
        )

    with filter_col2:
        history_status = st.selectbox(
            "Status",
            options=[""] + STATUSES,
            format_func=lambda x: "-- All Statuses --" if x == "" else x,
            key="history_status"
        )

    with filter_col3:
        history_date_from = st.date_input(
            "Planned Date From",
            value=None,
            key="history_date_from"
        )

    with filter_col4:
        history_date_to = st.date_input(
            "Planned Date To",
            value=None,
            key="history_date_to"
        )

    session_rows, session_error = load_stocktake_sessions(
        warehouse_id=history_warehouse_id,
        status_filter=history_status,
        planned_date_from=history_date_from,
        planned_date_to=history_date_to
    )

    if session_error:
        st.error(f"Unable to load stocktake sessions. {session_error}")
    else:
        if session_rows:
            session_display = []
            session_option_map = {}

            for row in session_rows:
                session_option_map[row[0]] = f"{row[1]} - {row[2]} - {row[5]}"
                session_display.append(
                    {
                        "ID": row[0],
                        "Session Name": row[1],
                        "Warehouse": row[2],
                        "Planned Date": row[3],
                        "Completed Date": row[4],
                        "Status": row[5],
                        "Operator": row[6],
                        "Notes": row[7],
                        "Item Count": row[8],
                    }
                )

            st.dataframe(session_display, use_container_width=True)

            selected_view_session_id = st.selectbox(
                "Select a session to view item lines",
                options=list(session_option_map.keys()),
                format_func=lambda x: session_option_map[x],
                key="selected_view_session_id"
            )

            item_rows, item_error = load_stocktake_items(selected_view_session_id)

            if item_error:
                st.error(f"Unable to load stocktake item lines. {item_error}")
            else:
                st.subheader("Stocktake Item Lines")
                if item_rows:
                    item_display = []
                    for row in item_rows:
                        item_display.append(
                            {
                                "Item ID": row[0],
                                "SKU": row[1],
                                "Chemical Name": row[2],
                                "Location": row[3],
                                "Batch No": row[4],
                                "System Quantity": format_decimal(row[5]),
                                "Counted Quantity": format_decimal(row[6]),
                                "Variance": format_decimal(row[7]),
                                "Variance Type": variance_label(float(row[7])),
                            }
                        )
                    st.dataframe(item_display, use_container_width=True)
                else:
                    st.info("This stocktake session has no item lines.")
        else:
            st.warning("No stocktake sessions matched the current filters.")

# ---------------------------------------------------------
# Tab 3: Edit Session and Items
# ---------------------------------------------------------
with tab3:
    st.subheader("Edit Stocktake Session and Item Lines")

    all_sessions, all_sessions_error = load_sessions()

    if all_sessions_error:
        st.error(f"Unable to load stocktake sessions. {all_sessions_error}")
    elif not all_sessions:
        st.info("No stocktake sessions are available to edit.")
    else:
        edit_session_options = {
            row[0]: f"{row[1]} - {row[2]} - {row[3]} - {row[4]}"
            for row in all_sessions
        }

        selected_edit_session_id = st.selectbox(
            "Select Session",
            options=list(edit_session_options.keys()),
            format_func=lambda x: edit_session_options[x],
            key="selected_edit_stocktake_session_id"
        )

        session_record, session_record_error = get_session_by_id(selected_edit_session_id)

        if session_record_error:
            st.error(f"Unable to load the selected session. {session_record_error}")
        elif session_record:
            st.subheader("Edit Session Header")

            with st.form("edit_stocktake_session_form"):
                col1, col2 = st.columns(2)

                with col1:
                    edit_session_name = st.text_input("Session Name *", value=session_record[1])
                    edit_warehouse_id = st.selectbox(
                        "Warehouse *",
                        options=list(warehouse_map.keys()),
                        index=list(warehouse_map.keys()).index(session_record[2]),
                        format_func=lambda x: warehouse_map[x]
                    )
                    edit_planned_date = st.date_input("Planned Date *", value=session_record[3])

                with col2:
                    edit_status = st.selectbox(
                        "Status *",
                        options=STATUSES,
                        index=STATUSES.index(session_record[5])
                    )
                    edit_operator_name = st.text_input("Operator Name *", value=session_record[6])
                    edit_notes = st.text_area("Notes", value=session_record[7] or "")

                edit_completed_date = None
                if edit_status == "COMPLETED":
                    edit_completed_date = st.date_input(
                        "Completed Date",
                        value=session_record[4] if session_record[4] else date.today()
                    )

                update_session_submitted = st.form_submit_button("Update Session Header")

                if update_session_submitted:
                    session_errors = validate_stocktake_session(
                        edit_session_name,
                        edit_warehouse_id,
                        edit_planned_date,
                        edit_status,
                        edit_operator_name
                    )

                    if edit_status == "COMPLETED" and edit_completed_date is None:
                        session_errors.append("Completed date is required when status is COMPLETED.")

                    if edit_status == "COMPLETED" and edit_completed_date and edit_completed_date < edit_planned_date:
                        session_errors.append("Completed date cannot be earlier than planned date.")

                    existing_items, _ = load_stocktake_items(selected_edit_session_id)
                    if existing_items:
                        for row in existing_items:
                            if not location_belongs_to_warehouse(row[9], edit_warehouse_id):
                                session_errors.append(
                                    "The selected warehouse does not match one or more existing item locations. "
                                    "Please edit or remove those item lines first."
                                )
                                break

                    if session_errors:
                        show_validation_errors(session_errors)
                    else:
                        update_query = """
                            UPDATE stocktake_sessions
                            SET
                                session_name = %s,
                                warehouse_id = %s,
                                planned_date = %s,
                                completed_date = %s,
                                status = %s,
                                operator_name = %s,
                                notes = %s
                            WHERE id = %s;
                        """

                        params = (
                            clean_text(edit_session_name),
                            edit_warehouse_id,
                            edit_planned_date,
                            edit_completed_date,
                            edit_status,
                            clean_text(edit_operator_name),
                            clean_text(edit_notes),
                            selected_edit_session_id
                        )

                        success, result = run_action(update_query, params=params)

                        if success:
                            st.success("Stocktake session updated successfully.")
                            st.rerun()
                        else:
                            st.error(result)

            st.divider()
            st.subheader("Current Stocktake Item Lines")

            current_item_rows, current_item_error = load_stocktake_items(selected_edit_session_id)

            if current_item_error:
                st.error(f"Unable to load stocktake item lines. {current_item_error}")
            else:
                if current_item_rows:
                    current_item_display = []
                    for row in current_item_rows:
                        current_item_display.append(
                            {
                                "Item ID": row[0],
                                "SKU": row[1],
                                "Chemical Name": row[2],
                                "Location": row[3],
                                "Batch No": row[4],
                                "System Quantity": format_decimal(row[5]),
                                "Counted Quantity": format_decimal(row[6]),
                                "Variance": format_decimal(row[7]),
                                "Variance Type": variance_label(float(row[7])),
                            }
                        )
                    st.dataframe(current_item_display, use_container_width=True)
                else:
                    st.info("No item lines found for this session.")

            edit_session_warehouse_id = session_record[2]
            edit_location_rows = load_locations_by_warehouse(edit_session_warehouse_id)
            edit_location_map = {row[0]: format_location_label(row) for row in edit_location_rows}

            st.divider()
            st.subheader("Add New Item to This Session")

            if not edit_location_rows:
                st.warning("This session's warehouse has no active storage locations.")
            else:
                add_col1, add_col2 = st.columns(2)

                with add_col1:
                    add_item_chemical_id = st.selectbox(
                        "Chemical *",
                        options=list(chemical_map.keys()),
                        format_func=lambda x: chemical_map[x],
                        key="add_stocktake_item_chemical_id_existing"
                    )
                    add_item_location_id = st.selectbox(
                        "Location *",
                        options=list(edit_location_map.keys()),
                        format_func=lambda x: edit_location_map[x],
                        key="add_stocktake_item_location_id_existing"
                    )
                    add_item_batch_no = st.text_input(
                        "Batch No",
                        key="add_stocktake_item_batch_no_existing"
                    )

                with add_col2:
                    add_item_system_quantity = get_system_quantity(
                        add_item_chemical_id,
                        add_item_location_id,
                        add_item_batch_no
                    )
                    st.number_input(
                        "System Quantity",
                        value=float(add_item_system_quantity),
                        step=0.01,
                        disabled=True,
                        key="display_add_stocktake_system_quantity_existing"
                    )
                    add_item_counted_quantity = st.number_input(
                        "Counted Quantity *",
                        min_value=0.0,
                        value=0.0,
                        step=0.01,
                        key="add_stocktake_item_counted_quantity_existing"
                    )
                    add_item_variance_preview = float(add_item_counted_quantity) - float(add_item_system_quantity)
                    st.number_input(
                        "Variance Preview",
                        value=float(add_item_variance_preview),
                        step=0.01,
                        disabled=True,
                        key="display_add_stocktake_variance_existing"
                    )

                if st.button("Add Item to Session", key="add_item_to_existing_stocktake_session"):
                    add_item_errors = validate_stocktake_item(
                        add_item_chemical_id,
                        add_item_location_id,
                        add_item_system_quantity,
                        add_item_counted_quantity
                    )

                    if not location_belongs_to_warehouse(add_item_location_id, edit_session_warehouse_id):
                        add_item_errors.append("Selected location does not belong to the session warehouse.")

                    if add_item_errors:
                        show_validation_errors(add_item_errors)
                    else:
                        insert_query = """
                            INSERT INTO stocktake_items
                            (
                                session_id,
                                chemical_id,
                                location_id,
                                batch_no,
                                system_quantity,
                                counted_quantity
                            )
                            VALUES (%s, %s, %s, %s, %s, %s);
                        """

                        params = (
                            selected_edit_session_id,
                            add_item_chemical_id,
                            add_item_location_id,
                            clean_text(add_item_batch_no),
                            add_item_system_quantity,
                            add_item_counted_quantity
                        )

                        success, result = run_action(insert_query, params=params)

                        if success:
                            st.success("Stocktake item line added successfully.")
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
                    key="selected_edit_stocktake_item_id"
                )

                edit_item_row, edit_item_error = get_stocktake_item_by_id(selected_edit_item_id)

                if edit_item_error:
                    st.error(f"Unable to load the selected stocktake item line. {edit_item_error}")
                elif edit_item_row:
                    with st.form("edit_stocktake_item_form"):
                        item_col1, item_col2 = st.columns(2)

                        with item_col1:
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

                        with item_col2:
                            refreshed_system_quantity = get_system_quantity(
                                edit_item_chemical_id,
                                edit_item_location_id,
                                edit_item_batch_no
                            )
                            st.number_input(
                                "System Quantity",
                                value=float(refreshed_system_quantity),
                                step=0.01,
                                disabled=True,
                                key="display_edit_stocktake_system_quantity"
                            )
                            edit_item_counted_quantity = st.number_input(
                                "Counted Quantity *",
                                min_value=0.0,
                                value=float(edit_item_row[6]),
                                step=0.01
                            )
                            refreshed_variance = float(edit_item_counted_quantity) - float(refreshed_system_quantity)
                            st.number_input(
                                "Variance Preview",
                                value=float(refreshed_variance),
                                step=0.01,
                                disabled=True,
                                key="display_edit_stocktake_variance"
                            )

                        update_item_submitted = st.form_submit_button("Update Item Line")

                        if update_item_submitted:
                            item_errors = validate_stocktake_item(
                                edit_item_chemical_id,
                                edit_item_location_id,
                                refreshed_system_quantity,
                                edit_item_counted_quantity
                            )

                            if not location_belongs_to_warehouse(edit_item_location_id, edit_session_warehouse_id):
                                item_errors.append("Selected location does not belong to the session warehouse.")

                            if item_errors:
                                show_validation_errors(item_errors)
                            else:
                                update_query = """
                                    UPDATE stocktake_items
                                    SET
                                        chemical_id = %s,
                                        location_id = %s,
                                        batch_no = %s,
                                        system_quantity = %s,
                                        counted_quantity = %s
                                    WHERE id = %s;
                                """

                                params = (
                                    edit_item_chemical_id,
                                    edit_item_location_id,
                                    clean_text(edit_item_batch_no),
                                    refreshed_system_quantity,
                                    edit_item_counted_quantity,
                                    selected_edit_item_id
                                )

                                success, result = run_action(update_query, params=params)

                                if success:
                                    st.success("Stocktake item line updated successfully.")
                                    st.rerun()
                                else:
                                    st.error(result)

                st.divider()
                st.subheader("Delete Item Line")

                confirm_delete_item = st.checkbox(
                    "I confirm that I want to delete the selected stocktake item line.",
                    key="confirm_delete_stocktake_item"
                )

                if st.button("Delete Selected Item Line", key="delete_selected_stocktake_item_button"):
                    if not confirm_delete_item:
                        st.error("Please confirm deletion before deleting the item line.")
                    else:
                        delete_item_query = """
                            DELETE FROM stocktake_items
                            WHERE id = %s;
                        """
                        success, result = run_action(delete_item_query, params=(selected_edit_item_id,))

                        if success:
                            if result > 0:
                                st.success("Stocktake item line deleted successfully.")
                                st.rerun()
                            else:
                                st.warning("No stocktake item line was deleted.")
                        else:
                            st.error(result)

# ---------------------------------------------------------
# Tab 4: Delete Session
# ---------------------------------------------------------
with tab4:
    st.subheader("Delete Stocktake Session")
    st.warning("Deleting a stocktake session will also delete all of its item lines.")

    delete_sessions, delete_sessions_error = load_sessions()

    if delete_sessions_error:
        st.error(f"Unable to load stocktake sessions. {delete_sessions_error}")
    elif not delete_sessions:
        st.info("No stocktake sessions are available to delete.")
    else:
        delete_session_options = {
            row[0]: f"{row[1]} - {row[2]} - {row[3]} - {row[4]}"
            for row in delete_sessions
        }

        selected_delete_session_id = st.selectbox(
            "Select Session to Delete",
            options=list(delete_session_options.keys()),
            format_func=lambda x: delete_session_options[x],
            key="selected_delete_stocktake_session_id"
        )

        delete_session_row, delete_session_error = get_session_by_id(selected_delete_session_id)

        if delete_session_error:
            st.error(f"Unable to load session details. {delete_session_error}")
        elif delete_session_row:
            st.write(f"**Session Name:** {delete_session_row[1]}")
            st.write(f"**Warehouse ID:** {delete_session_row[2]}")
            st.write(f"**Planned Date:** {delete_session_row[3]}")
            st.write(f"**Completed Date:** {delete_session_row[4]}")
            st.write(f"**Status:** {delete_session_row[5]}")
            st.write(f"**Operator Name:** {delete_session_row[6]}")

            confirm_delete_session = st.checkbox(
                "I confirm that I want to delete this stocktake session.",
                key="confirm_delete_stocktake_session"
            )

            if st.button("Delete Stocktake Session", key="delete_stocktake_session_button"):
                if not confirm_delete_session:
                    st.error("Please confirm deletion before deleting the stocktake session.")
                else:
                    delete_query = """
                        DELETE FROM stocktake_sessions
                        WHERE id = %s;
                    """
                    success, result = run_action(delete_query, params=(selected_delete_session_id,))

                    if success:
                        if result > 0:
                            st.success("Stocktake session deleted successfully.")
                            st.rerun()
                        else:
                            st.warning("No stocktake session was deleted.")
                    else:
                        st.error(result)