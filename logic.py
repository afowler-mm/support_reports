status_mapping = {
    2: "Open",
    3: "Pending",
    4: "Resolved",
    5: "Closed",
    6: "Waiting on Customer",
    7: "7",
    8: "Awaiting Deploy",
    9: "Change for Tech Review",
    10: "10",
    11: "11",
    12: "Deferred",
    13: "Peer Review",
    14: "14",
    15: "15",
    16: "16",
    17: "17",
    18: "18",
    19: "19",
    20: "20"
}


def calculate_billable_time(time_entry, ticket_data, time_hours, product_options):
    # given a time entry, let's figure out how much time should actually be billed
    
    # here's the data we need:
    product_id = ticket_data.get("product_id")
    product_name = product_options.get(product_id, "Unknown product")
    change_request = ticket_data["custom_fields"].get("change_request", False)
    time_spent = time_entry["time_spent_in_seconds"] / 3600
    billing_status = ticket_data["custom_fields"].get("billing_status")

    # configurations:
    saas_products = ["BlocksOffice", "MonkeyWrench"]
    unbillable_billing_statuses = ["Free", "90 days", "Invoice"]
    
    # determine billable status:
    if billing_status in unbillable_billing_statuses:
        return 0
    elif change_request:
        return time_spent
    elif product_name in saas_products:
        return 0
    elif time_entry["billable"]:
        return time_spent
    else:
        return 0