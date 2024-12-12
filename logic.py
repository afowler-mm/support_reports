from apis.freshdesk import freshdesk_api

def calculate_billable_time(time_entry, ticket_data, time_hours):
    # given a time entry, let's figure out how much time should actually be billed
    
    # here's the data we need:
    product_id = ticket_data.get("product_id")
    product_options = freshdesk_api.get_product_options()
    product_name = product_options.get(product_id, "Unknown product")
    change_request = ticket_data["custom_fields"].get("change_request", False)
    time_spent = time_entry["time_spent_in_seconds"] / 3600
    billing_status = ticket_data["custom_fields"].get("billing_status")

    # And here's some config:
    saas_products = ["BlocksOffice", "MonkeyWrench"]
    unbillable_billing_statuses = ["Free", "90 days", "Invoice"]
    
    # Now we can work out whether the time entry is billable or not:
    if billing_status in unbillable_billing_statuses:
        return 0
        # If the ticket is has one of these billing statuses in FreshDesk, it's definitely not billable
    elif change_request:
        return time_spent
        # Otherwise, if the ticket is marked as a change request, it's billable
    elif product_name in saas_products:
        return 0
        # Then, if it's a SaaS product, it's not billable
    elif time_entry["billable"]:
        return time_spent
        # If it's not a SaaS product, and the time entry is marked as billable, it's billable
    else:
        return 0
        # Otherwise, it's not billable