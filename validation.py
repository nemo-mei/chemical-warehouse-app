from decimal import Decimal, InvalidOperation


def is_blank(value):
    """
    Return True if the value is None or an empty/whitespace string.
    """
    return value is None or str(value).strip() == ""


def add_required_error(errors, value, field_name):
    """
    Add an error if a required field is blank.
    """
    if is_blank(value):
        errors.append(f"{field_name} is required.")


def add_nonnegative_error(errors, value, field_name):
    """
    Add an error if the value is not numeric or is less than 0.
    """
    if is_blank(value):
        return

    try:
        number = Decimal(str(value))
        if number < 0:
            errors.append(f"{field_name} must be greater than or equal to 0.")
    except (InvalidOperation, ValueError):
        errors.append(f"{field_name} must be a valid number.")


def add_positive_error(errors, value, field_name):
    """
    Add an error if the value is not numeric or is less than or equal to 0.
    """
    if is_blank(value):
        return

    try:
        number = Decimal(str(value))
        if number <= 0:
            errors.append(f"{field_name} must be greater than 0.")
    except (InvalidOperation, ValueError):
        errors.append(f"{field_name} must be a valid number.")


def add_date_order_error(errors, start_date, end_date, start_name, end_name):
    """
    Add an error if both dates exist and start_date is after end_date.
    """
    if start_date and end_date and start_date > end_date:
        errors.append(f"{start_name} must be earlier than or equal to {end_name}.")


def add_choice_error(errors, value, field_name, allowed_values):
    """
    Add an error if value is not in the allowed list.
    """
    if value not in allowed_values:
        errors.append(f"{field_name} must be one of: {', '.join(allowed_values)}.")


def add_unique_error(errors, exists_flag, field_name):
    """
    Add an error if a value that should be unique already exists.
    """
    if exists_flag:
        errors.append(f"{field_name} already exists. Please enter a unique value.")


def add_outbound_stock_error(errors, requested_qty, available_qty):
    """
    Add an error if outbound quantity is greater than available stock.
    """
    if requested_qty is None or available_qty is None:
        return

    try:
        requested = Decimal(str(requested_qty))
        available = Decimal(str(available_qty))

        if requested > available:
            errors.append(
                f"Outbound quantity cannot exceed available stock. Available stock: {available}."
            )
    except (InvalidOperation, ValueError):
        errors.append("Quantity values must be valid numbers.")


def add_nonnegative_quantity_error(errors, value, field_name):
    """
    Separate helper for quantities like counted_quantity or system_quantity.
    """
    add_nonnegative_error(errors, value, field_name)


def validate_chemical_form(sku, chemical_name, unit, min_stock):
    """
    Validate chemical form fields.
    Returns a list of error messages.
    """
    errors = []

    add_required_error(errors, sku, "SKU")
    add_required_error(errors, chemical_name, "Chemical name")
    add_required_error(errors, unit, "Unit")
    add_nonnegative_error(errors, min_stock, "Minimum stock")

    return errors


def validate_warehouse_form(warehouse_name, warehouse_code):
    """
    Validate warehouse form fields.
    """
    errors = []

    add_required_error(errors, warehouse_name, "Warehouse name")
    add_required_error(errors, warehouse_code, "Warehouse code")

    return errors


def validate_location_form(location_code, capacity):
    """
    Validate storage location form fields.
    """
    errors = []

    add_required_error(errors, location_code, "Location code")
    add_nonnegative_error(errors, capacity, "Capacity")

    return errors


def validate_stock_document_header(doc_no, doc_type, warehouse_id, operator_name):
    """
    Validate stock document header fields.
    """
    errors = []

    add_required_error(errors, doc_no, "Document number")
    add_required_error(errors, doc_type, "Document type")
    add_required_error(errors, warehouse_id, "Warehouse")
    add_required_error(errors, operator_name, "Operator name")
    add_choice_error(errors, doc_type, "Document type", ["INBOUND", "OUTBOUND"])

    return errors


def validate_stock_document_item(
    chemical_id,
    location_id,
    quantity,
    unit_price,
    manufacture_date,
    expiry_date
):
    """
    Validate stock document item fields.
    """
    errors = []

    add_required_error(errors, chemical_id, "Chemical")
    add_required_error(errors, location_id, "Storage location")
    add_positive_error(errors, quantity, "Quantity")
    add_nonnegative_error(errors, unit_price, "Unit price")
    add_date_order_error(
        errors,
        manufacture_date,
        expiry_date,
        "Manufacture date",
        "Expiry date"
    )

    return errors


def validate_stocktake_session(session_name, warehouse_id, planned_date, status, operator_name):
    """
    Validate stocktake session fields.
    """
    errors = []

    add_required_error(errors, session_name, "Session name")
    add_required_error(errors, warehouse_id, "Warehouse")
    add_required_error(errors, planned_date, "Planned date")
    add_required_error(errors, status, "Status")
    add_required_error(errors, operator_name, "Operator name")
    add_choice_error(errors, status, "Status", ["OPEN", "COMPLETED"])

    return errors


def validate_stocktake_item(chemical_id, location_id, system_quantity, counted_quantity):
    """
    Validate stocktake item fields.
    """
    errors = []

    add_required_error(errors, chemical_id, "Chemical")
    add_required_error(errors, location_id, "Storage location")
    add_nonnegative_quantity_error(errors, system_quantity, "System quantity")
    add_nonnegative_quantity_error(errors, counted_quantity, "Counted quantity")

    return errors