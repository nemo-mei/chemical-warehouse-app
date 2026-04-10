import streamlit as st


def clean_text(value):
    """
    Convert blank text values to None after stripping whitespace.
    """
    if value is None:
        return None

    text = str(value).strip()
    return text if text != "" else None


def format_decimal(value, default_value=0.0):
    """
    Convert a numeric value to float for display.
    """
    if value is None:
        return default_value
    return float(value)


def show_validation_errors(errors):
    """
    Show all validation errors together.
    """
    if not errors:
        return

    for error in errors:
        st.error(error)


def show_success_message(message):
    """
    Show a standard success message.
    """
    st.success(message)


def show_warning_message(message):
    """
    Show a standard warning message.
    """
    st.warning(message)


def show_error_message(message):
    """
    Show a standard error message.
    """
    st.error(message)


def show_no_data_message(message="No records found."):
    """
    Show a standard message when no data is available.
    """
    st.info(message)


def render_sidebar_instruction():
    """
    Show a standard instruction message for navigation.
    """
    st.info("Please use the sidebar to navigate to different functional pages.")


def render_section_title(title, description=None):
    """
    Render a section title and optional description.
    """
    st.subheader(title)

    if description:
        st.write(description)


def render_delete_confirmation(entity_name, key_prefix):
    """
    Render a reusable delete confirmation checkbox.

    Returns:
        bool: True if user checked confirmation, else False
    """
    return st.checkbox(
        f"I confirm that I want to delete this {entity_name}.",
        key=f"{key_prefix}_confirm_delete",
    )


def render_dataframe_or_message(
    data,
    empty_message="No records found.",
    use_container_width=True,
):
    """
    Display a dataframe when records exist, otherwise show an info message.
    """
    if data:
        st.dataframe(data, use_container_width=use_container_width)
    else:
        st.info(empty_message)


def format_warehouse_label(row):
    """
    Build a user-friendly warehouse label from a row tuple.
    Expected format: (id, warehouse_name, warehouse_code, ...)
    """
    return f"{row[1]} ({row[2]})"


def format_chemical_label(row):
    """
    Build a user-friendly chemical label from a row tuple.
    Expected format: (id, sku, chemical_name, unit, ...)
    """
    return f"{row[1]} - {row[2]}"


def format_location_label(row):
    """
    Build a user-friendly location label from a row tuple.
    Expected format: (id, location_code, location_type, ...)
    """
    location_type = row[2] if len(row) > 2 and row[2] else "No Type"
    return f"{row[1]} ({location_type})"


def variance_label(variance):
    """
    Return a readable label for stocktake variance.
    """
    if variance > 0:
        return "Surplus"

    if variance < 0:
        return "Shortage"

    return "Match"


def get_expiry_status(expiry_date, today_date):
    """
    Return a readable expiry status.
    """
    if expiry_date is None:
        return "No Expiry Date"

    days_left = (expiry_date - today_date).days

    if days_left < 0:
        return "Expired"

    if days_left <= 30:
        return "Expiring Within 30 Days"

    return "Valid"