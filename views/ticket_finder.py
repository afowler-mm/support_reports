import streamlit as st
import pandas as pd
from apis.freshdesk import freshdesk_api
from utils import date_range_selector
from logic import status_mapping


def display_ticket_finder(client_code: str, filters_container):
    with filters_container:
    
        if client_code == "admin":
            companies = freshdesk_api.get_companies()
            company_options = {c['name']: c['custom_fields'].get('company_code') for c in companies}
            selected_companies = st.multiselect("Select clients", list(company_options.keys()))
            selected_company_codes = [company_options[comp] for comp in selected_companies]
            
            # Show all tickets if no specific clients are selected
            if not selected_company_codes:
                st.info("No clients selected, showing tickets for all clients.")
                selected_company_codes = None
        else:
            # Non-admin users can only see their company's tickets
            selected_company_codes = [client_code]

        # Date range selection
        date_range = date_range_selector()
        start_date, end_date = date_range["start_date"], date_range["end_date"]
        
        st.divider()

    # Fetch and cache tickets
    with st.spinner("Loading tickets..."):
        tickets = get_tickets_within_date_range(start_date, end_date)

    if not tickets:
        st.warning("No tickets found in the selected range.")
        return

    # Filter tickets by selected companies
    if selected_company_codes:
        filtered_tickets = [
            ticket for ticket in tickets
            if ticket.get("company_id") and any(
                freshdesk_api.get_company_by_id(ticket["company_id"])["custom_fields"].get("company_code") == code
                for code in selected_company_codes
            )
        ]
    else:
        filtered_tickets = tickets

    if not filtered_tickets:
        st.write("No tickets found for the selected clients.")
        return

    # Convert to DataFrame for display
    tickets_df = pd.DataFrame(filtered_tickets)
    tickets_df["created_at"] = pd.to_datetime(tickets_df["created_at"]).dt.strftime('%Y-%m-%d %H:%M:%S')
    tickets_df["updated_at"] = pd.to_datetime(tickets_df["updated_at"]).dt.strftime('%Y-%m-%d %H:%M:%S')

    # Add category column (custom field)
    tickets_df["Category"] = tickets_df["custom_fields"].apply(lambda x: x.get("category", "Unknown"))

    # Add client name column for admins
    if client_code == "admin":
        def get_client_name(cid):
            if not cid or pd.isna(cid):  # Handle None or NaN cases
                return "Unknown"
            try:
                company = freshdesk_api.get_company_by_id(int(cid))
                return company.get("name", "Unknown")
            except (requests.exceptions.HTTPError, ValueError) as e:
                # Handle invalid or non-existent company_id
                st.warning(f"Unable to fetch company name for ID: {cid}. Error: {e}")
                return "Unknown"

        tickets_df["Client name"] = tickets_df["company_id"].apply(get_client_name)

    # Sort by creation date
    tickets_df = tickets_df.sort_values("created_at", ascending=False)

    # Add a column for clickable ticket links
    tickets_df["ticket_url"] = tickets_df["id"].apply(
        lambda tid: f"https://mademedia.freshdesk.com/support/tickets/{tid}"
    )
    
    # Add human-readable status column
    tickets_df["status_readable"] = tickets_df["status"].map(status_mapping).fillna("Unknown")

    # Display table with clickable links
    st.caption(f"Displaying {len(tickets_df)} tickets updated between {start_date} and {end_date}")
    display_columns = ["ticket_url", "subject", "Category", "status_readable", "created_at", "updated_at"]
    if client_code == "admin":
        display_columns.insert(2, "Client name")
        
    st.dataframe(
        tickets_df[display_columns],
        column_config={
            "ticket_url": st.column_config.LinkColumn("ID", display_text="tickets/(\\d+)"),
            "subject": st.column_config.TextColumn("Subject"),
            "Category": st.column_config.TextColumn("Category"),
            "status_readable": st.column_config.TextColumn("Status"),
            "created_at": st.column_config.DatetimeColumn("Created", format="ddd DD MMM YYYY, HH:mm z"),
            "updated_at": st.column_config.DatetimeColumn("Updated", format="ddd DD MMM YYYY, HH:mm z"),
        },
        hide_index=True,
        height=1000
    )



@st.cache_data(ttl=3600, show_spinner=False)
def get_tickets_within_date_range(start_date: str, end_date: str):
    # Fetch tickets updated within the date range
    tickets = freshdesk_api.get_tickets(updated_since=start_date)
    return [
        ticket for ticket in tickets
        if start_date <= ticket["updated_at"] <= end_date
    ]