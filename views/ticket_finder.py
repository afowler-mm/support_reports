import streamlit as st
import pandas as pd
from apis.freshdesk import freshdesk_api
from utils import date_range_selector
from logic import status_mapping


def display_ticket_finder(client_code: str):
    # Admin-only functionality
    if client_code == "admin":
        st.info("Select tickets for multiple clients using the multiselect.")
        companies = freshdesk_api.get_companies()
        company_options = {c['name']: c['custom_fields'].get('company_code') for c in companies}
        selected_companies = st.multiselect("Select clients", list(company_options.keys()))
        selected_company_codes = [company_options[comp] for comp in selected_companies]
    else:
        # Non-admin users can only see their company's tickets
        selected_company_codes = [client_code]

    # Date range selection
    date_range = date_range_selector()
    start_date, end_date = date_range["start_date"], date_range["end_date"]

    # Fetch and cache tickets
    with st.spinner("Loading tickets..."):
        tickets = get_tickets_within_date_range(start_date, end_date)

    if not tickets:
        st.write("No tickets found in the selected range.")
        return

    # Filter tickets by selected companies
    filtered_tickets = [
        ticket for ticket in tickets
        if ticket.get("company_id") and any(
            freshdesk_api.get_company_by_id(ticket["company_id"])["custom_fields"].get("company_code") == code
            for code in selected_company_codes
        )
    ]

    if not filtered_tickets:
        st.write("No tickets found for the selected clients.")
        return

    # Convert to DataFrame for display
    tickets_df = pd.DataFrame(filtered_tickets)
    tickets_df["created_at"] = pd.to_datetime(tickets_df["created_at"])
    tickets_df["updated_at"] = pd.to_datetime(tickets_df["updated_at"])
    
    # Map statuses to readable values
    tickets_df["status_readable"] = tickets_df["status"].map(status_mapping).fillna("Unknown")

    # Sort by creation date
    tickets_df = tickets_df.sort_values("created_at", ascending=False)

    # Add a column for clickable ticket links
    tickets_df["ticket_url"] = tickets_df["id"].apply(
        lambda tid: f"https://mademedia.freshdesk.com/support/tickets/{tid}"
    )

    # Display table with clickable links
    st.write(f"Displaying {len(tickets_df)} tickets:")
    st.dataframe(
        tickets_df[["ticket_url", "subject", "priority", "status_readable", "created_at", "updated_at"]],
        column_config={
            "ticket_url": st.column_config.LinkColumn(
                "ID",
                display_text="tickets/(\\d+)"
            ),
            "subject": st.column_config.TextColumn("Subject"),
            "priority": st.column_config.TextColumn("Priority"),
            "status_readable": st.column_config.TextColumn("Status"),
            "created_at": st.column_config.DatetimeColumn("Created At"),
            "updated_at": st.column_config.DatetimeColumn("Updated At"),
        },
        hide_index=True,
    )
    



@st.cache_data(ttl=3600, show_spinner=False)
def get_tickets_within_date_range(start_date: str, end_date: str):
    # Fetch tickets updated within the date range
    tickets = freshdesk_api.get_tickets(updated_since=start_date)
    return [
        ticket for ticket in tickets
        if start_date <= ticket["updated_at"] <= end_date
    ]